import pytest

import molvi.sounds as sounds_mod
from molvi.sounds import Sounds


def test_play_uses_platform_backend(monkeypatch, tmp_path):
    calls = []
    (tmp_path / "start.wav").write_bytes(b"RIFF")
    monkeypatch.setattr(sounds_mod, "ASSETS", tmp_path)
    monkeypatch.setattr(sounds_mod, "_play_wav", lambda path: calls.append(path))
    s = Sounds(enabled=True)
    s.play_start()
    assert len(calls) == 1
    assert calls[0].endswith("start.wav")


def test_disabled_plays_nothing(monkeypatch, tmp_path):
    calls = []
    (tmp_path / "start.wav").write_bytes(b"RIFF")
    monkeypatch.setattr(sounds_mod, "ASSETS", tmp_path)
    monkeypatch.setattr(sounds_mod, "_play_wav", lambda path: calls.append(path))
    s = Sounds(enabled=False)
    s.play_start()
    s.play_stop()
    assert calls == []
    s.set_enabled(True)
    (tmp_path / "stop.wav").write_bytes(b"RIFF")
    s.play_stop()
    assert len(calls) == 1


def test_missing_file_warns_once_no_crash(monkeypatch, tmp_path, caplog):
    monkeypatch.setattr(sounds_mod, "ASSETS", tmp_path)  # пусто
    s = Sounds(enabled=True)
    with caplog.at_level("WARNING"):
        s.play_start()
        s.play_start()
    assert len([r for r in caplog.records if "start.wav" in r.message]) == 1


def test_backend_error_does_not_raise(monkeypatch, tmp_path):
    (tmp_path / "start.wav").write_bytes(b"RIFF")
    monkeypatch.setattr(sounds_mod, "ASSETS", tmp_path)
    monkeypatch.setattr(
        sounds_mod, "_play_wav",
        lambda path: (_ for _ in ()).throw(OSError("нет аудиоустройства")),
    )
    Sounds(enabled=True).play_start()  # не должно бросить


def test_win32_backend_plays_async(monkeypatch):
    win_sounds = pytest.importorskip(
        "molvi.platform.win32.sounds", reason="winsound — только Windows"
    )
    calls = []
    monkeypatch.setattr(
        win_sounds.winsound, "PlaySound",
        lambda name, flags: calls.append((name, flags)),
    )
    win_sounds.play_wav("x.wav")
    # SND_ASYNC обязателен: синхронный сигнал задержал бы старт записи.
    assert calls == [("x.wav",
                      win_sounds.winsound.SND_FILENAME | win_sounds.winsound.SND_ASYNC)]


def test_darwin_backend_plays_async(monkeypatch):
    darwin_sounds = pytest.importorskip(
        "molvi.platform.darwin.sounds", reason="afplay — только macOS"
    )
    calls = []
    monkeypatch.setattr(
        darwin_sounds.subprocess, "Popen",
        lambda cmd, **kw: calls.append(cmd),
    )
    darwin_sounds.play_wav("x.wav")
    assert calls == [["afplay", "x.wav"]]
