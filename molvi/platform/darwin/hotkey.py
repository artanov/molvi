"""macOS-обвязка push-to-talk: Quartz Event Tap.

Имена клавиш — общие с Windows-версией (конфиг переносим между ОС): "win_*"
на маке означает Command, "alt_*" — Option. Коды — виртуальные keycodes
macOS (kVK_*, Events.h); автомату важно только их равенство.
"""
import logging

from molvi.hotkey import (  # noqa: F401 — реэкспорт платформенного интерфейса
    WM_KEYDOWN, WM_KEYUP,
    HotkeyListener as _HotkeyCore,
    KeyTable,
)
from molvi.hotkey import (
    human_label as _human_label,
    names_to_vks as _names_to_vks,
    normalize_capture as _normalize_capture,
)

log = logging.getLogger(__name__)

# kVK_ANSI_* и kVK_* из Carbon/HIToolbox Events.h
VK_NAMES = {
    "a": 0x00, "s": 0x01, "d": 0x02, "f": 0x03, "h": 0x04, "g": 0x05,
    "z": 0x06, "x": 0x07, "c": 0x08, "v": 0x09, "b": 0x0B, "q": 0x0C,
    "w": 0x0D, "e": 0x0E, "r": 0x0F, "y": 0x10, "t": 0x11,
    "1": 0x12, "2": 0x13, "3": 0x14, "4": 0x15, "6": 0x16, "5": 0x17,
    "9": 0x19, "7": 0x1A, "8": 0x1C, "0": 0x1D,
    "o": 0x1F, "u": 0x20, "i": 0x22, "p": 0x23, "l": 0x25, "j": 0x26,
    "k": 0x28, "n": 0x2D, "m": 0x2E,
    "tab": 0x30, "space": 0x31, "backquote": 0x32,
    # capslock намеренно нет: на маке это toggle (flagsChanged без отпускания),
    # push-to-talk из него не сделать.
    "win_right": 0x36, "win_left": 0x37, "shift_left": 0x38,
    "alt_left": 0x3A, "ctrl_left": 0x3B,
    "shift_right": 0x3C, "alt_right": 0x3D, "ctrl_right": 0x3E,
    "f1": 0x7A, "f2": 0x78, "f3": 0x63, "f4": 0x76, "f5": 0x60, "f6": 0x61,
    "f7": 0x62, "f8": 0x64, "f9": 0x65, "f10": 0x6D, "f11": 0x67, "f12": 0x6F,
    "f13": 0x69, "f14": 0x6B, "f15": 0x71, "f16": 0x6A, "f17": 0x40,
    "f18": 0x4F, "f19": 0x50, "f20": 0x5A,
    "left": 0x7B, "right": 0x7C, "down": 0x7D, "up": 0x7E,
    "home": 0x73, "end": 0x77, "pageup": 0x74, "pagedown": 0x79,
    "delete": 0x75,  # forward delete; клавиши Insert на маке нет
}
VK_TO_NAME = {v: k for k, v in VK_NAMES.items()}

MODIFIER_NAMES = {
    "ctrl_left", "ctrl_right", "shift_left", "shift_right",
    "alt_left", "alt_right", "win_left", "win_right",
}

_DISPLAY_RU = {
    "ctrl_left": "⌃ Control слева", "ctrl_right": "⌃ Control справа",
    "shift_left": "⇧ Shift слева", "shift_right": "⇧ Shift справа",
    "alt_left": "⌥ Option слева", "alt_right": "⌥ Option справа",
    "win_left": "⌘ Cmd слева", "win_right": "⌘ Cmd справа",
    "space": "Пробел", "tab": "Tab",
    "backquote": "`", "left": "←", "up": "↑", "right": "→", "down": "↓",
    "delete": "Delete", "home": "Home", "end": "End",
    "pageup": "PageUp", "pagedown": "PageDown",
}
_DISPLAY_EN = {
    "ctrl_left": "⌃ Left Control", "ctrl_right": "⌃ Right Control",
    "shift_left": "⇧ Left Shift", "shift_right": "⇧ Right Shift",
    "alt_left": "⌥ Left Option", "alt_right": "⌥ Right Option",
    "win_left": "⌘ Left Cmd", "win_right": "⌘ Right Cmd",
    "space": "Space", "tab": "Tab",
    "backquote": "`", "left": "←", "up": "↑", "right": "→", "down": "↓",
    "delete": "Delete", "home": "Home", "end": "End",
    "pageup": "PageUp", "pagedown": "PageDown",
}
_DISPLAY = {"ru": _DISPLAY_RU, "en": _DISPLAY_EN}

VK_ESCAPE = 0x35
TABLE = KeyTable(VK_NAMES, MODIFIER_NAMES, _DISPLAY, VK_ESCAPE)

# Правый Cmd: почти не используется соло, не конфликтует с системными
# сочетаниями и удобен под большой палец (см. docs/macos-port.md).
DEFAULT_HOTKEY = ["win_right"]


def names_to_vks(names):
    return _names_to_vks(names, TABLE)


def human_label(names):
    return _human_label(names, TABLE)


def normalize_capture(vks):
    return _normalize_capture(vks, TABLE)


# Метка собственных событий (kCGEventSourceUserData): наш CGEventPost(Cmd+V)
# не должен дёргать PTT — аналог фильтра LLKHF_INJECTED на Windows.
INJECT_MAGIC = 0x4D4F4C56  # "MOLV"

# Типы CGEvent (CGEventTypes.h) — числа, чтобы _on_event тестировался без Quartz.
_KEY_DOWN = 10        # kCGEventKeyDown
_KEY_UP = 11          # kCGEventKeyUp
_FLAGS_CHANGED = 12   # kCGEventFlagsChanged

# Модификаторы приходят как flagsChanged без направления; нажатие/отпускание
# восстанавливаем по device-битам флагов (IOKit NX_DEVICE*KEYMASK).
_DEVICE_MASKS = {
    0x3B: 0x0001,  # ctrl_left
    0x3E: 0x2000,  # ctrl_right
    0x38: 0x0002,  # shift_left
    0x3C: 0x0004,  # shift_right
    0x37: 0x0008,  # win_left (Cmd)
    0x36: 0x0010,  # win_right
    0x3A: 0x0020,  # alt_left (Option)
    0x3D: 0x0040,  # alt_right
}


class HotkeyListener(_HotkeyCore):
    def __init__(self, on_press, on_release, combo, on_esc=None):
        super().__init__(on_press, on_release, combo, table=TABLE, on_esc=on_esc)
        self._tap = None
        self._runloop = None

    def _on_event(self, type_, keycode, flags, user_data):
        """Событие CGEvent (уже распакованное) → автомат _handle().

        Автоповтор keyDown гасится автоматом (_armed); capslock/fn игнорируются
        (их нет в _DEVICE_MASKS: toggle-семантика не совместима с PTT)."""
        injected = user_data == INJECT_MAGIC
        if type_ == _FLAGS_CHANGED:
            mask = _DEVICE_MASKS.get(keycode)
            if mask is None:
                return
            msg = WM_KEYDOWN if flags & mask else WM_KEYUP
            self._handle(msg, keycode, injected)
        elif type_ == _KEY_DOWN:
            self._handle(WM_KEYDOWN, keycode, injected)
        elif type_ == _KEY_UP:
            self._handle(WM_KEYUP, keycode, injected)

    def run(self):
        """Блокирующий цикл event tap; запускать в отдельном потоке."""
        import Quartz

        def callback(proxy, type_, event, refcon):
            try:
                # macOS отключает «медленный» tap — молча включаем обратно,
                # иначе диктовка просто перестала бы работать навсегда.
                if type_ in (Quartz.kCGEventTapDisabledByTimeout,
                             Quartz.kCGEventTapDisabledByUserInput):
                    Quartz.CGEventTapEnable(self._tap, True)
                    return event
                self._on_event(
                    int(type_),
                    int(Quartz.CGEventGetIntegerValueField(
                        event, Quartz.kCGKeyboardEventKeycode)),
                    int(Quartz.CGEventGetFlags(event)),
                    int(Quartz.CGEventGetIntegerValueField(
                        event, Quartz.kCGEventSourceUserData)),
                )
            except Exception:
                log.exception("Ошибка в обработчике hotkey")
            return event

        self._callback = callback  # держим ссылку от GC
        mask = (Quartz.CGEventMaskBit(Quartz.kCGEventKeyDown)
                | Quartz.CGEventMaskBit(Quartz.kCGEventKeyUp)
                | Quartz.CGEventMaskBit(Quartz.kCGEventFlagsChanged))
        # ListenOnly: нам достаточно подслушивать (разрешение «Мониторинг
        # ввода»); активный tap потребовал бы ещё и Accessibility.
        self._tap = Quartz.CGEventTapCreate(
            Quartz.kCGSessionEventTap, Quartz.kCGHeadInsertEventTap,
            Quartz.kCGEventTapOptionListenOnly, mask, callback, None)
        if self._tap is None:
            raise OSError(
                "Не удалось создать event tap. Выдайте разрешение: System "
                "Settings → Privacy & Security → Input Monitoring → Molvi "
                "(или Терминал в dev-режиме) и перезапустите."
            )
        source = Quartz.CFMachPortCreateRunLoopSource(None, self._tap, 0)
        self._runloop = Quartz.CFRunLoopGetCurrent()
        Quartz.CFRunLoopAddSource(self._runloop, source,
                                  Quartz.kCFRunLoopCommonModes)
        Quartz.CGEventTapEnable(self._tap, True)
        Quartz.CFRunLoopRun()
        self._tap = None

    def stop(self):
        if self._runloop is not None:
            import Quartz
            Quartz.CFRunLoopStop(self._runloop)
