"""macOS-часть оверлея: настоящая альфа-прозрачность окна Tk.

Фаза 0: минимум, чтобы оверлей рисовался. Фаза 2: не красть фокус
(NSApp activationPolicy), уровень поверх всех окон (NSWindow.level),
монитор активного окна (NSScreen). См. docs/macos-port.md.
"""
import logging

log = logging.getLogger(__name__)


def apply_no_activate(root):
    pass  # фаза 2: activationPolicy через PyObjC


def monitor_workarea():
    return None  # фаза 2: NSScreen активного окна; пока — экран по метрикам tk


def dpi(root):
    # Tk на маке работает в поинтах: 96 даёт те же видимые пропорции пилюли,
    # что 192 (200 %) на Windows-мониторе.
    return 96


def enable_transparency(root):
    """→ цвет фона окна/канвы: systemTransparent превращается в дырку."""
    root.attributes("-transparent", True)
    return "systemTransparent"


def pill_to_photoimage(root, rgba):
    """RGBA-пилюля как есть: у окна настоящая альфа, маттинг не нужен."""
    from PIL import ImageTk

    return ImageTk.PhotoImage(rgba, master=root)
