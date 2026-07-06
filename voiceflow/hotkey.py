import ctypes
import ctypes.wintypes as wintypes
import logging

log = logging.getLogger(__name__)

_user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32

WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105
WM_QUIT = 0x0012
VK_RCONTROL = 0xA3
VK_LCONTROL = 0xA2

VK_ESCAPE = 0x1B
LLKHF_INJECTED = 0x10

VK_NAMES = {}
for _i in range(26):
    VK_NAMES[chr(ord("a") + _i)] = 0x41 + _i
for _i in range(10):
    VK_NAMES[str(_i)] = 0x30 + _i
for _i in range(24):
    VK_NAMES[f"f{_i + 1}"] = 0x70 + _i
VK_NAMES.update({
    "ctrl_left": 0xA2, "ctrl_right": 0xA3,
    "shift_left": 0xA0, "shift_right": 0xA1,
    "alt_left": 0xA4, "alt_right": 0xA5,
    "win_left": 0x5B, "win_right": 0x5C,
    "space": 0x20, "capslock": 0x14, "tab": 0x09, "backquote": 0xC0,
    "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
    "insert": 0x2D, "delete": 0x2E, "home": 0x24, "end": 0x23,
    "pageup": 0x21, "pagedown": 0x22,
})
VK_TO_NAME = {v: k for k, v in VK_NAMES.items()}

MODIFIER_NAMES = {
    "ctrl_left", "ctrl_right", "shift_left", "shift_right",
    "alt_left", "alt_right", "win_left", "win_right",
}

_DISPLAY = {
    "ctrl_left": "Ctrl слева", "ctrl_right": "Ctrl справа",
    "shift_left": "Shift слева", "shift_right": "Shift справа",
    "alt_left": "Alt слева", "alt_right": "Alt справа",
    "win_left": "Win слева", "win_right": "Win справа",
    "space": "Пробел", "capslock": "CapsLock", "tab": "Tab",
    "backquote": "`", "left": "←", "up": "↑", "right": "→", "down": "↓",
    "insert": "Insert", "delete": "Delete", "home": "Home", "end": "End",
    "pageup": "PageUp", "pagedown": "PageDown",
}


def names_to_vks(names):
    vks = []
    for name in names:
        vk = VK_NAMES.get(name)
        if vk is None:
            raise ValueError(f"Неизвестное имя клавиши: {name!r}")
        vks.append(vk)
    return vks


def human_label(names):
    return " + ".join(_DISPLAY.get(n, n.upper()) for n in names)


def normalize_capture(vks):
    names = [VK_TO_NAME[vk] for vk in vks if vk in VK_TO_NAME]
    mods = sorted((n for n in names if n in MODIFIER_NAMES), key=lambda n: VK_NAMES[n])
    rest = sorted((n for n in names if n not in MODIFIER_NAMES), key=lambda n: VK_NAMES[n])
    return mods + rest


_HOOKPROC = ctypes.CFUNCTYPE(
    ctypes.c_longlong, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM
)

LRESULT = ctypes.c_ssize_t  # LONG_PTR: pointer-width, not c_int

_user32.SetWindowsHookExW.argtypes = [
    ctypes.c_int, _HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD
]
_user32.SetWindowsHookExW.restype = wintypes.HHOOK
_user32.CallNextHookEx.argtypes = [
    wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM
]
_user32.CallNextHookEx.restype = LRESULT
_user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
_user32.UnhookWindowsHookEx.restype = wintypes.BOOL
_user32.GetMessageW.argtypes = [
    ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT
]
_user32.GetMessageW.restype = ctypes.c_int
_user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
_user32.TranslateMessage.restype = wintypes.BOOL
_user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
_user32.DispatchMessageW.restype = LRESULT
_user32.PostThreadMessageW.argtypes = [
    wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
]
_user32.PostThreadMessageW.restype = wintypes.BOOL
_kernel32.GetCurrentThreadId.argtypes = []
_kernel32.GetCurrentThreadId.restype = wintypes.DWORD


class _KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG)),
    ]


class HotkeyListener:
    """Push-to-talk по комбинации клавиш.

    Все клавиши комбо зажаты → on_press; любая отпущена → on_release;
    повторный on_press — только после полного отпускания всех клавиш.
    Инжектированные события игнорируются: иначе собственная эмуляция
    Ctrl+V дёргала бы hotkey, содержащий Ctrl.
    """

    def __init__(self, on_press, on_release, combo):
        self._on_press = on_press
        self._on_release = on_release
        self._combo = frozenset(combo)
        self._down = set()
        self._released = set()
        self._active = False
        self._armed = True
        self._capture_cb = None
        self._cap_peak = set()
        self._cap_down = set()
        self._hook = None
        self._thread_id = None
        self._proc = _HOOKPROC(self._low_level_proc)  # держим ссылку от GC

    def set_combo(self, vks):
        if self._active:
            self._active = False
            self._on_release()
        self._combo = frozenset(vks)
        self._down = set()
        self._released = set()
        self._armed = True

    def start_capture(self, callback):
        """Копит зажатые клавиши; все отпущены → callback(имена), Esc → callback(None)."""
        if self._active:
            self._active = False
            self._on_release()
        self._down = set()
        self._released = set()
        self._cap_peak = set()
        self._cap_down = set()
        self._capture_cb = callback

    def _handle(self, msg, vk, injected=False):
        if injected:
            return
        if self._capture_cb is not None:
            self._handle_capture(msg, vk)
            return
        if vk not in self._combo:
            return
        if msg in (WM_KEYDOWN, WM_SYSKEYDOWN):
            self._down.add(vk)
            if self._armed and self._down == self._combo:
                self._armed = False
                self._released = set()
                self._active = True
                self._on_press()
        elif msg in (WM_KEYUP, WM_SYSKEYUP):
            self._down.discard(vk)
            if self._active:
                self._active = False
                self._on_release()
            # "Полное отпускание" — каждая клавиша комбо хоть раз была
            # отпущена по отдельности с последнего срабатывания (не
            # обязательно все одновременно, см. test_no_refire_until_full_release).
            self._released.add(vk)
            if self._released >= self._combo:
                self._armed = True

    def _handle_capture(self, msg, vk):
        if msg in (WM_KEYDOWN, WM_SYSKEYDOWN):
            if vk == VK_ESCAPE:
                cb, self._capture_cb = self._capture_cb, None
                cb(None)
                return
            if vk in VK_TO_NAME:
                self._cap_down.add(vk)
                self._cap_peak.add(vk)
        elif msg in (WM_KEYUP, WM_SYSKEYUP):
            self._cap_down.discard(vk)
            if not self._cap_down and self._cap_peak:
                cb, self._capture_cb = self._capture_cb, None
                cb(normalize_capture(self._cap_peak))

    def _low_level_proc(self, n_code, w_param, l_param):
        if n_code >= 0:
            kb = ctypes.cast(l_param, ctypes.POINTER(_KBDLLHOOKSTRUCT)).contents
            try:
                self._handle(w_param, kb.vkCode, bool(kb.flags & LLKHF_INJECTED))
            except Exception:
                log.exception("Ошибка в обработчике hotkey")
        return _user32.CallNextHookEx(None, n_code, w_param, l_param)

    def run(self):
        """Блокирующий цикл; запускать в отдельном потоке."""
        self._thread_id = _kernel32.GetCurrentThreadId()
        self._hook = _user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._proc, None, 0)
        if not self._hook:
            raise OSError("SetWindowsHookExW failed")
        msg = wintypes.MSG()
        while _user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            _user32.TranslateMessage(ctypes.byref(msg))
            _user32.DispatchMessageW(ctypes.byref(msg))
        _user32.UnhookWindowsHookEx(self._hook)
        self._hook = None

    def stop(self):
        if self._thread_id:
            _user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
