import time

import numpy as np
import pytest

from voiceflow.controller import Controller


class FakeRecorder:
    def __init__(self, audio):
        self.audio = audio
        self.started = 0
    def start(self):
        self.started += 1
    def stop(self):
        return self.audio


class FakeTranscriber:
    def __init__(self, text="привет мир", error=None):
        self.text = text
        self.error = error
        self.calls = []
    def transcribe(self, audio):
        self.calls.append(audio)
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


def _make(audio_sec=1.0, text="привет мир", error=None):
    audio = np.zeros(int(16000 * audio_sec), dtype=np.float32)
    rec, tr, ui = FakeRecorder(audio), FakeTranscriber(text, error), FakeUI()
    inserted = []
    notes = []
    ctl = Controller(
        rec, tr, lambda t, m: inserted.append((t, m)), ui,
        min_duration_sec=0.3, samplerate=16000, paste_mode="clipboard",
        notify=notes.append,
    )
    ctl.start()
    return ctl, rec, tr, ui, inserted, notes


def test_full_cycle_inserts_text():
    ctl, rec, tr, ui, inserted, _ = _make()
    ctl.on_press()
    ctl.on_release()
    assert _wait_until(lambda: inserted)
    ctl.shutdown()
    assert inserted == [("привет мир", "clipboard")]
    assert ui.events == ["recording", "transcribing", "hide"]


def test_short_recording_ignored():
    ctl, rec, tr, ui, inserted, _ = _make(audio_sec=0.1)
    ctl.on_press()
    ctl.on_release()
    assert _wait_until(lambda: "hide" in ui.events)
    ctl.shutdown()
    assert inserted == []
    assert tr.calls == []


def test_empty_transcription_not_inserted():
    ctl, rec, tr, ui, inserted, _ = _make(text="")
    ctl.on_press()
    ctl.on_release()
    assert _wait_until(lambda: ui.events.count("hide") >= 1)
    ctl.shutdown()
    assert inserted == []


def test_paused_ignores_hotkey():
    ctl, rec, tr, ui, inserted, _ = _make()
    assert ctl.toggle_pause() is True
    ctl.on_press()
    ctl.on_release()
    time.sleep(0.1)
    ctl.shutdown()
    assert rec.started == 0
    assert inserted == []
    assert ctl.toggle_pause() is False


def test_transcribe_error_notifies_and_hides():
    ctl, rec, tr, ui, inserted, notes = _make(error=RuntimeError("boom"))
    ctl.on_press()
    ctl.on_release()
    assert _wait_until(lambda: notes)
    ctl.shutdown()
    assert inserted == []
    assert "hide" in ui.events


def test_release_without_press_is_noop():
    ctl, rec, tr, ui, inserted, _ = _make()
    ctl.on_release()
    time.sleep(0.05)
    ctl.shutdown()
    assert tr.calls == []
