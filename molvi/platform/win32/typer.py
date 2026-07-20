import ctypes
import logging
import time

import win32clipboard
import win32con

log = logging.getLogger(__name__)

PASTE_HINT = "Ctrl+V"

_user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32

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
    log.info("paste: старый буфер %s, кладу %d симв",
             "пуст/не-текст" if old is None else f"{len(old)} симв", len(text))
    _set_clipboard_text(text)
    _press_ctrl_v()
    log.info("paste: Ctrl+V отправлен")
    # Пауза, чтобы целевое приложение успело прочитать буфер до восстановления.
    time.sleep(restore_delay)
    if old is not None:
        _set_clipboard_text(old)
        log.info("paste: буфер восстановлен")


def copy_to_clipboard(text):
    """Явное копирование по просьбе пользователя (пункт трея) —
    без вставки и без восстановления прежнего буфера."""
    _set_clipboard_text(text)


def get_target():
    """Цель вставки — активное окно в момент отпускания хоткея."""
    return _user32.GetForegroundWindow() or None


def target_is_foreground(target):
    return target is not None and _user32.GetForegroundWindow() == target


def activate_target(target, settle_delay=0.15):
    """Вернуть фокус исходному окну; True — окно реально стало активным.

    SetForegroundWindow из фонового процесса Windows может молча
    проигнорировать (foreground lock) — цепляемся к потоку текущего
    активного окна через AttachThreadInput и проверяем результат,
    а не верим вызову. Пауза — чтобы окно успело принять фокус до Ctrl+V.
    """
    if target is None or not _user32.IsWindow(target):
        return False
    if _user32.GetForegroundWindow() == target:
        return True
    fg = _user32.GetForegroundWindow()
    our_tid = _kernel32.GetCurrentThreadId()
    fg_tid = _user32.GetWindowThreadProcessId(fg, None) if fg else 0
    attached = False
    try:
        if fg_tid and fg_tid != our_tid:
            attached = bool(_user32.AttachThreadInput(our_tid, fg_tid, True))
        _user32.SetForegroundWindow(target)
    finally:
        if attached:
            _user32.AttachThreadInput(our_tid, fg_tid, False)
    time.sleep(settle_delay)
    return _user32.GetForegroundWindow() == target


def _utf16_units(ch):
    """Символ → его UTF-16 code units: wScan в KEYEVENTF_UNICODE 16-битный,
    поэтому символы вне BMP (эмодзи) шлются суррогатной парой, а не обрезаются."""
    data = ch.encode("utf-16-le")
    return [int.from_bytes(data[i:i + 2], "little") for i in range(0, len(data), 2)]


def type_text_direct(text):
    for ch in text:
        if ch == "\n":
            _send_key(vk=VK_RETURN)
            _send_key(vk=VK_RETURN, flags=KEYEVENTF_KEYUP)
            continue
        for unit in _utf16_units(ch):
            _send_key(scan=unit, flags=KEYEVENTF_UNICODE)
            _send_key(scan=unit, flags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP)
        time.sleep(0.005)


def _foreground_is_console():
    """Классическая консоль (conhost) не превращает Ctrl+V во «вставить»,
    когда TUI-приложение включило сырой режим ввода — туда надо печатать."""
    hwnd = _user32.GetForegroundWindow()
    buf = ctypes.create_unicode_buffer(64)
    _user32.GetClassNameW(hwnd, buf, 64)
    return buf.value == "ConsoleWindowClass"


def insert_text(text, mode):
    if mode == "type" or (mode == "auto" and _foreground_is_console()):
        log.info("insert: печатаю посимвольно (%d симв)", len(text))
        try:
            type_text_direct(text)
        except Exception:
            # Печать сорвалась посреди текста — кладём его в буфер, чтобы
            # распознанное не пропало (paste-режим делает это сам).
            try:
                _set_clipboard_text(text)
            except Exception:
                log.exception("Не удалось положить текст в буфер обмена")
            raise
    else:
        paste_text(text)
