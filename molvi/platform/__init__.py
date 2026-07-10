"""Платформенный слой: выбор реализации по sys.platform.

Каждый подмодуль (hotkey, typer, autostart, sounds, overlay) существует в двух
вариантах — win32 и darwin — с одинаковым интерфейсом. Остальной код импортирует
их только отсюда: `from molvi.platform import hotkey`.
"""
import sys

if sys.platform == "win32":
    from molvi.platform.win32 import autostart, hotkey, overlay, sounds, typer
elif sys.platform == "darwin":
    from molvi.platform.darwin import autostart, hotkey, overlay, sounds, typer
else:
    raise ImportError(f"Molvi не поддерживает платформу {sys.platform!r}")

__all__ = ["autostart", "hotkey", "overlay", "sounds", "typer"]
