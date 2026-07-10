"""Разовая миграция данных со старого имени (VoiceFlow) на новое (Molvi).

Только для установленной (frozen) сборки: переносит %APPDATA%\\VoiceFlow →
%APPDATA%\\Molvi и чинит запись автозапуска в реестре, чтобы пользователь не
потерял config и уже скачанные CUDA-DLL. В dev-режиме данные лежат в корне
репозитория — мигрировать нечего. Всё best-effort: ошибка шага не мешает запуску.
"""
import os
import sys
from pathlib import Path

from molvi import paths

_OLD_APP_NAME = "VoiceFlow"
_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _appdata():
    return Path(os.environ.get("APPDATA", str(Path.home())))


def migrate_data_dir():
    """Переносит старую папку данных в новую, если новой ещё нет. → перенесли?"""
    old = _appdata() / _OLD_APP_NAME
    new = _appdata() / paths.APP_NAME
    if old.exists() and not new.exists():
        os.rename(old, new)
        return True
    return False


def migrate_autostart():
    """Убирает старую запись автозапуска VoiceFlow; если она была активна —
    ставит новую (Molvi) на текущий исполняемый файл. → была старая запись?"""
    import winreg

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0,
                        winreg.KEY_READ | winreg.KEY_SET_VALUE) as key:
        try:
            winreg.QueryValueEx(key, _OLD_APP_NAME)
        except FileNotFoundError:
            return False
        winreg.DeleteValue(key, _OLD_APP_NAME)

    from molvi import autostart
    autostart.enable(paths.autostart_command())
    return True


def run():
    """Прогнать все шаги миграции (только для frozen-сборки на Windows:
    под старым именем существовали только Windows-установки)."""
    if not paths.is_frozen() or sys.platform != "win32":
        return
    for step in (migrate_data_dir, migrate_autostart):
        try:
            step()
        except Exception:
            pass
