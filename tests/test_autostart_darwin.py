"""LaunchAgent-автозапуск macOS: чистый plistlib — гоняется на любой ОС."""
import plistlib

import pytest

from molvi.platform.darwin import autostart


@pytest.fixture
def plist_in_tmp(monkeypatch, tmp_path):
    path = tmp_path / "LaunchAgents" / "tech.molvi.app.plist"
    monkeypatch.setattr(autostart, "_plist_path", lambda: path)
    return path


def test_enable_disable_cycle(plist_in_tmp):
    assert autostart.is_enabled() is False
    autostart.enable('"/Applications/Molvi.app/Contents/MacOS/Molvi"')
    assert autostart.is_enabled() is True
    data = plistlib.loads(plist_in_tmp.read_bytes())
    assert data["Label"] == "tech.molvi.app"
    assert data["ProgramArguments"] == ["/Applications/Molvi.app/Contents/MacOS/Molvi"]
    assert data["RunAtLoad"] is True
    autostart.disable()
    assert autostart.is_enabled() is False
    assert not plist_in_tmp.exists()


def test_enable_splits_dev_command_into_argv(plist_in_tmp):
    # dev-команда «"python" -m molvi.app» с пробелом в пути питона
    autostart.enable('"/Users/x y/.venv/bin/python" -m molvi.app')
    data = plistlib.loads(plist_in_tmp.read_bytes())
    assert data["ProgramArguments"] == ["/Users/x y/.venv/bin/python", "-m", "molvi.app"]


def test_disable_when_absent_is_noop(plist_in_tmp):
    autostart.disable()  # не должно бросить
