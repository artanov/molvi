import ctypes
import time

import win32clipboard
import win32con

_user32 = ctypes.windll.user32

VK_CONTROL = 0x11
VK_V = 0x56
VK_RETURN = 0x0D
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004


def _open_clipboard(retries=10, delay=0.05):
    """Буфер может быть занят другим процессом — пробуем несколько раз."""
    for _ in range(retries):
        try:
            win32clipboard.OpenClipboard()
            return
        except Exception:
            time.sleep(delay)
    win32clipboard.OpenClipboard()  # последняя попытка — пусть исключение всплывёт


def _get_clipboard_text():
    _open_clipboard()
    try:
        if win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
            return win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
        return None  # не текст (картинка/файлы) — восстановить не сможем
    finally:
        win32clipboard.CloseClipboard()


def _set_clipboard_text(text):
    _open_clipboard()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, text)
    finally:
        win32clipboard.CloseClipboard()


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.c_ushort),
        ("wScan", ctypes.c_ushort),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", ctypes.c_ulong),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class _HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", ctypes.c_ulong),
        ("wParamL", ctypes.c_ushort),
        ("wParamH", ctypes.c_ushort),
    ]


class _INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("ki", _KEYBDINPUT), ("mi", _MOUSEINPUT), ("hi", _HARDWAREINPUT)]
    _anonymous_ = ("u",)
    _fields_ = [("type", ctypes.c_ulong), ("u", _U)]


def _send_key(vk=0, scan=0, flags=0):
    inp = _INPUT(type=1)  # INPUT_KEYBOARD
    inp.ki = _KEYBDINPUT(vk, scan, flags, 0, None)
    if _user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(_INPUT)) != 1:
        raise OSError("SendInput failed")


def _press_ctrl_v():
    _send_key(vk=VK_CONTROL)
    _send_key(vk=VK_V)
    _send_key(vk=VK_V, flags=KEYEVENTF_KEYUP)
    _send_key(vk=VK_CONTROL, flags=KEYEVENTF_KEYUP)


def paste_text(text, restore_delay=0.3):
    old = _get_clipboard_text()
    _set_clipboard_text(text)
    _press_ctrl_v()
    # Пауза, чтобы целевое приложение успело прочитать буфер до восстановления.
    time.sleep(restore_delay)
    if old is not None:
        _set_clipboard_text(old)


def type_text_direct(text):
    for ch in text:
        if ch == "\n":
            _send_key(vk=VK_RETURN)
            _send_key(vk=VK_RETURN, flags=KEYEVENTF_KEYUP)
            continue
        code = ord(ch)
        _send_key(scan=code, flags=KEYEVENTF_UNICODE)
        _send_key(scan=code, flags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP)
        time.sleep(0.005)


def insert_text(text, mode):
    if mode == "type":
        type_text_direct(text)
    else:
        paste_text(text)
