"""Ядро push-to-talk: конечный автомат комбинации клавиш, без системных API.

Платформенная обвязка (низкоуровневый хук WinAPI / event tap Quartz) живёт в
molvi/platform/*/hotkey.py и транслирует события ОС в вызовы
HotkeyListener._handle(). Константы WM_* исторически совпадают с кодами
сообщений Windows, но здесь это просто абстрактные коды «нажато/отпущено».

Коды клавиш (vk) — произвольные числа из таблицы KeyTable: у Windows свои,
у macOS свои; автомат сравнивает их только на равенство. Имена клавиш
("ctrl_left", "win_right", …) — общие для всех платформ и хранятся в конфиге.
"""
import logging
import threading

from molvi import i18n

log = logging.getLogger(__name__)

WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105
VK_RCONTROL = 0xA3
VK_LCONTROL = 0xA2

VK_ESCAPE = 0x1B

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

_DISPLAY_RU = {
    "ctrl_left": "Ctrl слева", "ctrl_right": "Ctrl справа",
    "shift_left": "Shift слева", "shift_right": "Shift справа",
    "alt_left": "Alt слева", "alt_right": "Alt справа",
    "win_left": "Win слева", "win_right": "Win справа",
    "space": "Пробел", "capslock": "CapsLock", "tab": "Tab",
    "backquote": "`", "left": "←", "up": "↑", "right": "→", "down": "↓",
    "insert": "Insert", "delete": "Delete", "home": "Home", "end": "End",
    "pageup": "PageUp", "pagedown": "PageDown",
}
_DISPLAY_EN = {
    "ctrl_left": "Left Ctrl", "ctrl_right": "Right Ctrl",
    "shift_left": "Left Shift", "shift_right": "Right Shift",
    "alt_left": "Left Alt", "alt_right": "Right Alt",
    "win_left": "Left Win", "win_right": "Right Win",
    "space": "Space", "capslock": "CapsLock", "tab": "Tab",
    "backquote": "`", "left": "←", "up": "↑", "right": "→", "down": "↓",
    "insert": "Insert", "delete": "Delete", "home": "Home", "end": "End",
    "pageup": "PageUp", "pagedown": "PageDown",
}
_DISPLAY = {"ru": _DISPLAY_RU, "en": _DISPLAY_EN}


class KeyTable:
    """Платформенный набор клавиш: имя↔vk, модификаторы, подписи, Esc."""

    def __init__(self, names, modifiers, display, escape_vk):
        self.names = names
        self.to_name = {v: k for k, v in names.items()}
        self.modifiers = modifiers
        # подписи по языкам {"ru": {...}, "en": {...}}
        self.display = display
        self.escape_vk = escape_vk


# Таблица Windows — исторический набор по умолчанию; тесты автомата гоняются
# на ней (автомату важно только равенство vk, не их платформенный смысл).
TABLE = KeyTable(VK_NAMES, MODIFIER_NAMES, _DISPLAY, VK_ESCAPE)


def names_to_vks(names, table=TABLE):
    vks = []
    for name in names:
        vk = table.names.get(name)
        if vk is None:
            raise ValueError(f"Неизвестное имя клавиши: {name!r}")
        vks.append(vk)
    return vks


def human_label(names, table=TABLE):
    labels = table.display.get(i18n.current_language(), {})
    return " + ".join(labels.get(n, n.upper()) for n in names)


def normalize_capture(vks, table=TABLE):
    names = [table.to_name[vk] for vk in vks if vk in table.to_name]
    mods = sorted((n for n in names if n in table.modifiers),
                  key=lambda n: table.names[n])
    rest = sorted((n for n in names if n not in table.modifiers),
                  key=lambda n: table.names[n])
    return mods + rest


class HotkeyListener:
    """Push-to-talk по комбинации клавиш.

    Все клавиши комбо зажаты → on_press; любая отпущена → on_release;
    повторный on_press — только после полного отпускания всех клавиш.
    Инжектированные события игнорируются: иначе собственная эмуляция
    Ctrl+V дёргала бы hotkey, содержащий Ctrl.

    run()/stop() — в платформенных подклассах (molvi/platform/*/hotkey.py).
    """

    def __init__(self, on_press, on_release, combo, table=TABLE, on_esc=None):
        self._on_press = on_press
        self._on_release = on_release
        self._on_esc = on_esc
        self._combo = frozenset(combo)
        self._table = table
        # Выставляется обвязкой, если run() умер (на маке — нет разрешения
        # Input Monitoring): UI по флагу не ждёт колбэков от мёртвого хука.
        self.dead = False
        self._down = set()
        self._released = set()
        self._active = False
        self._armed = True
        self._capture_cb = None
        self._cap_peak = set()
        self._cap_down = set()
        # set_combo/start_capture зовутся из tk-потока, _handle — из потока
        # хука; без лока сброс _active/_down может проскочить посреди
        # обработки нажатия и оставить запись включённой навсегда.
        self._lock = threading.Lock()

    def set_combo(self, vks):
        with self._lock:
            self._combo = frozenset(vks)
            self._down = set()
            self._released = set()
            self._armed = True
            was_active, self._active = self._active, False
        if was_active:
            self._on_release()

    def start_capture(self, callback):
        """Копит зажатые клавиши; все отпущены → callback(имена), Esc → callback(None)."""
        with self._lock:
            self._down = set()
            self._released = set()
            self._armed = True
            self._cap_peak = set()
            self._cap_down = set()
            self._capture_cb = callback
            was_active, self._active = self._active, False
        if was_active:
            self._on_release()

    def cancel_capture(self):
        """Прервать начатый start_capture, не дожидаясь клавиш (callback не зовётся)."""
        with self._lock:
            self._capture_cb = None

    def _handle(self, msg, vk, injected=False):
        if injected:
            return
        with self._lock:
            if self._capture_cb is not None:
                self._handle_capture(msg, vk)
                return
            if (self._on_esc is not None and vk == self._table.escape_vk
                    and msg in (WM_KEYDOWN, WM_SYSKEYDOWN)):
                # Esc-отмена вставки: репортим всегда, фильтрует по своему
                # состоянию Controller — хук не знает, идёт ли обработка.
                self._on_esc()
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
            if vk == self._table.escape_vk:
                cb, self._capture_cb = self._capture_cb, None
                cb(None)
                return
            if vk in self._table.to_name:
                self._cap_down.add(vk)
                self._cap_peak.add(vk)
        elif msg in (WM_KEYUP, WM_SYSKEYUP):
            self._cap_down.discard(vk)
            if not self._cap_down and self._cap_peak:
                cb, self._capture_cb = self._capture_cb, None
                cb(normalize_capture(self._cap_peak, self._table))
