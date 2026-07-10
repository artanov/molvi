"""Платформенный слой: выбор реализации по sys.platform.

Каждый подмодуль (hotkey, typer, autostart, sounds, overlay) существует в двух
вариантах — win32 и darwin — с одинаковым интерфейсом. Остальной код импортирует
их только отсюда: `from molvi.platform import hotkey`.

Подмодули грузятся лениво (PEP 562): typer на маке тянет Quartz/AppKit —
сотни миллисекунд, которые не должен платить, например, импорт sounds.
PyInstaller динамический импорт не видит — win32/darwin-модули перечислены
в hiddenimports обоих spec'ов.
"""
import importlib
import sys

if sys.platform == "win32":
    _BACKEND = "win32"
elif sys.platform == "darwin":
    _BACKEND = "darwin"
else:
    raise ImportError(f"Molvi не поддерживает платформу {sys.platform!r}")

_SUBMODULES = ("autostart", "hotkey", "overlay", "sounds", "typer")


def __getattr__(name):
    if name in _SUBMODULES:
        module = importlib.import_module(f"molvi.platform.{_BACKEND}.{name}")
        globals()[name] = module  # кэш: следующий доступ без importlib
        return module
    raise AttributeError(f"module 'molvi.platform' has no attribute {name!r}")


__all__ = list(_SUBMODULES)
