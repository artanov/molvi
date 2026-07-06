import voiceflow.sounds as sounds_mod
from voiceflow.sounds import Sounds


def test_play_calls_winsound_async(monkeypatch, tmp_path):
    calls = []
    (tmp_path / "start.wav").write_bytes(b"RIFF")
    monkeypatch.setattr(sounds_mod, "ASSETS", tmp_path)
    monkeypatch.setattr(
        sounds_mod.winsound, "PlaySound", lambda name, flags: calls.append((name, flags))
    )
    s = Sounds(enabled=True)
    s.play_start()
    assert len(calls) == 1
    assert calls[0][0].endswith("start.wav")
    assert calls[0][1] == sounds_mod.winsound.SND_FILENAME | sounds_mod.winsound.SND_ASYNC


def test_disabled_plays_nothing(monkeypatch, tmp_path):
    calls = []
    (tmp_path / "start.wav").write_bytes(b"RIFF")
    monkeypatch.setattr(sounds_mod, "ASSETS", tmp_path)
    monkeypatch.setattr(sounds_mod.winsound, "PlaySound", lambda *a: calls.append(a))
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
