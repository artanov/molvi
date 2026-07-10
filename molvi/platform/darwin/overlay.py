"""macOS-часть оверлея: настоящая альфа-прозрачность Tk-окна, «не красть
фокус» через NSApp activationPolicy, уровень поверх окон через NSWindow,
монитор активного окна через CGWindowList + NSScreen."""
import logging

log = logging.getLogger(__name__)

def apply_no_activate(root):
    """Molvi — приложение строки меню: без иконки в Dock и без Cmd+Tab.

    Accessory-политики мало: deiconify() Tk-окна всё равно делает его key
    (терминал пользователя теряет фокус, и Cmd+V уходит в никуда, пока окно
    не вернут кликом). Класс help + noActivates — mac-эквивалент
    WS_EX_NOACTIVATE: окно показывается, не забирая активацию.
    Уровень отдельно не трогаем: help-окна и так floating, поверх обычных
    (winfo_id — не NSView, к NSWindow пути нет)."""
    from AppKit import NSApplication, NSApplicationActivationPolicyAccessory

    NSApplication.sharedApplication().setActivationPolicy_(
        NSApplicationActivationPolicyAccessory)
    root.tk.call("::tk::unsupported::MacWindowStyle", "style", root._w,
                 "help", "noActivates")
    # Tk deiconify() на маке активирует приложение (украл бы фокус у окна,
    # куда пользователь диктует) — поэтому окно маппится ОДИН раз здесь,
    # на старте, невидимым, а показ/скрытие дальше — только альфа+geometry
    # (show_window/hide_window), которые активацию не трогают.
    root.attributes("-alpha", 0.0)
    root.geometry("+20000+20000")
    root.deiconify()


def show_window(root):
    root.attributes("-alpha", 1.0)
    root.lift()


def hide_window(root):
    # Альфа 0 не отменяет перехват кликов — уводим окно ещё и за экран.
    root.attributes("-alpha", 0.0)
    root.geometry("+20000+20000")


def _frontmost_window_center():
    """Центр фронтального окна активного приложения (координаты CG, y вниз);
    None, если не нашли."""
    import Quartz
    from AppKit import NSWorkspace

    front = NSWorkspace.sharedWorkspace().frontmostApplication()
    if front is None:
        return None
    pid = front.processIdentifier()
    windows = Quartz.CGWindowListCopyWindowInfo(
        Quartz.kCGWindowListOptionOnScreenOnly, Quartz.kCGNullWindowID) or []
    for info in windows:
        # Слой 0 — обычные окна (без меню-бара, дока и наших оверлеев).
        if info.get("kCGWindowOwnerPID") != pid or info.get("kCGWindowLayer") != 0:
            continue
        b = info.get("kCGWindowBounds") or {}
        return b.get("X", 0) + b.get("Width", 0) / 2, b.get("Y", 0) + b.get("Height", 0) / 2
    return None


def monitor_workarea():
    """Рабочая область (l, t, r, b в tk-координатах) монитора с активным
    окном; None при ошибке — вызывающий откатится на метрики tk.

    NSScreen отсчитывает y снизу вверх от первичного экрана, tk и CGWindow —
    сверху вниз; переводим через высоту первичного экрана."""
    try:
        from AppKit import NSScreen

        screens = NSScreen.screens()
        if not screens:
            return None
        primary_h = screens[0].frame().size.height
        target = screens[0]
        center = _frontmost_window_center()
        if center is not None:
            cx, cy_cg = center
            cy = primary_h - cy_cg  # CG (y вниз) → Cocoa (y вверх)
            for scr in screens:
                f = scr.frame()
                if (f.origin.x <= cx < f.origin.x + f.size.width
                        and f.origin.y <= cy < f.origin.y + f.size.height):
                    target = scr
                    break
        vf = target.visibleFrame()  # без меню-бара и дока
        left = int(vf.origin.x)
        right = int(vf.origin.x + vf.size.width)
        top = int(primary_h - (vf.origin.y + vf.size.height))
        bottom = int(primary_h - vf.origin.y)
        return left, top, right, bottom
    except Exception:
        log.warning("Не удалось определить монитор активного окна", exc_info=True)
        return None


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
