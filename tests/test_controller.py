import time

import numpy as np
import pytest

from molvi import i18n
from molvi.controller import Controller


@pytest.fixture(autouse=True)
def _reset_language():
    # Уведомления идут через tr() — фиксируем язык, чтобы тесты не зависели
    # от порядка запуска (другой файл мог оставить i18n в состоянии "en").
    i18n.set_language("ru")
    yield
    i18n.set_language("ru")


class FakeRecorder:
    def __init__(self, audio):
        self.audio = audio
        self.started = 0
        self.stop_error = None
        self.device = None
    def start(self):
        self.started += 1
    def stop(self):
        if self.stop_error is not None:
            raise self.stop_error
        return self.audio


class FakeTranscriber:
    def __init__(self, text="привет мир", error=None, delay=0.0):
        self.text = text
        self.error = error
        self.delay = delay
        self.calls = []
    def transcribe(self, audio):
        self.calls.append(audio)
        if self.delay:
            time.sleep(self.delay)
        if self.error:
            raise self.error
        return self.text


class FakeUI:
    def __init__(self):
        self.events = []
    def show_recording(self):
        self.events.append("recording")
    def show_transcribing(self):
        self.events.append("transcribing")
    def hide(self):
        self.events.append("hide")


def _wait_until(cond, timeout=2.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if cond():
            return True
        time.sleep(0.01)
    return False


class FakeSounds:
    def __init__(self):
        self.events = []
    def play_start(self):
        self.events.append("start")
    def play_stop(self):
        self.events.append("stop")


def _make(audio_sec=1.0, text="привет мир", error=None, sounds=None,
          target_fns=None):
    audio = np.zeros(int(16000 * audio_sec), dtype=np.float32)
    rec, tr, ui = FakeRecorder(audio), FakeTranscriber(text, error), FakeUI()
    inserted = []
    notes = []
    ctl = Controller(
        rec, tr, lambda t, m: inserted.append((t, m)), ui,
        min_duration_sec=0.3, samplerate=16000, paste_mode="clipboard",
        notify=notes.append, sounds=sounds, target_fns=target_fns,
    )
    ctl.start()
    return ctl, rec, tr, ui, inserted, notes, sounds


def test_full_cycle_inserts_text():
    ctl, rec, tr, ui, inserted, *_ = _make()
    ctl.on_press()
    ctl.on_release()
    assert _wait_until(lambda: inserted)
    ctl.shutdown()
    assert inserted == [("привет мир", "clipboard")]
    assert ui.events == ["recording", "transcribing", "hide"]


def test_short_recording_ignored():
    ctl, rec, tr, ui, inserted, *_ = _make(audio_sec=0.1)
    ctl.on_press()
    ctl.on_release()
    assert _wait_until(lambda: "hide" in ui.events)
    ctl.shutdown()
    assert inserted == []
    assert tr.calls == []


def test_empty_transcription_not_inserted():
    ctl, rec, tr, ui, inserted, *_ = _make(text="")
    ctl.on_press()
    ctl.on_release()
    assert _wait_until(lambda: ui.events.count("hide") >= 1)
    ctl.shutdown()
    assert inserted == []


def test_paused_ignores_hotkey():
    ctl, rec, tr, ui, inserted, *_ = _make()
    assert ctl.toggle_pause() is True
    ctl.on_press()
    ctl.on_release()
    time.sleep(0.1)
    ctl.shutdown()
    assert rec.started == 0
    assert inserted == []
    assert ctl.toggle_pause() is False


def test_transcribe_error_notifies_and_hides():
    ctl, rec, tr, ui, inserted, notes, _ = _make(error=RuntimeError("boom"))
    ctl.on_press()
    ctl.on_release()
    assert _wait_until(lambda: notes)
    ctl.shutdown()
    assert inserted == []
    assert "hide" in ui.events


def test_recorder_stop_error_notifies_and_hides():
    ctl, rec, tr, ui, inserted, notes, _ = _make()
    rec.stop_error = RuntimeError("device lost")
    ctl.on_press()
    ctl.on_release()
    assert notes  # notify called synchronously from the hook thread
    assert "hide" in ui.events
    assert tr.calls == []
    assert inserted == []
    # Controller survives: a subsequent cycle with the error cleared works.
    rec.stop_error = None
    ctl.on_press()
    ctl.on_release()
    assert _wait_until(lambda: inserted)
    ctl.shutdown()
    assert inserted == [("привет мир", "clipboard")]


def test_overlay_not_hidden_while_next_recording_active():
    audio = np.zeros(int(16000 * 1.0), dtype=np.float32)
    rec, tr, ui = FakeRecorder(audio), FakeTranscriber(delay=0.2), FakeUI()
    inserted = []
    ctl = Controller(
        rec, tr, lambda t, m: inserted.append((t, m)), ui,
        min_duration_sec=0.3, samplerate=16000, paste_mode="clipboard",
    )
    ctl.start()
    ctl.on_press()
    ctl.on_release()  # job1 queued, worker sleeps ~0.2s inside transcribe()
    time.sleep(0.05)  # worker is now mid-job on job1
    ctl.on_press()  # user starts recording the next phrase before job1 finishes
    assert _wait_until(lambda: len(inserted) == 1)
    # job1's worker-loop finally ran while a new recording was active — it must
    # not have hidden the "Запись…" indicator for the recording in progress.
    assert ui.events == ["recording", "transcribing", "recording"]
    ctl.on_release()  # job2 queued; nothing is recording anymore afterwards
    assert _wait_until(lambda: len(inserted) == 2)
    assert ui.events[-1] == "hide"
    ctl.shutdown()


def test_release_without_press_is_noop():
    ctl, rec, tr, ui, inserted, *_ = _make()
    ctl.on_release()
    time.sleep(0.05)
    ctl.shutdown()
    assert tr.calls == []


def test_sounds_played_on_start_and_enqueue():
    sounds = FakeSounds()
    ctl, rec, tr, ui, inserted, notes, snd = _make(sounds=sounds)
    ctl.on_press()
    ctl.on_release()
    assert _wait_until(lambda: inserted)
    ctl.shutdown()
    assert snd.events == ["start", "stop"]


def test_short_recording_plays_no_stop_sound():
    sounds = FakeSounds()
    ctl, rec, tr, ui, inserted, notes, snd = _make(audio_sec=0.1, sounds=sounds)
    ctl.on_press()
    ctl.on_release()
    ctl.shutdown()
    assert snd.events == ["start"]


def test_model_reload_blocks_dictation_and_swaps_transcriber():
    ctl, rec, tr, ui, inserted, notes, _ = _make()
    token = ctl.begin_model_reload()
    ctl.on_press()
    ctl.on_release()
    assert rec.started == 0
    new_tr = FakeTranscriber(text="новая модель")
    ctl.finish_model_reload(new_tr, token)
    ctl.on_press()
    ctl.on_release()
    assert _wait_until(lambda: inserted)
    ctl.shutdown()
    assert inserted == [("новая модель", "clipboard")]


def test_model_reload_failure_keeps_old_transcriber():
    ctl, rec, tr, ui, inserted, notes, _ = _make(text="старая модель")
    token = ctl.begin_model_reload()
    ctl.finish_model_reload(None, token)   # загрузка не удалась — откат
    ctl.on_press()
    ctl.on_release()
    assert _wait_until(lambda: inserted)
    ctl.shutdown()
    assert inserted == [("старая модель", "clipboard")]


def test_stale_reload_ignored():
    ctl, rec, tr, ui, inserted, notes, _ = _make(text="исходная модель")
    t1 = ctl.begin_model_reload()
    t2 = ctl.begin_model_reload()
    tr_a = FakeTranscriber(text="модель A")
    ctl.finish_model_reload(tr_a, t1)  # устаревший — должен быть проигнорирован
    ctl.on_press()
    ctl.on_release()
    assert rec.started == 0  # всё ещё считается идущей перезагрузка t2
    tr_b = FakeTranscriber(text="модель B")
    ctl.finish_model_reload(tr_b, t2)  # актуальный — применяется
    ctl.on_press()
    ctl.on_release()
    assert _wait_until(lambda: inserted)
    ctl.shutdown()
    assert inserted == [("модель B", "clipboard")]


def test_set_device_applies_to_recorder():
    ctl, rec, tr, ui, inserted, notes, _ = _make()
    ctl.set_device("Mic B")
    ctl.shutdown()
    assert rec.device == "Mic B"


def test_set_language_forwarded_to_transcriber():
    ctl, rec, tr, ui, inserted, notes, _ = _make()
    tr.language = None
    tr.set_language = lambda lang: setattr(tr, "language", lang)
    ctl.set_language("ru")
    ctl.shutdown()
    assert tr.language == "ru"


def test_transcribe_error_message_does_not_mention_clipboard():
    # В буфере ничего нет — сообщение не должно врать про Ctrl+V.
    ctl, rec, tr, ui, inserted, notes, _ = _make(error=RuntimeError("boom"))
    ctl.on_press()
    ctl.on_release()
    assert _wait_until(lambda: notes)
    ctl.shutdown()
    assert notes[0] == i18n.tr("controller.transcribe_error", exc=RuntimeError("boom"))
    assert "буфер" not in notes[0]


def test_insert_error_message_mentions_clipboard():
    # Вставка сорвалась — текст в буфере (insert_fn кладёт его туда), говорим об этом.
    audio = np.zeros(16000, dtype=np.float32)
    rec, tr, ui = FakeRecorder(audio), FakeTranscriber("текст"), FakeUI()
    notes = []

    def failing_insert(t, m):
        raise OSError("SendInput failed")

    ctl = Controller(
        rec, tr, failing_insert, ui, min_duration_sec=0.3,
        samplerate=16000, paste_mode="clipboard", notify=notes.append,
    )
    ctl.start()
    ctl.on_press()
    ctl.on_release()
    assert _wait_until(lambda: notes)
    ctl.shutdown()
    assert notes[0] == i18n.tr(
        "controller.paste_error", exc=OSError("SendInput failed"), paste_hint="Ctrl+V"
    )


def test_failed_recorder_start_leaves_not_recording():
    ctl, rec, tr, ui, inserted, notes, _ = _make()
    rec.start = lambda: (_ for _ in ()).throw(OSError("device busy"))
    ctl.on_press()
    assert notes  # пользователь уведомлён
    # Флаг записи не выставлен: следующий on_release — no-op, а не фантомный стоп.
    ctl.on_release()
    ctl.shutdown()
    assert tr.calls == []
    assert ui.events[-1] == "hide"


def test_last_text_none_before_first_dictation():
    ctl, *_ = _make()
    ctl.shutdown()
    assert ctl.last_text() is None


def test_last_text_saved_after_transcription():
    ctl, rec, tr, ui, inserted, *_ = _make(text="привет мир")
    ctl.on_press()
    ctl.on_release()
    assert _wait_until(lambda: inserted)
    ctl.shutdown()
    assert ctl.last_text() == "привет мир"


def test_last_text_saved_even_if_insert_fails():
    # Смысл фичи: расшифровка не должна пропасть, даже когда вставка упала.
    audio = np.zeros(16000, dtype=np.float32)
    rec, tr, ui = FakeRecorder(audio), FakeTranscriber("важный текст"), FakeUI()
    notes = []

    def failing_insert(t, m):
        raise OSError("SendInput failed")

    ctl = Controller(
        rec, tr, failing_insert, ui, min_duration_sec=0.3,
        samplerate=16000, paste_mode="clipboard", notify=notes.append,
    )
    ctl.start()
    ctl.on_press()
    ctl.on_release()
    assert _wait_until(lambda: notes)
    ctl.shutdown()
    assert ctl.last_text() == "важный текст"


def test_empty_transcription_keeps_previous_last_text():
    ctl, rec, tr, ui, inserted, *_ = _make(text="привет мир")
    ctl.on_press()
    ctl.on_release()
    assert _wait_until(lambda: inserted)
    tr.text = ""   # следующая диктовка распознана в пустоту
    ctl.on_press()
    ctl.on_release()
    assert _wait_until(lambda: ui.events.count("hide") >= 2)
    ctl.shutdown()
    assert ctl.last_text() == "привет мир"


class FakeTarget:
    """Функции цели: журнал вызовов + управляемое поведение фокуса."""
    def __init__(self, target="win1", foreground=True, activate_ok=True):
        self.target = target
        self.foreground = foreground
        self.activate_ok = activate_ok
        self.calls = []

    def get_target(self):
        self.calls.append("get")
        return self.target

    def is_foreground(self, t):
        self.calls.append(("is_fg", t))
        return self.foreground

    def activate(self, t):
        self.calls.append(("activate", t))
        return self.activate_ok

    @property
    def fns(self):
        return (self.get_target, self.is_foreground, self.activate)


def test_target_unchanged_inserts_without_activate():
    ft = FakeTarget(foreground=True)
    ctl, rec, tr, ui, inserted, notes, _ = _make(target_fns=ft.fns)
    ctl.on_press()
    ctl.on_release()
    assert _wait_until(lambda: inserted)
    ctl.shutdown()
    assert "get" in ft.calls
    assert ("is_fg", "win1") in ft.calls
    assert ("activate", "win1") not in ft.calls
    assert inserted == [("привет мир", "clipboard")]


def test_focus_changed_activates_then_inserts():
    ft = FakeTarget(foreground=False, activate_ok=True)
    ctl, rec, tr, ui, inserted, notes, _ = _make(target_fns=ft.fns)
    ctl.on_press()
    ctl.on_release()
    assert _wait_until(lambda: inserted)
    ctl.shutdown()
    assert ("activate", "win1") in ft.calls
    assert inserted == [("привет мир", "clipboard")]


def test_activate_failed_skips_insert_and_notifies():
    ft = FakeTarget(foreground=False, activate_ok=False)
    ctl, rec, tr, ui, inserted, notes, _ = _make(target_fns=ft.fns)
    ctl.on_press()
    ctl.on_release()
    assert _wait_until(lambda: notes)
    ctl.shutdown()
    assert inserted == []
    assert notes[0] == i18n.tr("controller.target_lost")
    assert ctl.last_text() == "привет мир"  # текст спасает трей


def test_get_target_error_degrades_to_old_behavior():
    ft = FakeTarget()
    ft.get_target = lambda: (_ for _ in ()).throw(OSError("no window"))
    ctl, rec, tr, ui, inserted, notes, _ = _make(target_fns=ft.fns)
    ctl.on_press()
    ctl.on_release()
    assert _wait_until(lambda: inserted)
    ctl.shutdown()
    assert inserted == [("привет мир", "clipboard")]


def test_no_target_fns_keeps_old_behavior():
    ctl, rec, tr, ui, inserted, notes, _ = _make()
    ctl.on_press()
    ctl.on_release()
    assert _wait_until(lambda: inserted)
    ctl.shutdown()
    assert inserted == [("привет мир", "clipboard")]


def _make_slow(text="текст", delay=0.3):
    audio = np.zeros(16000, dtype=np.float32)
    rec, tr, ui = FakeRecorder(audio), FakeTranscriber(text, delay=delay), FakeUI()
    inserted, notes = [], []
    ctl = Controller(
        rec, tr, lambda t, m: inserted.append((t, m)), ui,
        min_duration_sec=0.3, samplerate=16000, paste_mode="clipboard",
        notify=notes.append,
    )
    ctl.start()
    return ctl, tr, ui, inserted, notes


def test_cancel_pending_skips_insert_keeps_text():
    ctl, tr, ui, inserted, notes = _make_slow()
    ctl.on_press()
    ctl.on_release()
    time.sleep(0.05)          # распознавание началось (delay=0.3)
    ctl.cancel_pending()
    assert _wait_until(lambda: notes)
    ctl.shutdown()
    assert inserted == []
    assert ctl.last_text() == "текст"
    assert notes[0] == i18n.tr("controller.paste_cancelled")


def test_cancel_outside_processing_is_noop():
    ctl, rec, tr, ui, inserted, notes, _ = _make()
    ctl.cancel_pending()      # заданий нет — Esc в обычной работе безвреден
    ctl.on_press()
    ctl.on_release()
    assert _wait_until(lambda: inserted)
    ctl.shutdown()
    assert notes == []
    assert inserted == [("привет мир", "clipboard")]


def test_next_dictation_after_cancel_inserts():
    ctl, tr, ui, inserted, notes = _make_slow()
    ctl.on_press()
    ctl.on_release()
    time.sleep(0.05)
    ctl.cancel_pending()
    assert _wait_until(lambda: notes)
    ctl.on_press()            # новая диктовка — новое намерение вставить
    ctl.on_release()
    assert _wait_until(lambda: inserted)
    ctl.shutdown()
    assert inserted == [("текст", "clipboard")]
