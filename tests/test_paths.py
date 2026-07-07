import sys
from pathlib import Path

import voiceflow.paths as paths


def test_dev_mode_uses_repo_root(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert paths.is_frozen() is False
    root = paths.repo_root()
    assert (root / "voiceflow").is_dir()
    assert paths.config_path() == root / "config.json"
    assert paths.log_path() == root / "voiceflow.log"
    assert paths.cuda_dir() == root / "cuda"
    assert paths.autostart_command() == str(root / "voiceflow.bat")


def test_frozen_mode_uses_appdata(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", r"C:\Apps\VoiceFlow\VoiceFlow.exe", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert paths.is_frozen() is True
    d = paths.data_dir()
    assert d == tmp_path / "VoiceFlow"
    assert d.is_dir()  # data_dir создаёт каталог
    assert paths.config_path() == d / "config.json"
    assert paths.cuda_dir() == d / "cuda"
    assert not paths.cuda_dir().exists()  # cuda_dir НЕ создаёт
    assert paths.autostart_command() == r'"C:\Apps\VoiceFlow\VoiceFlow.exe"'
