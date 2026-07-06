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

_HOOKPROC = ctypes.CFUNCTYPE(
    ctypes.c_longlong, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM
)


class _KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG)),
    ]


class HotkeyListener:
    def __init__(self, on_press, on_release, vk=VK_RCONTROL):
        self._on_press = on_press
        self._on_release = on_release
        self._vk = vk
        self._is_down = False
        self._hook = None
        self._thread_id = None
        self._proc = _HOOKPROC(self._low_level_proc)  # держим ссылку от GC

    def _handle(self, msg, vk):
        if vk != self._vk:
            return
        if msg in (WM_KEYDOWN, WM_SYSKEYDOWN):
            if not self._is_down:  # подавляем автоповтор Windows
                self._is_down = True
                self._on_press()
        elif msg in (WM_KEYUP, WM_SYSKEYUP):
            if self._is_down:
                self._is_down = False
                self._on_release()

    def _low_level_proc(self, n_code, w_param, l_param):
        if n_code >= 0:
            kb = ctypes.cast(l_param, ctypes.POINTER(_KBDLLHOOKSTRUCT)).contents
            try:
                self._handle(w_param, kb.vkCode)
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
