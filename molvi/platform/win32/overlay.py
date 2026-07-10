"""Windows-часть оверлея: прозрачность через ключевой цвет, WS_EX_NOACTIVATE,
рабочая область монитора активного окна, DPI."""
import ctypes
import ctypes.wintypes as wintypes
import logging

from molvi import theme

log = logging.getLogger(__name__)

GWL_EXSTYLE = -20
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080

KEY_COLOR = "#ff00fe"


def _hwnd(root):
    user32 = ctypes.windll.user32
    user32.GetParent.argtypes = [wintypes.HWND]
    user32.GetParent.restype = wintypes.HWND
    return user32.GetParent(root.winfo_id()) or root.winfo_id()


def apply_no_activate(root):
    """Окно не забирает фокус — иначе вставка ушла бы в оверлей.
    Вызывать ДО первого показа окна: первый deiconify() украл бы фокус."""
    user32 = ctypes.windll.user32
    user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
    user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
    user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
    hwnd = _hwnd(root)
    style = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
    user32.SetWindowLongPtrW(
        hwnd, GWL_EXSTYLE, style | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW
    )


def monitor_workarea():
    """Рабочая область монитора с активным окном; None при ошибке.

    Пилюля должна быть на том же мониторе, куда печатается текст, —
    winfo_screenwidth() на нескольких мониторах давал центр всего
    виртуального стола, и оверлей уезжал на соседний экран."""
    try:
        user32 = ctypes.windll.user32

        class MONITORINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD),
                        ("rcMonitor", wintypes.RECT),
                        ("rcWork", wintypes.RECT),
                        ("dwFlags", wintypes.DWORD)]

        MONITOR_DEFAULTTONEAREST = 2
        monitor = user32.MonitorFromWindow(
            user32.GetForegroundWindow(), MONITOR_DEFAULTTONEAREST)
        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(MONITORINFO)
        if not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            return None
        r = info.rcWork
        return r.left, r.top, r.right, r.bottom
    except Exception:
        log.warning("Не удалось определить монитор активного окна", exc_info=True)
        return None


def dpi(root):
    try:
        user32 = ctypes.windll.user32
        user32.GetDpiForWindow.argtypes = [wintypes.HWND]
        user32.GetDpiForWindow.restype = wintypes.UINT
        return user32.GetDpiForWindow(_hwnd(root)) or 96
    except Exception:
        return 96


def show_window(root):
    root.deiconify()


def hide_window(root):
    root.withdraw()


def enable_transparency(root):
    """→ цвет фона окна/канвы: всё, что им закрашено, становится прозрачным."""
    root.attributes("-transparentcolor", KEY_COLOR)
    return KEY_COLOR


def pill_to_photoimage(root, rgba):
    """RGBA-пилюля → PhotoImage поверх ключевого цвета.

    Ключевой цвет прозрачен только при ТОЧНОМ совпадении, поэтому альфу
    делаем бинарной, примешав полупрозрачные пиксели к тёмному матту
    (иначе — розовая кайма)."""
    from PIL import Image, ImageTk

    matte = Image.new("RGBA", rgba.size, theme.INK_800)
    matte.alpha_composite(rgba)
    hard_alpha = rgba.getchannel("A").point(lambda a: 255 if a >= 128 else 0)
    bg = Image.new("RGB", rgba.size, KEY_COLOR)
    bg.paste(matte.convert("RGB"), mask=hard_alpha)
    return ImageTk.PhotoImage(bg, master=root)
