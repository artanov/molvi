import sys

from molvi.app import _ensure_std_streams


def test_ensure_std_streams_replaces_none(monkeypatch):
    # windowed-сборка PyInstaller: консоли нет, потоки == None
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    _ensure_std_streams()
    # tqdm (внутри huggingface_hub) пишет прогресс в stderr — .write не должен падать
    assert sys.stdout is not None and sys.stderr is not None
    sys.stdout.write("x")
    sys.stderr.write("x")


def test_ensure_std_streams_keeps_real_streams(monkeypatch):
    real_out, real_err = sys.__stdout__, sys.__stderr__
    monkeypatch.setattr(sys, "stdout", real_out)
    monkeypatch.setattr(sys, "stderr", real_err)
    _ensure_std_streams()
    assert sys.stdout is real_out and sys.stderr is real_err
