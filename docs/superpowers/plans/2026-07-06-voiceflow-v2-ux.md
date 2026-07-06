# VoiceFlow V2 UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hotkey-комбинации с захватом нажатием, окно настроек из трея, оверлей на PNG-картинках, звуки записи, автозапуск — поверх работающего v1.

**Architecture:** Потоковая модель v1 не меняется (tk — главный поток, хук — свой, распознавание — worker, pystray — detached). `hotkey.py` переписывается на множества клавиш; появляются `settings.py` (Toplevel-окно), `autostart.py` (winreg), `sounds.py` (winsound); `overlay.py` учится показывать PNG и открывать настройки через свою очередь.

**Tech Stack:** как v1 (Python 3.13 venv, tkinter/ttk, pystray, Pillow, sounddevice) + stdlib `winreg`, `winsound`, `wave`.

## Global Constraints

- Спека: `docs/superpowers/specs/2026-07-06-voiceflow-v2-ux-design.md` — все точные значения оттуда.
- Конфиг `hotkey` — список имён клавиш, дефолт `["ctrl_left"]`; миграция строк v1: `"left_ctrl"`→`["ctrl_left"]`, `"right_ctrl"`→`["ctrl_right"]`, прочие строки → `["ctrl_right"]` с warning.
- Новый ключ `sounds: true`.
- Комбо: все клавиши зажаты → on_press; любая отпущена → on_release; повторный on_press только после полного отпускания; инжектированные события (LLKHF_INJECTED = 0x10) игнорируются полностью.
- Захват: пиковое множество зажатых; Esc — отмена (`callback(None)`); неизвестные клавиши игнорируются.
- Оверлей: `voiceflow/assets/recording.png|transcribing.png` 400×128, ключевой цвет `#ff00fe`, масштаб = DPI/192, откат на текстовый вид при отсутствии файлов.
- Звуки: `assets/start.wav|stop.wav`, winsound `SND_FILENAME | SND_ASYNC`, отсутствие файлов — warning один раз, без падения.
- Автозапуск: значение `VoiceFlow` в `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`.
- Пресеты качества: `large-v3` / `small` / `base` (точные подписи — в коде Task 6).
- Все команды — Git Bash из `F:/voiceflow`; тесты `.venv/Scripts/python -m pytest`; сейчас 32 passed.
- Коммиты с трейлером `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`; PowerShell-инструмент на машине сломан — только Bash.
- Работающий экземпляр VoiceFlow не перезапускать из задач — это сделает контроллер после финального ревью.

## File Structure

```
voiceflow/
├── config.py       # Task 1 (modify): hotkey-список+миграция, sounds, save_config
├── hotkey.py       # Task 2 (rewrite): таблица VK, комбо, injected-фильтр, захват
├── sounds.py       # Task 3 (create): Sounds.play_start/play_stop
├── autostart.py    # Task 4 (create): is_enabled/enable/disable
├── overlay.py      # Task 5 (modify): PNG+DPI+transparentcolor, канал settings
├── settings.py     # Task 6 (create): SettingsWindow + чистые хелперы
├── controller.py   # Task 7 (modify): звуки, set_device, guard перезагрузки модели
├── tray.py         # Task 8 (modify): пункт «Настройки…»
├── app.py          # Task 8 (modify): wiring, apply_settings, фоновый reload
└── assets/         # Task 3: start.wav, stop.wav; recording.png, transcribing.png (плейсхолдеры)
scripts/gen_assets.py  # Task 3 (create): генерация wav и png-плейсхолдеров
tests/test_config.py      # Task 1 (modify)
tests/test_hotkey.py      # Task 2 (rewrite)
tests/test_sounds.py      # Task 3 (create)
tests/test_autostart.py   # Task 4 (create)
tests/test_settings.py    # Task 6 (create)
tests/test_controller.py  # Task 7 (modify)
```

---

### Task 1: config.py — hotkey-список, миграция, sounds, save_config

**Files:**
- Modify: `voiceflow/config.py` (текущий: DEFAULTS c `"hotkey": "right_ctrl"`, `load_config` с try/except на битый JSON)
- Test: `tests/test_config.py` (сейчас 4 теста — не трогать, добавить новые)

**Interfaces:**
- Produces: `DEFAULTS["hotkey"] == ["ctrl_left"]`, `DEFAULTS["sounds"] is True`; `load_config(path) -> dict` мигрирует строковый hotkey в список; `save_config(path, cfg) -> None` пишет JSON (utf-8, ensure_ascii=False, indent=2).

- [ ] **Step 1: Написать падающие тесты** (добавить в конец `tests/test_config.py`)

```python
from voiceflow.config import save_config


def test_defaults_have_v2_keys():
    assert DEFAULTS["hotkey"] == ["ctrl_left"]
    assert DEFAULTS["sounds"] is True


def test_hotkey_v1_strings_migrate(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"hotkey": "left_ctrl"}), encoding="utf-8")
    assert load_config(p)["hotkey"] == ["ctrl_left"]
    p.write_text(json.dumps({"hotkey": "right_ctrl"}), encoding="utf-8")
    assert load_config(p)["hotkey"] == ["ctrl_right"]
    p.write_text(json.dumps({"hotkey": "weird"}), encoding="utf-8")
    assert load_config(p)["hotkey"] == ["ctrl_right"]


def test_hotkey_list_passes_through(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"hotkey": ["ctrl_left", "alt_left", "x"]}), encoding="utf-8")
    assert load_config(p)["hotkey"] == ["ctrl_left", "alt_left", "x"]


def test_hotkey_garbage_falls_back_to_default(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"hotkey": [1, 2]}), encoding="utf-8")
    assert load_config(p)["hotkey"] == DEFAULTS["hotkey"]
    p.write_text(json.dumps({"hotkey": []}), encoding="utf-8")
    assert load_config(p)["hotkey"] == DEFAULTS["hotkey"]


def test_save_config_round_trip(tmp_path):
    p = tmp_path / "config.json"
    cfg = load_config(p)
    cfg["hotkey"] = ["f9"]
    cfg["sounds"] = False
    save_config(p, cfg)
    loaded = load_config(p)
    assert loaded["hotkey"] == ["f9"]
    assert loaded["sounds"] is False
```

- [ ] **Step 2: Убедиться, что падают**

Run: `.venv/Scripts/python -m pytest tests/test_config.py -v`
Expected: FAIL — `ImportError: cannot import name 'save_config'`

- [ ] **Step 3: Реализация** — заменить содержимое `voiceflow/config.py` на:

```python
import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

DEFAULTS = {
    "model": "large-v3",
    "device": "auto",           # auto | cuda | cpu
    "compute_type": "int8_float16",
    "language": "auto",         # auto | ru | en
    "hotkey": ["ctrl_left"],    # список имён клавиш (см. hotkey.VK_NAMES)
    "sounds": True,
    "min_duration_sec": 0.3,
    "paste_mode": "auto",       # auto (консоль → печать, иначе Ctrl+V) | clipboard | type
    "input_device": None,       # имя/индекс устройства sounddevice; None = системное
    "samplerate": 16000,
}

_HOTKEY_V1 = {"left_ctrl": ["ctrl_left"], "right_ctrl": ["ctrl_right"]}


def _migrate_hotkey(value):
    if isinstance(value, str):
        migrated = _HOTKEY_V1.get(value)
        if migrated is None:
            log.warning("Неизвестный hotkey %r из конфига v1, использую ctrl_right", value)
            return ["ctrl_right"]
        return list(migrated)
    if isinstance(value, list) and value and all(isinstance(x, str) for x in value):
        return value
    log.warning("Некорректный hotkey %r, использую значение по умолчанию", value)
    return list(DEFAULTS["hotkey"])


def load_config(path):
    path = Path(path)
    cfg = dict(DEFAULTS)
    if not path.exists():
        return cfg
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        log.warning("config.json повреждён, использую настройки по умолчанию", exc_info=True)
        return cfg
    if not isinstance(data, dict):
        log.warning("config.json не является объектом, использую настройки по умолчанию")
        return cfg
    cfg.update({k: v for k, v in data.items() if k in DEFAULTS})
    cfg["hotkey"] = _migrate_hotkey(cfg["hotkey"])
    return cfg


def save_config(path, cfg):
    Path(path).write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8"
    )
```

(Заодно закрывается nano-находка финального ревью v1: `config.json` с не-dict содержимым больше не роняет загрузку.)

- [ ] **Step 4: Тесты зелёные**

Run: `.venv/Scripts/python -m pytest tests/test_config.py -v`
Expected: 9 passed

- [ ] **Step 5: Полный прогон** — `.venv/Scripts/python -m pytest` → 37 passed (app.py пока использует старый `resolve_hotkey`; тесты его не гоняют)

- [ ] **Step 6: Commit** — `git add voiceflow/config.py tests/test_config.py && git commit -m "feat: hotkey combo config with v1 migration, sounds key, save_config"`

---

### Task 2: hotkey.py — таблица VK, комбинации, injected-фильтр, захват

**Files:**
- Modify: `voiceflow/hotkey.py` (константы и прототипы WinAPI строк 1–72 сохранить как есть; удалить `HOTKEY_VKS`/`resolve_hotkey`; класс переписать)
- Test: `tests/test_hotkey.py` (переписать целиком)

**Interfaces:**
- Consumes: config `hotkey: list[str]` (Task 1).
- Produces:
  - `VK_NAMES: dict[str, int]`, `VK_TO_NAME: dict[int, str]`, `MODIFIER_NAMES: set[str]`, `VK_ESCAPE = 0x1B`;
  - `names_to_vks(names: list[str]) -> list[int]` — ValueError при неизвестном имени;
  - `human_label(names: list[str]) -> str` — «Ctrl слева + Alt слева + X»;
  - `normalize_capture(vks: set[int]) -> list[str]` — модификаторы сначала, внутри групп по VK;
  - `HotkeyListener(on_press, on_release, combo: list[int])` с `run()`, `stop()`, `set_combo(vks: list[int])`, `start_capture(callback)`;
  - внутренний `_handle(msg: int, vk: int, injected: bool = False)` — чистая тестируемая логика.
- ВАЖНО: `app.py` в v1 импортирует `resolve_hotkey` — в этой задаче заменить в `app.py` ровно две строки (см. Step 5), иначе приложение не стартует. Полный wiring — Task 8.

- [ ] **Step 1: Переписать тесты** — заменить содержимое `tests/test_hotkey.py` на:

```python
import pytest

from voiceflow.hotkey import (
    WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP,
    VK_ESCAPE, VK_NAMES, HotkeyListener,
    human_label, names_to_vks, normalize_capture,
)

CTRL_L = VK_NAMES["ctrl_left"]
ALT_L = VK_NAMES["alt_left"]
X = VK_NAMES["x"]


def _make(combo=("ctrl_left", "alt_left", "x")):
    events = []
    hl = HotkeyListener(
        on_press=lambda: events.append("press"),
        on_release=lambda: events.append("release"),
        combo=names_to_vks(list(combo)),
    )
    return hl, events


def test_names_to_vks_and_unknown():
    assert names_to_vks(["ctrl_left", "x"]) == [0xA2, 0x58]
    with pytest.raises(ValueError):
        names_to_vks(["nosuchkey"])


def test_human_label():
    assert human_label(["ctrl_left", "alt_left", "x"]) == "Ctrl слева + Alt слева + X"


def test_combo_fires_when_all_down_releases_on_any_up():
    hl, events = _make()
    hl._handle(WM_KEYDOWN, CTRL_L)
    hl._handle(WM_KEYDOWN, ALT_L)
    assert events == []
    hl._handle(WM_KEYDOWN, X)
    assert events == ["press"]
    hl._handle(WM_KEYUP, ALT_L)
    assert events == ["press", "release"]


def test_no_refire_until_full_release():
    hl, events = _make()
    for vk in (CTRL_L, ALT_L, X):
        hl._handle(WM_KEYDOWN, vk)
    hl._handle(WM_KEYUP, X)
    hl._handle(WM_KEYDOWN, X)  # дожатие без полного отпускания
    assert events == ["press", "release"]
    hl._handle(WM_KEYUP, CTRL_L)
    hl._handle(WM_KEYUP, ALT_L)
    for vk in (CTRL_L, ALT_L, X):
        hl._handle(WM_KEYDOWN, vk)
    assert events == ["press", "release", "press"]


def test_autorepeat_suppressed():
    hl, events = _make(combo=("ctrl_right",))
    vk = VK_NAMES["ctrl_right"]
    for _ in range(5):
        hl._handle(WM_KEYDOWN, vk)
    hl._handle(WM_KEYUP, vk)
    assert events == ["press", "release"]


def test_sys_messages_and_other_keys():
    hl, events = _make(combo=("alt_left",))
    hl._handle(WM_KEYDOWN, 0x41)  # 'A' — не из комбо
    hl._handle(WM_SYSKEYDOWN, ALT_L)
    hl._handle(WM_SYSKEYUP, ALT_L)
    assert events == ["press", "release"]


def test_injected_events_ignored():
    hl, events = _make(combo=("ctrl_left",))
    hl._handle(WM_KEYDOWN, CTRL_L, injected=True)
    hl._handle(WM_KEYUP, CTRL_L, injected=True)
    assert events == []


def test_set_combo_releases_active_recording():
    hl, events = _make(combo=("ctrl_left",))
    hl._handle(WM_KEYDOWN, CTRL_L)
    hl.set_combo([X])
    assert events == ["press", "release"]
    hl._handle(WM_KEYDOWN, X)
    assert events == ["press", "release", "press"]


def test_capture_collects_names_modifiers_first():
    hl, events = _make()
    captured = []
    hl.start_capture(captured.append)
    hl._handle(WM_KEYDOWN, X)       # порядок нажатия не важен
    hl._handle(WM_KEYDOWN, CTRL_L)
    hl._handle(WM_KEYDOWN, ALT_L)
    hl._handle(WM_KEYUP, X)
    hl._handle(WM_KEYUP, CTRL_L)
    assert captured == []           # ещё не всё отпущено
    hl._handle(WM_KEYUP, ALT_L)
    assert captured == [["ctrl_left", "alt_left", "x"]]
    assert events == []             # диктовка в захвате не дёргается


def test_capture_escape_cancels():
    hl, _ = _make()
    captured = []
    hl.start_capture(captured.append)
    hl._handle(WM_KEYDOWN, CTRL_L)
    hl._handle(WM_KEYDOWN, VK_ESCAPE)
    assert captured == [None]
    # после отмены обычная работа восстановлена
    hl._handle(WM_KEYUP, CTRL_L)


def test_capture_ignores_unknown_keys():
    hl, _ = _make()
    captured = []
    hl.start_capture(captured.append)
    hl._handle(WM_KEYDOWN, 0xFF)    # нет в таблице
    hl._handle(WM_KEYDOWN, X)
    hl._handle(WM_KEYUP, 0xFF)
    hl._handle(WM_KEYUP, X)
    assert captured == [["x"]]


def test_normalize_capture_orders_by_vk_within_groups():
    assert normalize_capture({VK_NAMES["x"], VK_NAMES["alt_left"], VK_NAMES["ctrl_right"]}) == [
        "ctrl_right", "alt_left", "x"
    ]
```

- [ ] **Step 2: Убедиться, что падают** — `.venv/Scripts/python -m pytest tests/test_hotkey.py -v` → FAIL `ImportError` (нет `names_to_vks` и т.д.)

- [ ] **Step 3: Реализация.** В `voiceflow/hotkey.py`: строки с константами сообщений, `LRESULT`, прототипами WinAPI и `_KBDLLHOOKSTRUCT` оставить без изменений. Удалить `HOTKEY_VKS` и `resolve_hotkey`. После строки `VK_LCONTROL = 0xA2` добавить таблицы, заменить класс:

```python
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
```

Класс `HotkeyListener` заменить на:

```python
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
        self._armed = True

    def start_capture(self, callback):
        """Копит зажатые клавиши; все отпущены → callback(имена), Esc → callback(None)."""
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
                self._active = True
                self._on_press()
        elif msg in (WM_KEYUP, WM_SYSKEYUP):
            self._down.discard(vk)
            if self._active:
                self._active = False
                self._on_release()
            if not self._down:
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
```

- [ ] **Step 4: Тесты зелёные** — `.venv/Scripts/python -m pytest tests/test_hotkey.py -v` → 12 passed

- [ ] **Step 5: Починить app.py (минимально).** В `voiceflow/app.py` заменить строки

```python
        from voiceflow.hotkey import resolve_hotkey
        listener = HotkeyListener(
            on_press=controller.on_press,
            on_release=controller.on_release,
            vk=resolve_hotkey(cfg["hotkey"]),
        )
```

на

```python
        from voiceflow.hotkey import VK_LCONTROL, names_to_vks
        try:
            combo = names_to_vks(cfg["hotkey"])
        except ValueError:
            log.warning("Некорректный hotkey %r, использую ctrl_left", cfg["hotkey"])
            combo = [VK_LCONTROL]
        listener = HotkeyListener(
            on_press=controller.on_press,
            on_release=controller.on_release,
            combo=combo,
        )
```

и строку `key_name = "левый Ctrl" if cfg["hotkey"] == "left_ctrl" else "правый Ctrl"` на

```python
        from voiceflow.hotkey import human_label
        key_name = human_label(cfg["hotkey"])
```

- [ ] **Step 6: Полный прогон** — `.venv/Scripts/python -m pytest` → 43 passed

- [ ] **Step 7: Commit** — `git add voiceflow/hotkey.py voiceflow/app.py tests/test_hotkey.py && git commit -m "feat: hotkey combos with capture mode and injected-event filter"`

---

### Task 3: sounds.py + генерация ассетов (wav + png-плейсхолдеры)

**Files:**
- Create: `voiceflow/sounds.py`, `scripts/gen_assets.py`
- Create (сгенерировать скриптом и закоммитить): `voiceflow/assets/start.wav`, `voiceflow/assets/stop.wav`, `voiceflow/assets/recording.png`, `voiceflow/assets/transcribing.png`
- Test: `tests/test_sounds.py`

**Interfaces:**
- Produces: `class Sounds(enabled: bool = True)` c `play_start()`, `play_stop()`, `set_enabled(bool)`; `voiceflow/assets/` с 4 файлами. PNG-плейсхолдеры позже заменятся картинками пользователя из Gemini **с теми же именами** — код от этого не меняется.

- [ ] **Step 1: Написать падающий тест**

`tests/test_sounds.py`:
```python
import voiceflow.sounds as sounds_mod
from voiceflow.sounds import Sounds


def test_play_calls_winsound_async(monkeypatch, tmp_path):
    calls = []
    (tmp_path / "start.wav").write_bytes(b"RIFF")
    monkeypatch.setattr(sounds_mod, "ASSETS", tmp_path)
    monkeypatch.setattr(
        sounds_mod.winsound, "PlaySound", lambda name, flags: calls.append((name, flags))
    )
    s = Sounds(enabled=True)
    s.play_start()
    assert len(calls) == 1
    assert calls[0][0].endswith("start.wav")
    assert calls[0][1] == sounds_mod.winsound.SND_FILENAME | sounds_mod.winsound.SND_ASYNC


def test_disabled_plays_nothing(monkeypatch, tmp_path):
    calls = []
    (tmp_path / "start.wav").write_bytes(b"RIFF")
    monkeypatch.setattr(sounds_mod, "ASSETS", tmp_path)
    monkeypatch.setattr(sounds_mod.winsound, "PlaySound", lambda *a: calls.append(a))
    s = Sounds(enabled=False)
    s.play_start()
    s.play_stop()
    assert calls == []
    s.set_enabled(True)
    (tmp_path / "stop.wav").write_bytes(b"RIFF")
    s.play_stop()
    assert len(calls) == 1


def test_missing_file_warns_once_no_crash(monkeypatch, tmp_path, caplog):
    monkeypatch.setattr(sounds_mod, "ASSETS", tmp_path)  # пусто
    s = Sounds(enabled=True)
    with caplog.at_level("WARNING"):
        s.play_start()
        s.play_start()
    assert len([r for r in caplog.records if "start.wav" in r.message]) == 1
```

- [ ] **Step 2: Убедиться, что падает** — `.venv/Scripts/python -m pytest tests/test_sounds.py -v` → FAIL `ModuleNotFoundError`

- [ ] **Step 3: Реализация**

`voiceflow/sounds.py`:
```python
import logging
import winsound
from pathlib import Path

log = logging.getLogger(__name__)

ASSETS = Path(__file__).parent / "assets"


class Sounds:
    """Короткие сигналы начала/конца записи. Никогда не бросает исключений."""

    def __init__(self, enabled=True):
        self._enabled = enabled
        self._warned = set()

    def set_enabled(self, enabled):
        self._enabled = enabled

    def play_start(self):
        self._play("start.wav")

    def play_stop(self):
        self._play("stop.wav")

    def _play(self, name):
        if not self._enabled:
            return
        path = ASSETS / name
        if not path.is_file():
            if name not in self._warned:
                self._warned.add(name)
                log.warning("Звук %s не найден, сигнал пропущен", name)
            return
        try:
            winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC)
        except Exception:
            log.warning("Не удалось воспроизвести %s", name, exc_info=True)
```

- [ ] **Step 4: Тесты зелёные** — `.venv/Scripts/python -m pytest tests/test_sounds.py -v` → 3 passed

- [ ] **Step 5: Скрипт генерации ассетов**

`scripts/gen_assets.py`:
```python
"""Генерирует ассеты: start.wav/stop.wav (синус-тики) и PNG-плейсхолдеры оверлея.

PNG — временные заглушки; пользователь заменит их картинками из Gemini
(400x128, RGBA, те же имена). Запуск: .venv/Scripts/python scripts/gen_assets.py
"""
import math
import struct
import sys
import wave
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ASSETS = Path(__file__).resolve().parents[1] / "voiceflow" / "assets"
ASSETS.mkdir(exist_ok=True)


def make_wav(path, freq, ms=70, rate=22050, volume=0.35):
    n = int(rate * ms / 1000)
    frames = bytearray()
    for i in range(n):
        fade = min(1.0, (n - i) / (n * 0.4), i / (n * 0.1) if n else 1.0)
        val = int(32767 * volume * fade * math.sin(2 * math.pi * freq * i / rate))
        frames += struct.pack("<h", val)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(frames))
    print(f"wrote {path}")


def make_png(path, bg, icon, text):
    img = Image.new("RGBA", (400, 128), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, 399, 127), radius=64, fill=bg)
    if icon == "dot":
        d.ellipse((36, 44, 76, 84), fill="white")
    else:  # hourglass
        d.polygon([(40, 40), (72, 40), (56, 64), (40, 88), (72, 88), (56, 64)], fill="white")
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 40)
    except OSError:
        font = ImageFont.load_default()
    d.text((100, 64), text, fill="white", font=font, anchor="lm")
    img.save(path)
    print(f"wrote {path}")


make_wav(ASSETS / "start.wav", freq=880)
make_wav(ASSETS / "stop.wav", freq=523)
make_png(ASSETS / "recording.png", (192, 57, 43, 235), "dot", "Запись…")
make_png(ASSETS / "transcribing.png", (44, 62, 80, 235), "hourglass", "Распознаю…")
```

Run: `.venv/Scripts/python scripts/gen_assets.py`
Expected: 4 строки `wrote ...`, файлы появились в `voiceflow/assets/`.

- [ ] **Step 6: Полный прогон** — `.venv/Scripts/python -m pytest` → 46 passed

- [ ] **Step 7: Commit** — `git add voiceflow/sounds.py voiceflow/assets scripts/gen_assets.py tests/test_sounds.py && git commit -m "feat: recording sounds and generated overlay/sound assets"`

---

### Task 4: autostart.py — автозапуск через реестр

**Files:**
- Create: `voiceflow/autostart.py`
- Test: `tests/test_autostart.py`

**Interfaces:**
- Produces: `is_enabled() -> bool`, `enable(command: str) -> None`, `disable() -> None`. Ошибки реестра пробрасываются как `OSError` (вызывающий показывает уведомление). Команду задаёт вызывающий (v2 — путь к `voiceflow.bat`; спека B подставит exe).

- [ ] **Step 1: Написать падающий тест**

`tests/test_autostart.py`:
```python
import winreg

import voiceflow.autostart as autostart


class FakeKey:
    def __init__(self, store):
        self.store = store
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False


def _patch_registry(monkeypatch, store):
    key = FakeKey(store)
    monkeypatch.setattr(autostart.winreg, "OpenKey", lambda *a, **kw: key)
    monkeypatch.setattr(
        autostart.winreg, "SetValueEx",
        lambda k, name, res, typ, val: store.__setitem__(name, val),
    )
    def query(k, name):
        if name not in store:
            raise FileNotFoundError
        return store[name], winreg.REG_SZ
    monkeypatch.setattr(autostart.winreg, "QueryValueEx", query)
    def delete(k, name):
        if name not in store:
            raise FileNotFoundError
        del store[name]
    monkeypatch.setattr(autostart.winreg, "DeleteValue", delete)


def test_enable_disable_cycle(monkeypatch):
    store = {}
    _patch_registry(monkeypatch, store)
    assert autostart.is_enabled() is False
    autostart.enable(r"F:\voiceflow\voiceflow.bat")
    assert store["VoiceFlow"] == r"F:\voiceflow\voiceflow.bat"
    assert autostart.is_enabled() is True
    autostart.disable()
    assert "VoiceFlow" not in store
    assert autostart.is_enabled() is False


def test_disable_when_absent_is_noop(monkeypatch):
    _patch_registry(monkeypatch, {})
    autostart.disable()  # не должно бросить
```

- [ ] **Step 2: Убедиться, что падает** — `.venv/Scripts/python -m pytest tests/test_autostart.py -v` → FAIL `ModuleNotFoundError`

- [ ] **Step 3: Реализация**

`voiceflow/autostart.py`:
```python
import winreg

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_VALUE_NAME = "VoiceFlow"


def _open(access):
    return winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, access)


def is_enabled():
    with _open(winreg.KEY_READ) as key:
        try:
            winreg.QueryValueEx(key, _VALUE_NAME)
            return True
        except FileNotFoundError:
            return False


def enable(command):
    with _open(winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, _VALUE_NAME, 0, winreg.REG_SZ, command)


def disable():
    with _open(winreg.KEY_SET_VALUE) as key:
        try:
            winreg.DeleteValue(key, _VALUE_NAME)
        except FileNotFoundError:
            pass
```

- [ ] **Step 4: Тесты зелёные** — `.venv/Scripts/python -m pytest tests/test_autostart.py -v` → 2 passed; полный прогон → 48 passed

- [ ] **Step 5: Commit** — `git add voiceflow/autostart.py tests/test_autostart.py && git commit -m "feat: autostart via HKCU Run registry key"`

---

### Task 5: overlay.py — PNG-картинки, DPI, канал настроек

**Files:**
- Modify: `voiceflow/overlay.py` (полная замена, текущее содержимое — 88 строк, см. git)
- Modify: `scripts/try_overlay.py` — без изменений кода, но прогнать для проверки

**Interfaces:**
- Consumes: `voiceflow/assets/recording.png`, `transcribing.png` (Task 3).
- Produces (для Task 6 и 8): всё из v1 (`show_recording/show_transcribing/hide/schedule_quit/run`) плюс `open_settings()` (потокобезопасно), `set_settings_opener(fn)` (fn зовётся в tk-потоке), свойство `root` (tk.Tk — родитель для Toplevel настроек).

GUI-модуль: юнит-тестов нет (конвенция v1), проверка ручным скриптом.

- [ ] **Step 1: Реализация** — заменить содержимое `voiceflow/overlay.py` на:

```python
import ctypes
import ctypes.wintypes as wintypes
import logging
import queue
import tkinter as tk
from pathlib import Path

log = logging.getLogger(__name__)

GWL_EXSTYLE = -20
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080

KEY_COLOR = "#ff00fe"
ASSETS = Path(__file__).parent / "assets"
_IMAGE_FILES = {"recording": "recording.png", "transcribing": "transcribing.png"}
_BASE_SIZE = (400, 128)   # размер PNG; соответствует 192 DPI (200%)

_TEXT_STATES = {
    "recording": ("●  Запись…", "#c0392b"),
    "transcribing": ("⏳  Распознаю…", "#2c3e50"),
}


class Overlay:
    """Мини-окно поверх всех окон. Не забирает фокус (WS_EX_NOACTIVATE) —
    иначе вставка ушла бы в оверлей, а не в активное приложение."""

    def __init__(self):
        self._queue = queue.Queue()
        self._on_open_settings = None
        self._root = tk.Tk()
        self._root.withdraw()
        self._root.overrideredirect(True)
        self._root.attributes("-topmost", True)
        # Стиль WS_EX_NOACTIVATE должен стоять ДО первого показа окна,
        # иначе первый deiconify() украдёт фокус у активного приложения.
        self._root.update_idletasks()
        self._apply_no_activate()
        self._images = self._load_images()
        if self._images:
            self._root.configure(bg=KEY_COLOR)
            self._root.attributes("-transparentcolor", KEY_COLOR)
            self._label = tk.Label(self._root, bg=KEY_COLOR, bd=0)
            w, h = self._images["recording"].width(), self._images["recording"].height()
        else:
            self._root.attributes("-alpha", 0.92)
            self._label = tk.Label(
                self._root, text="", font=("Segoe UI", 12, "bold"),
                fg="white", bg="#c0392b", padx=18, pady=8,
            )
            w, h = 190, 44
        self._label.pack()
        sw = self._root.winfo_screenwidth()
        sh = self._root.winfo_screenheight()
        self._root.geometry(f"{w}x{h}+{(sw - w) // 2}+{sh - 140 - h + 44}")
        self._root.after(50, self._poll)

    @property
    def root(self):
        return self._root

    def _hwnd(self):
        user32 = ctypes.windll.user32
        user32.GetParent.argtypes = [wintypes.HWND]
        user32.GetParent.restype = wintypes.HWND
        return user32.GetParent(self._root.winfo_id()) or self._root.winfo_id()

    def _apply_no_activate(self):
        user32 = ctypes.windll.user32
        user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
        user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
        user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
        hwnd = self._hwnd()
        style = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
        user32.SetWindowLongPtrW(
            hwnd, GWL_EXSTYLE, style | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW
        )

    def _dpi(self):
        try:
            user32 = ctypes.windll.user32
            user32.GetDpiForWindow.argtypes = [wintypes.HWND]
            user32.GetDpiForWindow.restype = wintypes.UINT
            return user32.GetDpiForWindow(self._hwnd()) or 96
        except Exception:
            return 96

    def _load_images(self):
        """PNG → PhotoImage, скомпонованные на ключевой цвет; None при любой проблеме."""
        try:
            from PIL import Image, ImageTk
            scale = self._dpi() / 192
            size = (max(1, int(_BASE_SIZE[0] * scale)), max(1, int(_BASE_SIZE[1] * scale)))
            images = {}
            for state, fname in _IMAGE_FILES.items():
                path = ASSETS / fname
                if not path.is_file():
                    log.warning("Нет %s — оверлей в текстовом режиме", fname)
                    return None
                img = Image.open(path).convert("RGBA").resize(size, Image.LANCZOS)
                bg = Image.new("RGBA", size, KEY_COLOR)
                bg.alpha_composite(img)
                images[state] = ImageTk.PhotoImage(bg.convert("RGB"), master=self._root)
            return images
        except Exception:
            log.warning("Не удалось загрузить картинки оверлея", exc_info=True)
            return None

    def _poll(self):
        try:
            while True:
                state = self._queue.get_nowait()
                if state == "quit":
                    self._root.destroy()
                    return
                if state == "settings":
                    if self._on_open_settings is not None:
                        self._on_open_settings()
                elif state == "hide":
                    self._root.withdraw()
                elif self._images:
                    self._label.config(image=self._images[state])
                    self._root.deiconify()
                else:
                    text, bg = _TEXT_STATES[state]
                    self._label.config(text=text, bg=bg)
                    self._root.deiconify()
        except queue.Empty:
            pass
        self._root.after(50, self._poll)

    # --- потокобезопасный интерфейс (Controller, Tray) ---
    def show_recording(self):
        self._queue.put("recording")

    def show_transcribing(self):
        self._queue.put("transcribing")

    def hide(self):
        self._queue.put("hide")

    def open_settings(self):
        self._queue.put("settings")

    def set_settings_opener(self, fn):
        self._on_open_settings = fn

    def schedule_quit(self):
        self._queue.put("quit")

    def run(self):
        self._root.mainloop()
```

- [ ] **Step 2: Ручная проверка** — `.venv/Scripts/python scripts/try_overlay.py` (~30 c). Expected: печатает OK; на экране видны картинки-пилюли (плейсхолдеры из Task 3), а не текстовые надписи; фокус из активного окна не уходит.

- [ ] **Step 3: Проверка отката** — временно переименовать `voiceflow/assets/recording.png` → запустить `try_overlay.py` → текстовый вид v1, OK, в логе warning; вернуть файл на место.

- [ ] **Step 4: Полный прогон** — `.venv/Scripts/python -m pytest` → 48 passed

- [ ] **Step 5: Commit** — `git add voiceflow/overlay.py && git commit -m "feat: image overlay with DPI scaling and settings channel"`

---

### Task 6: settings.py — окно настроек

**Files:**
- Create: `voiceflow/settings.py`
- Test: `tests/test_settings.py` (только чистые хелперы; GUI — вручную в Task 8)

**Interfaces:**
- Consumes: `hotkey.human_label/names_to_vks/HotkeyListener.start_capture` (Task 2), `autostart.is_enabled` (Task 4), `sounddevice.query_devices`.
- Produces: `SettingsWindow(root, cfg, listener, on_save)` где `on_save(new_cfg: dict, autostart_on: bool)` зовётся в tk-потоке по кнопке «Сохранить»; методы `alive() -> bool`, `lift_window()`. Хелперы: `dedupe_input_devices(devices) -> list[str]`, `quality_index_for_model(model) -> int`, `language_index(code) -> int`, константы `QUALITY_PRESETS`, `LANGUAGES`.

- [ ] **Step 1: Написать падающий тест**

`tests/test_settings.py`:
```python
from voiceflow.settings import (
    LANGUAGES, QUALITY_PRESETS,
    dedupe_input_devices, language_index, quality_index_for_model,
)


def test_quality_presets_models():
    assert [m for _, m in QUALITY_PRESETS] == ["large-v3", "small", "base"]


def test_quality_index_for_model():
    assert quality_index_for_model("small") == 1
    assert quality_index_for_model("no-such") == 0


def test_language_index():
    assert [c for _, c in LANGUAGES] == ["auto", "ru", "en"]
    assert language_index("ru") == 1
    assert language_index("xx") == 0


def test_dedupe_input_devices():
    devices = [
        {"name": "Mic A", "max_input_channels": 2},
        {"name": "Speakers", "max_input_channels": 0},
        {"name": "Mic A", "max_input_channels": 2},   # дубль из другого hostapi
        {"name": "Mic B", "max_input_channels": 1},
    ]
    assert dedupe_input_devices(devices) == ["Mic A", "Mic B"]
```

- [ ] **Step 2: Убедиться, что падает** — `.venv/Scripts/python -m pytest tests/test_settings.py -v` → FAIL `ModuleNotFoundError`

- [ ] **Step 3: Реализация**

`voiceflow/settings.py`:
```python
import logging
import tkinter as tk
from tkinter import ttk

import sounddevice as sd

from voiceflow import autostart
from voiceflow import hotkey as hk

log = logging.getLogger(__name__)

QUALITY_PRESETS = [
    ("Максимальное — large-v3 (нужна NVIDIA, ~3 ГБ)", "large-v3"),
    ("Среднее — small (~500 МБ)", "small"),
    ("Быстрое — base (~150 МБ)", "base"),
]
LANGUAGES = [("Авто", "auto"), ("Русский", "ru"), ("English", "en")]
_DEFAULT_DEVICE_LABEL = "Системный по умолчанию"


def quality_index_for_model(model):
    for i, (_label, m) in enumerate(QUALITY_PRESETS):
        if m == model:
            return i
    return 0


def language_index(code):
    for i, (_label, c) in enumerate(LANGUAGES):
        if c == code:
            return i
    return 0


def dedupe_input_devices(devices):
    seen, out = set(), []
    for d in devices:
        if d.get("max_input_channels", 0) <= 0:
            continue
        name = d["name"]
        if name not in seen:
            seen.add(name)
            out.append(name)
    return out


class SettingsWindow:
    """Окно настроек. Создавать и использовать только в tk-потоке."""

    def __init__(self, root, cfg, listener, on_save):
        self._cfg = dict(cfg)
        self._listener = listener
        self._on_save = on_save
        self._hotkey_names = list(cfg["hotkey"])
        self._capture_result = "idle"

        win = self._win = tk.Toplevel(root)
        win.title("VoiceFlow — настройки")
        win.resizable(False, False)
        win.attributes("-topmost", True)
        frm = ttk.Frame(win, padding=16)
        frm.grid()
        frm.columnconfigure(1, minsize=280)

        ttk.Label(frm, text="Клавиша диктовки:").grid(row=0, column=0, sticky="w", pady=4)
        self._hotkey_var = tk.StringVar(value=hk.human_label(self._hotkey_names))
        ttk.Label(frm, textvariable=self._hotkey_var).grid(row=0, column=1, sticky="w")
        self._hotkey_btn = ttk.Button(frm, text="Изменить", command=self._change_hotkey)
        self._hotkey_btn.grid(row=0, column=2, padx=(8, 0))

        ttk.Label(frm, text="Микрофон:").grid(row=1, column=0, sticky="w", pady=4)
        devices = [_DEFAULT_DEVICE_LABEL] + dedupe_input_devices(sd.query_devices())
        self._mic = ttk.Combobox(frm, values=devices, state="readonly", width=40)
        cur = cfg["input_device"]
        self._mic.current(devices.index(cur) if cur in devices else 0)
        self._mic.grid(row=1, column=1, columnspan=2, sticky="we")

        ttk.Label(frm, text="Язык:").grid(row=2, column=0, sticky="w", pady=4)
        self._lang = ttk.Combobox(
            frm, values=[label for label, _ in LANGUAGES], state="readonly"
        )
        self._lang.current(language_index(cfg["language"]))
        self._lang.grid(row=2, column=1, columnspan=2, sticky="we")

        ttk.Label(frm, text="Качество:").grid(row=3, column=0, sticky="w", pady=4)
        self._quality = ttk.Combobox(
            frm, values=[label for label, _ in QUALITY_PRESETS], state="readonly"
        )
        self._quality.current(quality_index_for_model(cfg["model"]))
        self._quality.grid(row=3, column=1, columnspan=2, sticky="we")

        self._sounds_var = tk.BooleanVar(value=bool(cfg["sounds"]))
        ttk.Checkbutton(frm, text="Звуки записи", variable=self._sounds_var).grid(
            row=4, column=0, columnspan=3, sticky="w", pady=4
        )

        try:
            autostart_now = autostart.is_enabled()
        except OSError:
            autostart_now = False
        self._autostart_var = tk.BooleanVar(value=autostart_now)
        ttk.Checkbutton(
            frm, text="Запускать вместе с Windows", variable=self._autostart_var
        ).grid(row=5, column=0, columnspan=3, sticky="w", pady=4)

        btns = ttk.Frame(frm)
        btns.grid(row=6, column=0, columnspan=3, pady=(12, 0))
        ttk.Button(btns, text="Сохранить", command=self._save).grid(row=0, column=0, padx=4)
        ttk.Button(btns, text="Отмена", command=self._win.destroy).grid(row=0, column=1, padx=4)

    # --- hotkey capture ---
    def _change_hotkey(self):
        self._hotkey_btn.config(state="disabled")
        self._hotkey_var.set("Нажмите комбинацию… (Esc — отмена)")
        self._capture_result = "wait"
        # колбэк придёт из потока хука — только записываем результат
        self._listener.start_capture(self._on_captured)
        self._win.after(100, self._poll_capture)

    def _on_captured(self, names):
        self._capture_result = names if names else "cancel"

    def _poll_capture(self):
        if not self.alive():
            return
        result = self._capture_result
        if result == "wait":
            self._win.after(100, self._poll_capture)
            return
        if isinstance(result, list):
            self._hotkey_names = result
        self._capture_result = "idle"
        self._hotkey_var.set(hk.human_label(self._hotkey_names))
        self._hotkey_btn.config(state="normal")

    # --- save ---
    def _save(self):
        cfg = dict(self._cfg)
        cfg["hotkey"] = list(self._hotkey_names)
        mic = self._mic.get()
        cfg["input_device"] = None if mic == _DEFAULT_DEVICE_LABEL else mic
        cfg["language"] = LANGUAGES[self._lang.current()][1]
        cfg["model"] = QUALITY_PRESETS[self._quality.current()][1]
        cfg["sounds"] = bool(self._sounds_var.get())
        self._on_save(cfg, bool(self._autostart_var.get()))
        self._win.destroy()

    def alive(self):
        try:
            return bool(self._win.winfo_exists())
        except tk.TclError:
            return False

    def lift_window(self):
        self._win.deiconify()
        self._win.lift()
```

- [ ] **Step 4: Тесты зелёные** — `.venv/Scripts/python -m pytest tests/test_settings.py -v` → 4 passed; полный прогон → 52 passed

- [ ] **Step 5: Commit** — `git add voiceflow/settings.py tests/test_settings.py && git commit -m "feat: settings window with hotkey capture"`

---

### Task 7: controller.py — звуки, set_device, guard перезагрузки модели

**Files:**
- Modify: `voiceflow/controller.py`
- Test: `tests/test_controller.py` (добавить тесты, существующие 8 не ломать; `_make` дополнить параметром sounds)

**Interfaces:**
- Consumes: `Sounds.play_start/play_stop` (Task 3, duck-typed).
- Produces: `Controller(..., sounds=None)`; `set_device(device) -> None`; `begin_model_reload() -> None` (on_press игнорируется); `finish_model_reload(transcriber=None) -> None` (None = откат на старый).

- [ ] **Step 1: Написать падающие тесты** (добавить в `tests/test_controller.py`; в `_make` добавить параметр и прокинуть `sounds=sounds` в конструктор, вернуть его последним элементом кортежа — обновить существующие распаковки добавлением `*_`):

```python
class FakeSounds:
    def __init__(self):
        self.events = []
    def play_start(self):
        self.events.append("start")
    def play_stop(self):
        self.events.append("stop")


def test_sounds_played_on_start_and_enqueue():
    sounds = FakeSounds()
    ctl, rec, tr, ui, inserted, notes, snd = _make(sounds=sounds)
    ctl.on_press()
    ctl.on_release()
    assert _wait_until(lambda: inserted)
    ctl.shutdown()
    assert snd.events == ["start", "stop"]


def test_short_recording_plays_no_stop_sound():
    sounds = FakeSounds()
    ctl, rec, tr, ui, inserted, notes, snd = _make(audio_sec=0.1, sounds=sounds)
    ctl.on_press()
    ctl.on_release()
    ctl.shutdown()
    assert snd.events == ["start"]


def test_model_reload_blocks_dictation_and_swaps_transcriber():
    ctl, rec, tr, ui, inserted, notes, _ = _make()
    ctl.begin_model_reload()
    ctl.on_press()
    ctl.on_release()
    assert rec.started == 0
    new_tr = FakeTranscriber(text="новая модель")
    ctl.finish_model_reload(new_tr)
    ctl.on_press()
    ctl.on_release()
    assert _wait_until(lambda: inserted)
    ctl.shutdown()
    assert inserted == [("новая модель", "clipboard")]


def test_model_reload_failure_keeps_old_transcriber():
    ctl, rec, tr, ui, inserted, notes, _ = _make(text="старая модель")
    ctl.begin_model_reload()
    ctl.finish_model_reload(None)   # загрузка не удалась — откат
    ctl.on_press()
    ctl.on_release()
    assert _wait_until(lambda: inserted)
    ctl.shutdown()
    assert inserted == [("старая модель", "clipboard")]


def test_set_device_applies_to_recorder():
    ctl, rec, tr, ui, inserted, notes, _ = _make()
    ctl.set_device("Mic B")
    ctl.shutdown()
    assert rec.device == "Mic B"
```

`FakeRecorder` дополнить атрибутом `self.device = None` в `__init__` (Controller.set_device присваивает `recorder.device`).

- [ ] **Step 2: Убедиться, что падают** — `.venv/Scripts/python -m pytest tests/test_controller.py -v` → FAIL (нет sounds/begin_model_reload)

- [ ] **Step 3: Реализация.** В `voiceflow/controller.py`:

Конструктор: добавить параметр `sounds=None` и поля:
```python
    def __init__(self, recorder, transcriber, insert_fn, ui, *,
                 min_duration_sec=0.3, samplerate=16000,
                 paste_mode="clipboard", notify=None, sounds=None):
        ...
        self._sounds = sounds
        self._reloading = False
```

`on_press`: условие пропуска — `if self._paused or self._recording or self._reloading:`; после `self._ui.show_recording()` добавить:
```python
            if self._sounds is not None:
                self._sounds.play_start()
```

`on_release`: после `self._jobs.put(audio)` добавить:
```python
        if self._sounds is not None:
            self._sounds.play_stop()
```

Новые методы (после `toggle_pause`):
```python
    def set_device(self, device):
        self._recorder.device = device

    def begin_model_reload(self):
        with self._lock:
            self._reloading = True

    def finish_model_reload(self, transcriber=None):
        with self._lock:
            if transcriber is not None:
                self._transcriber = transcriber
            self._reloading = False
```

- [ ] **Step 4: Тесты зелёные** — `.venv/Scripts/python -m pytest tests/test_controller.py -v` → 13 passed; полный прогон → 57 passed

- [ ] **Step 5: Commit** — `git add voiceflow/controller.py tests/test_controller.py && git commit -m "feat: controller sounds, device switch and model-reload guard"`

---

### Task 8: tray + app wiring, README, e2e

**Files:**
- Modify: `voiceflow/tray.py` (пункт «Настройки…»), `voiceflow/app.py` (wiring), `README.md`

**Interfaces:**
- Consumes: всё из Task 1–7 (сигнатуры — в их блоках Produces).
- Produces: работающее приложение v2.

- [ ] **Step 1: tray.py** — конструктор и меню заменить на:

```python
    def __init__(self, on_toggle_pause, on_exit, on_settings=None):
        self._on_toggle_pause = on_toggle_pause
        self._on_exit = on_exit
        self._on_settings = on_settings or (lambda: None)
        self._paused = False
        self._icon = pystray.Icon(
            "VoiceFlow", _make_icon_image(), "VoiceFlow",
            menu=pystray.Menu(
                pystray.MenuItem("Настройки…", self._settings),
                pystray.MenuItem(
                    lambda item: "Возобновить" if self._paused else "Пауза",
                    self._toggle,
                ),
                pystray.MenuItem("Выход", self._exit),
            ),
        )

    def _settings(self, icon, item):
        self._on_settings()
```

- [ ] **Step 2: app.py** — заменить `main()` целиком на:

```python
def main():
    _setup_logging()
    log = logging.getLogger("voiceflow")
    try:
        log.info("Запуск VoiceFlow")

        from voiceflow.config import load_config, save_config
        cfg = load_config(ROOT / "config.json")

        # Тяжёлые импорты — после логирования, чтобы ошибки попали в лог.
        from voiceflow import autostart
        from voiceflow.controller import Controller
        from voiceflow.hotkey import (
            VK_LCONTROL, HotkeyListener, human_label, names_to_vks,
        )
        from voiceflow.overlay import Overlay
        from voiceflow.recorder import Recorder
        from voiceflow.settings import SettingsWindow
        from voiceflow.sounds import Sounds
        from voiceflow.transcriber import Transcriber
        from voiceflow.tray import Tray
        from voiceflow.typer import insert_text

        overlay = Overlay()
        sounds = Sounds(cfg["sounds"])

        # Коллбэки трея могут сработать до конца загрузки модели —
        # до присваивания controller/listener они должны быть безопасны.
        controller = None
        listener = None

        def shutdown():
            log.info("Завершение")
            if listener is not None:
                listener.stop()
            if controller is not None:
                controller.shutdown()
            tray.stop()
            overlay.schedule_quit()

        tray = Tray(
            on_toggle_pause=lambda: controller.toggle_pause() if controller is not None else False,
            on_exit=shutdown,
            on_settings=overlay.open_settings,
        )
        tray.start()
        tray.notify("Загружаю модель распознавания…")

        log.info("Загрузка модели %s (%s)", cfg["model"], cfg["device"])
        transcriber = Transcriber(cfg["model"], cfg["device"], cfg["compute_type"], cfg["language"])
        log.info("Модель загружена, устройство: %s", transcriber.device)

        recorder = Recorder(samplerate=cfg["samplerate"], device=cfg["input_device"])
        controller = Controller(
            recorder, transcriber, insert_text, overlay,
            min_duration_sec=cfg["min_duration_sec"],
            samplerate=cfg["samplerate"],
            paste_mode=cfg["paste_mode"],
            notify=tray.notify,
            sounds=sounds,
        )
        controller.start()

        def _combo_from_cfg():
            try:
                return names_to_vks(cfg["hotkey"])
            except ValueError:
                log.warning("Некорректный hotkey %r, использую ctrl_left", cfg["hotkey"])
                return [VK_LCONTROL]

        listener = HotkeyListener(
            on_press=controller.on_press,
            on_release=controller.on_release,
            combo=_combo_from_cfg(),
        )
        hotkey_thread = threading.Thread(target=listener.run, daemon=True)
        hotkey_thread.start()

        def _reload_model():
            try:
                new_tr = Transcriber(
                    cfg["model"], cfg["device"], cfg["compute_type"], cfg["language"]
                )
                controller.finish_model_reload(new_tr)
                log.info("Модель %s загружена, устройство: %s", cfg["model"], new_tr.device)
                tray.notify(f"Готов. Модель: {cfg['model']}")
            except Exception as exc:
                log.exception("Не удалось загрузить модель %s", cfg["model"])
                controller.finish_model_reload(None)
                tray.notify(f"Не удалось загрузить модель: {exc}. Работает прежняя.")

        def apply_settings(new_cfg, autostart_on):
            # вызывается в tk-потоке из SettingsWindow
            old_model = (cfg["model"], cfg["language"])
            cfg.update(new_cfg)
            save_config(ROOT / "config.json", cfg)
            listener.set_combo(_combo_from_cfg())
            sounds.set_enabled(cfg["sounds"])
            controller.set_device(cfg["input_device"])
            try:
                if autostart_on:
                    autostart.enable(str(ROOT / "voiceflow.bat"))
                else:
                    autostart.disable()
            except OSError as exc:
                log.exception("Автозапуск: ошибка реестра")
                tray.notify(f"Не удалось изменить автозапуск: {exc}")
            if (cfg["model"], cfg["language"]) != old_model:
                controller.begin_model_reload()
                tray.notify("Загружаю модель… Диктовка временно недоступна.")
                threading.Thread(target=_reload_model, daemon=True).start()
            log.info("Настройки применены: hotkey=%s", cfg["hotkey"])

        settings_ref = {"win": None}

        def open_settings_window():
            # вызывается в tk-потоке из Overlay._poll
            win = settings_ref["win"]
            if win is not None and win.alive():
                win.lift_window()
                return
            settings_ref["win"] = SettingsWindow(
                overlay.root, cfg, listener, apply_settings
            )

        overlay.set_settings_opener(open_settings_window)

        suffix = "" if transcriber.device == "cuda" else " (CPU — медленный режим!)"
        tray.notify(f"Готов. Зажмите {human_label(cfg['hotkey'])} и говорите{suffix}")
        overlay.run()  # блокирует главный поток до schedule_quit()
        log.info("Остановлен")
    except Exception:
        log.exception("Фатальная ошибка")
        raise
```

- [ ] **Step 3: README** — в таблице config.json заменить строку hotkey на
`| hotkey | ["ctrl_left"] | список клавиш (см. Настройки → Изменить); напр. ["ctrl_left","alt_left","x"] |`
и добавить строку `| sounds | true | звуковые сигналы начала/конца записи |`.
После раздела «Запуск» добавить раздел:

```markdown
## Настройки

Правый клик по иконке в трее → «Настройки…»: клавиша диктовки (кнопка
«Изменить» — нажмите новую комбинацию), микрофон, язык, качество модели,
звуки, автозапуск. Смена качества/языка перезагружает модель в фоне
(~5–30 с, диктовка в это время недоступна).
```

- [ ] **Step 4: Полный прогон** — `.venv/Scripts/python -m pytest` → 57 passed

- [ ] **Step 5: Бегло проверить старт (без перезапуска рабочего экземпляра!)** — только синтаксис/импорты: `.venv/Scripts/python -c "import voiceflow.app, voiceflow.settings, voiceflow.sounds, voiceflow.autostart"` → без ошибок.

- [ ] **Step 6: Commit** — `git add voiceflow/tray.py voiceflow/app.py README.md && git commit -m "feat: settings wiring, tray menu item and README for v2"`

- [ ] **Step 7: Ручной e2e-чек-лист** (выполняет пользователь после перезапуска приложения контроллером):

1. Трей → Настройки… → окно открывается; повторный клик поднимает то же окно.
2. «Изменить» → нажать Ctrl+Alt+X → подпись обновилась; Сохранить → диктовка работает только по Ctrl+Alt+X; короткие Ctrl+C не мигают оверлеем.
3. «Изменить» → Esc → комбинация не изменилась.
4. Оверлей показывает картинки-пилюли; фокус не крадёт; на 150% DPI размер пропорционален.
5. Звуки: тик при старте, так при остановке; чекбокс выключает.
6. Качество → «Быстрое (base)» → уведомление «Загружаю модель…» → «Готов»; диктовка работает (быстрее, менее точно); вернуть «Максимальное».
7. Автозапуск: включить → `reg query HKCU\Software\Microsoft\Windows\CurrentVersion\Run /v VoiceFlow` показывает путь; выключить → значения нет.
8. Ctrl+V-вставка при hotkey с Ctrl в составе не запускает запись (инжект-фильтр).
