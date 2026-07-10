"""Windows-обвязка push-to-talk: низкоуровневый хук клавиатуры (WinAPI).

Автомат комбинации — в molvi/hotkey.py; здесь только трансляция событий
WH_KEYBOARD_LL в _handle() и цикл сообщений run()/stop().
"""
import ctypes
import ctypes.wintypes as wintypes
import logging

from molvi.hotkey import (  # noqa: F401 — реэкспорт платформенного интерфейса
    MODIFIER_NAMES, TABLE, VK_ESCAPE, VK_LCONTROL, VK_NAMES, VK_RCONTROL,
    VK_TO_NAME, WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP,
    HotkeyListener as _HotkeyCore,
    human_label, names_to_vks, normalize_capture,
)

log = logging.getLogger(__name__)

_user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32

WH_KEYBOARD_LL = 13
WM_QUIT = 0x0012
LLKHF_INJECTED = 0x10

DEFAULT_HOTKEY = ["ctrl_left"]

LRESULT = ctypes.c_ssize_t  # LONG_PTR: pointer-width, not c_int

_HOOKPROC = ctypes.CFUNCTYPE(
    LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM
)

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


class HotkeyListener(_HotkeyCore):
    def __init__(self, on_press, on_release, combo):
        super().__init__(on_press, on_release, combo, table=TABLE)
        self._hook = None
        self._thread_id = None
        self._proc = _HOOKPROC(self._low_level_proc)  # держим ссылку от GC

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
