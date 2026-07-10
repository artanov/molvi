import sys
from pathlib import Path

import molvi.paths as paths


def test_dev_mode_uses_repo_root(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert paths.is_frozen() is False
    root = paths.repo_root()
    assert (root / "molvi").is_dir()
    assert paths.config_path() == root / "config.json"
    assert paths.log_path() == root / "molvi.log"
    assert paths.cuda_dir() == root / "cuda"


def test_dev_autostart_command_win(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setattr(paths.sys, "platform", "win32")
    # В кавычках — как и frozen-ветка: путь с пробелом не должен ломать автозапуск.
    assert paths.autostart_command() == f'"{paths.repo_root() / "molvi.bat"}"'


def test_dev_autostart_command_darwin(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setattr(paths.sys, "platform", "darwin")
    assert paths.autostart_command() == f'"{sys.executable}" -m molvi.app'


def test_frozen_mode_uses_appdata_on_windows(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", r"C:\Apps\Molvi\Molvi.exe", raising=False)
    monkeypatch.setattr(paths.sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert paths.is_frozen() is True
    d = paths.data_dir()
    assert d == tmp_path / "Molvi"
    assert d.is_dir()  # data_dir создаёт каталог
    assert paths.config_path() == d / "config.json"
    assert paths.cuda_dir() == d / "cuda"
    assert not paths.cuda_dir().exists()  # cuda_dir НЕ создаёт
    assert paths.autostart_command() == r'"C:\Apps\Molvi\Molvi.exe"'


def test_frozen_mode_uses_app_support_on_mac(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(paths.sys, "platform", "darwin")
    monkeypatch.setattr(paths.Path, "home", lambda: tmp_path)
    d = paths.data_dir()
    assert d == tmp_path / "Library" / "Application Support" / "Molvi"
    assert d.is_dir()  # data_dir создаёт каталог
    assert paths.config_path() == d / "config.json"
