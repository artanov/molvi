"""Вставка текста на macOS: NSPasteboard + CGEventPost(Cmd+V) или посимвольно.

Свои события помечаются INJECT_MAGIC в kCGEventSourceUserData — hotkey-тап
их отфильтрует (иначе эмуляция Cmd+V дёргала бы PTT, содержащий Cmd).
CGEventPost требует разрешение Accessibility (System Settings → Privacy &
Security → Универсальный доступ).
"""
import logging
import time

import Quartz
from AppKit import NSPasteboard, NSPasteboardTypeString

from molvi.platform.darwin.hotkey import INJECT_MAGIC

log = logging.getLogger(__name__)

PASTE_HINT = "Cmd+V"

VK_V = 0x09       # kVK_ANSI_V
VK_RETURN = 0x24  # kVK_Return


def _get_clipboard_text():
    pb = NSPasteboard.generalPasteboard()
    return pb.stringForType_(NSPasteboardTypeString)  # None — не текст


def _set_clipboard_text(text):
    pb = NSPasteboard.generalPasteboard()
    pb.clearContents()
    if not pb.setString_forType_(text, NSPasteboardTypeString):
        raise OSError("NSPasteboard.setString_forType_ failed")


def _post(event):
    Quartz.CGEventSetIntegerValueField(
        event, Quartz.kCGEventSourceUserData, INJECT_MAGIC)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)


def _press_cmd_v():
    for down in (True, False):
        ev = Quartz.CGEventCreateKeyboardEvent(None, VK_V, down)
        # Флаг Cmd на самом событии — физическое нажатие Cmd не эмулируем.
        Quartz.CGEventSetFlags(ev, Quartz.kCGEventFlagMaskCommand)
        _post(ev)


def paste_text(text, restore_delay=0.3):
    old = _get_clipboard_text()
    log.info("paste: старый буфер %s, кладу %d симв",
             "пуст/не-текст" if old is None else f"{len(old)} симв", len(text))
    _set_clipboard_text(text)
    _press_cmd_v()
    log.info("paste: Cmd+V отправлен")
    # Пауза, чтобы целевое приложение успело прочитать буфер до восстановления.
    time.sleep(restore_delay)
    if old is not None:
        _set_clipboard_text(old)
        log.info("paste: буфер восстановлен")


def type_text_direct(text):
    for ch in text:
        if ch == "\n":
            for down in (True, False):
                _post(Quartz.CGEventCreateKeyboardEvent(None, VK_RETURN, down))
            continue
        # CGEventKeyboardSetUnicodeString принимает UTF-16 целиком —
        # суррогатный костыль из win-версии не нужен.
        units = len(ch.encode("utf-16-le")) // 2
        for down in (True, False):
            ev = Quartz.CGEventCreateKeyboardEvent(None, 0, down)
            Quartz.CGEventKeyboardSetUnicodeString(ev, units, ch)
            _post(ev)
        time.sleep(0.005)


def insert_text(text, mode):
    # В отличие от Windows, режим auto не различает консоль: терминалы мака
    # (Terminal, iTerm) сами превращают Cmd+V во «вставить».
    if mode == "type":
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
