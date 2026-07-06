import time

import numpy as np
import pytest

from voiceflow.controller import Controller


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


def _make(audio_sec=1.0, text="привет мир", error=None, sounds=None):
    audio = np.zeros(int(16000 * audio_sec), dtype=np.float32)
    rec, tr, ui = FakeRecorder(audio), FakeTranscriber(text, error), FakeUI()
    inserted = []
    notes = []
    ctl = Controller(
        rec, tr, lambda t, m: inserted.append((t, m)), ui,
        min_duration_sec=0.3, samplerate=16000, paste_mode="clipboard",
        notify=notes.append, sounds=sounds,
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
