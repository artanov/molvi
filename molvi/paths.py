"""Пути данных: dev-режим — корень репозитория, frozen (PyInstaller) — %APPDATA%."""
import os
import sys
from pathlib import Path

APP_NAME = "Molvi"


def is_frozen():
    return bool(getattr(sys, "frozen", False))


def repo_root():
    return Path(__file__).resolve().parents[1]


def data_dir():
    if is_frozen():
        base = Path(os.environ.get("APPDATA", str(Path.home()))) / APP_NAME
    else:
        base = repo_root()
    base.mkdir(parents=True, exist_ok=True)
    return base


def config_path():
    return data_dir() / "config.json"


def log_path():
    return data_dir() / "molvi.log"


def cuda_dir():
    return data_dir() / "cuda"


def autostart_command():
    if is_frozen():
        return f'"{sys.executable}"'
    return f'"{repo_root() / "molvi.bat"}"'  # путь с пробелом сломал бы автозапуск
