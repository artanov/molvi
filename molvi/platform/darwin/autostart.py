"""Автозапуск на macOS: LaunchAgent plist в ~/Library/LaunchAgents.

launchctl не зовём: RunAtLoad сработает при следующем входе в систему,
а немедленный запуск второй копии поверх работающей только мешал бы.
"""
import logging
import plistlib
import shlex
from pathlib import Path

from molvi import paths

log = logging.getLogger(__name__)

LABEL = "Запускать при входе в систему"

_PLIST_LABEL = "tech.molvi.app"


def _plist_path():
    return Path.home() / "Library" / "LaunchAgents" / f"{_PLIST_LABEL}.plist"


def is_enabled():
    return _plist_path().is_file()


def enable(command):
    # command — строка из paths.autostart_command() (пути в кавычках);
    # LaunchAgent ждёт argv-список.
    plist = {
        "Label": _PLIST_LABEL,
        "ProgramArguments": shlex.split(command),
        "RunAtLoad": True,
        "LimitLoadToSessionType": "Aqua",  # только GUI-сессия, не ssh
    }
    if not paths.is_frozen():
        # dev-команда — «python -m molvi.app»: launchd стартует из «/»,
        # без cwd в корне репозитория модуль molvi не найдётся.
        plist["WorkingDirectory"] = str(paths.repo_root())
    path = _plist_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        plistlib.dump(plist, f)


def disable():
    _plist_path().unlink(missing_ok=True)
