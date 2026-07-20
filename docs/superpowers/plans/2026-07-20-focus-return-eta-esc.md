# «Свободные руки во время обработки» — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Во время распознавания можно переключать окна — текст вставится в исходное окно; на пилюле — счётчик остатка «~N с»; Esc отменяет вставку.

**Architecture:** Цель вставки (HWND / pid) снимается при отпускании хоткея и едет в очередь вместе с аудио; перед вставкой при смене фокуса `Controller` возвращает его через новые платформенные `activate_target()`. ETA — скользящее RTF-среднее в контроллере, отображение — счётчик на пилюле. Esc — колбэк `on_esc` в ядре `HotkeyListener` (Esc не глотается) → `Controller.cancel_pending()`.

**Tech Stack:** Python 3.13, ctypes/WinAPI (SetForegroundWindow + AttachThreadInput), AppKit (NSRunningApplication), tkinter, pytest.

Спека: `docs/superpowers/specs/2026-07-20-focus-return-eta-esc-design.md`.

## Global Constraints

- Комментарии в коде и сообщения коммитов — по-русски; комментарии объясняют «почему», не «что» (CLAUDE.md).
- Тесты: `.venv\Scripts\python -m pytest -q` (Windows) — все зелёные; darwin-тесты скипаются на Windows.
- Ключи i18n в RU и EN обязаны совпадать (существующий `test_ru_en_same_keys`).
- Никаких новых зависимостей.
- Esc НЕ глотается хуком; вставка «вслепую» в чужое окно запрещена (неудача активации → пропуск вставки, текст спасает трей).

---

### Task 1: on_esc в ядре HotkeyListener и платформенных обвязках

**Files:**
- Modify: `molvi/hotkey.py` (конструктор ~строка 127, `_handle` ~строка 175)
- Modify: `molvi/platform/win32/hotkey.py:71-72` (конструктор)
- Modify: `molvi/platform/darwin/hotkey.py:118-119` (конструктор)
- Test: `tests/test_hotkey.py` (дописать в конец)

**Interfaces:**
- Consumes: существующие `HotkeyListener`, `KeyTable.escape_vk` (Esc-код платформы уже в таблице: win 0x1B, mac 0x35).
- Produces: `HotkeyListener(on_press, on_release, combo, table=TABLE, on_esc=None)` — ядро; платформенные подклассы: `HotkeyListener(on_press, on_release, combo, on_esc=None)`. `on_esc: () -> None` зовётся на каждом keydown Esc вне режима захвата; событие не глотается.

- [ ] **Step 1: Написать падающие тесты**

В конец `tests/test_hotkey.py` (импорты `HotkeyListener`, `WM_KEYDOWN`, `WM_KEYUP` там уже есть — добавить `VK_ESCAPE` к существующей строке импорта из `molvi.hotkey`):

```python
def test_esc_keydown_calls_on_esc_once():
    events = []
    listener = HotkeyListener(lambda: None, lambda: None, [0xA2],
                              on_esc=lambda: events.append("esc"))
    listener._handle(WM_KEYDOWN, VK_ESCAPE)
    listener._handle(WM_KEYUP, VK_ESCAPE)   # keyup колбэк не дёргает
    assert events == ["esc"]


def test_esc_without_callback_is_noop():
    listener = HotkeyListener(lambda: None, lambda: None, [0xA2])
    listener._handle(WM_KEYDOWN, VK_ESCAPE)  # не бросает и не ломает автомат
    listener._handle(WM_KEYDOWN, 0xA2)
    listener._handle(WM_KEYUP, 0xA2)


def test_esc_during_capture_cancels_capture_not_on_esc():
    # Захват комбинации в настройках использует Esc как «отмена» —
    # приоритет у захвата, on_esc молчит.
    events, captured = [], []
    listener = HotkeyListener(lambda: None, lambda: None, [0xA2],
                              on_esc=lambda: events.append("esc"))
    listener.start_capture(captured.append)
    listener._handle(WM_KEYDOWN, VK_ESCAPE)
    assert captured == [None]
    assert events == []


def test_esc_injected_ignored():
    events = []
    listener = HotkeyListener(lambda: None, lambda: None, [0xA2],
                              on_esc=lambda: events.append("esc"))
    listener._handle(WM_KEYDOWN, VK_ESCAPE, injected=True)
    assert events == []
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `.venv\Scripts\python -m pytest tests/test_hotkey.py -q`
Expected: FAIL — `TypeError: ... unexpected keyword argument 'on_esc'`.

- [ ] **Step 3: Реализация**

`molvi/hotkey.py`, конструктор ядра:

```python
    def __init__(self, on_press, on_release, combo, table=TABLE, on_esc=None):
        self._on_press = on_press
        self._on_release = on_release
        self._on_esc = on_esc
```

(остальные строки конструктора без изменений). В `_handle`, после ветки захвата и ДО `if vk not in self._combo`:

```python
            if (self._on_esc is not None and vk == self._table.escape_vk
                    and msg in (WM_KEYDOWN, WM_SYSKEYDOWN)):
                # Esc-отмена вставки: репортим всегда, фильтрует по своему
                # состоянию Controller — хук не знает, идёт ли обработка.
                self._on_esc()
                return
```

Платформенные подклассы — прокинуть параметр. `molvi/platform/win32/hotkey.py`:

```python
    def __init__(self, on_press, on_release, combo, on_esc=None):
        super().__init__(on_press, on_release, combo, table=TABLE, on_esc=on_esc)
```

`molvi/platform/darwin/hotkey.py` — та же правка конструктора (своя `TABLE` с mac-кодом Esc уже подставляется).

- [ ] **Step 4: Тесты зелёные**

Run: `.venv\Scripts\python -m pytest tests/test_hotkey.py tests/test_hotkey_darwin.py -q`
Expected: PASS (darwin — SKIP на Windows).

- [ ] **Step 5: Commit**

```bash
git add molvi/hotkey.py molvi/platform/win32/hotkey.py molvi/platform/darwin/hotkey.py tests/test_hotkey.py
git commit -m "feat(hotkey): колбэк on_esc в ядре автомата — Esc репортится, не глотается"
```

---

### Task 2: функции цели вставки в платформенных typer-модулях

**Files:**
- Modify: `molvi/platform/win32/typer.py` (после `copy_to_clipboard`)
- Modify: `molvi/platform/darwin/typer.py` (после `copy_to_clipboard`)
- Test: `tests/test_typer.py`, `tests/test_typer_darwin.py` (дописать в конец)

**Interfaces:**
- Consumes: `_user32` (win), AppKit (mac) — уже импортированы в модулях.
- Produces (оба модуля): `get_target() -> handle | None` (win: HWND, mac: pid), `target_is_foreground(target) -> bool`, `activate_target(target, settle_delay=0.15) -> bool` — `True` только если цель реально стала активной; невалидная цель → `False` без исключения.

- [ ] **Step 1: Написать падающие тесты (win)**

В конец `tests/test_typer.py`:

```python
class FakeUser32:
    """WinAPI-заглушка для функций цели: журнал вызовов + управляемый фокус."""
    def __init__(self, foreground=100, valid=True, activate_switches=True):
        self.foreground = foreground
        self.valid = valid
        self.activate_switches = activate_switches
        self.calls = []

    def GetForegroundWindow(self):
        return self.foreground

    def IsWindow(self, hwnd):
        return 1 if self.valid else 0

    def GetWindowThreadProcessId(self, hwnd, ref):
        return 42  # чужой поток — ветка AttachThreadInput

    def AttachThreadInput(self, a, b, attach):
        self.calls.append(("attach", bool(attach)))
        return 1

    def SetForegroundWindow(self, hwnd):
        self.calls.append(("set_fg", hwnd))
        if self.activate_switches:
            self.foreground = hwnd
        return 1


@pytest.fixture
def fake_user32(monkeypatch):
    fake = FakeUser32()
    monkeypatch.setattr(typer, "_user32", fake)
    monkeypatch.setattr(typer.time, "sleep", lambda s: None)
    return fake


def test_get_target_returns_foreground_or_none(fake_user32):
    assert typer.get_target() == 100
    fake_user32.foreground = 0
    assert typer.get_target() is None


def test_target_is_foreground(fake_user32):
    assert typer.target_is_foreground(100) is True
    assert typer.target_is_foreground(200) is False
    assert typer.target_is_foreground(None) is False


def test_activate_target_invalid_window_false(fake_user32):
    fake_user32.valid = False
    assert typer.activate_target(200) is False
    assert fake_user32.calls == []  # до SetForegroundWindow не дошли


def test_activate_target_already_foreground_true(fake_user32):
    assert typer.activate_target(100) is True
    assert fake_user32.calls == []


def test_activate_target_switches_and_verifies(fake_user32):
    assert typer.activate_target(200) is True
    assert ("set_fg", 200) in fake_user32.calls
    # AttachThreadInput отцеплен после активации
    assert fake_user32.calls.count(("attach", True)) == 1
    assert fake_user32.calls.count(("attach", False)) == 1


def test_activate_target_verifies_result_not_call(fake_user32):
    # SetForegroundWindow «сработал», но фокус не сменился (foreground lock)
    fake_user32.activate_switches = False
    assert typer.activate_target(200) is False
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `.venv\Scripts\python -m pytest tests/test_typer.py -q`
Expected: FAIL — `AttributeError: ... has no attribute 'get_target'`.

- [ ] **Step 3: Реализация (win)**

`molvi/platform/win32/typer.py`, рядом с `_user32` вверху добавить:

```python
_kernel32 = ctypes.windll.kernel32
```

После `copy_to_clipboard`:

```python
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
```

- [ ] **Step 4: Реализация (darwin) + тесты**

`molvi/platform/darwin/typer.py`. Вверху к импорту AppKit добавить `NSWorkspace, NSRunningApplication, NSApplicationActivateIgnoringOtherApps`:

```python
from AppKit import (NSPasteboard, NSPasteboardTypeString, NSWorkspace,
                    NSRunningApplication,
                    NSApplicationActivateIgnoringOtherApps)
```

После `copy_to_clipboard`:

```python
def _frontmost_pid():
    app = NSWorkspace.sharedWorkspace().frontmostApplication()
    return None if app is None else app.processIdentifier()


def get_target():
    """Цель вставки. Точность macOS — приложение (pid), не окно:
    конкретное окно внутри приложения восстанавливает само приложение."""
    return _frontmost_pid()


def target_is_foreground(target):
    return target is not None and _frontmost_pid() == target


def activate_target(target, settle_delay=0.15):
    """Вернуть фокус исходному приложению; True — оно реально активно."""
    if target is None:
        return False
    app = NSRunningApplication.runningApplicationWithProcessIdentifier_(target)
    if app is None or app.isTerminated():
        return False
    app.activateWithOptions_(NSApplicationActivateIgnoringOtherApps)
    time.sleep(settle_delay)
    return _frontmost_pid() == target
```

В конец `tests/test_typer_darwin.py`:

```python
def test_target_is_foreground_darwin(monkeypatch):
    monkeypatch.setattr(typer, "_frontmost_pid", lambda: 777)
    assert typer.target_is_foreground(777) is True
    assert typer.target_is_foreground(1) is False
    assert typer.target_is_foreground(None) is False


def test_activate_target_none_is_false():
    assert typer.activate_target(None) is False
```

(Глубокое мокирование AppKit не делаем — поведение активации проверяется вживую на маке; это отмечено в спеке.)

- [ ] **Step 5: Тесты зелёные**

Run: `.venv\Scripts\python -m pytest tests/test_typer.py tests/test_typer_darwin.py -q`
Expected: PASS (darwin — SKIP на Windows).

- [ ] **Step 6: Commit**

```bash
git add molvi/platform/win32/typer.py molvi/platform/darwin/typer.py tests/test_typer.py tests/test_typer_darwin.py
git commit -m "feat(typer): функции цели вставки — get_target/target_is_foreground/activate_target"
```

---

### Task 3: Controller — цель вставки через очередь и возврат фокуса

**Files:**
- Modify: `molvi/controller.py` (конструктор, `on_release`, `_run`)
- Modify: `molvi/i18n.py` (ключ `controller.target_lost` в RU и EN, после `controller.paste_error`)
- Test: `tests/test_controller.py` (дописать; правка `_make`)

**Interfaces:**
- Consumes: сигнатуры Task 2 (передаются кортежем, сами функции не импортируются — контроллер кроссплатформенный).
- Produces: `Controller(..., target_fns=None)` — кортеж `(get_target, target_is_foreground, activate_target)` или `None` (старое поведение). Очередь заданий теперь несёт `(audio, target)`. Ключ `controller.target_lost`.

- [ ] **Step 1: Написать падающие тесты**

В `tests/test_controller.py` дополнить `_make` (новый параметр, прокинуть в Controller):

```python
def _make(audio_sec=1.0, text="привет мир", error=None, sounds=None,
          target_fns=None):
    audio = np.zeros(int(16000 * audio_sec), dtype=np.float32)
    rec, tr, ui = FakeRecorder(audio), FakeTranscriber(text, error), FakeUI()
    inserted = []
    notes = []
    ctl = Controller(
        rec, tr, lambda t, m: inserted.append((t, m)), ui,
        min_duration_sec=0.3, samplerate=16000, paste_mode="clipboard",
        notify=notes.append, sounds=sounds, target_fns=target_fns,
    )
    ctl.start()
    return ctl, rec, tr, ui, inserted, notes, sounds
```

В конец файла:

```python
class FakeTarget:
    """Функции цели: журнал вызовов + управляемое поведение фокуса."""
    def __init__(self, target="win1", foreground=True, activate_ok=True):
        self.target = target
        self.foreground = foreground
        self.activate_ok = activate_ok
        self.calls = []

    def get_target(self):
        self.calls.append("get")
        return self.target

    def is_foreground(self, t):
        self.calls.append(("is_fg", t))
        return self.foreground

    def activate(self, t):
        self.calls.append(("activate", t))
        return self.activate_ok

    @property
    def fns(self):
        return (self.get_target, self.is_foreground, self.activate)


def test_target_unchanged_inserts_without_activate():
    ft = FakeTarget(foreground=True)
    ctl, rec, tr, ui, inserted, notes, _ = _make(target_fns=ft.fns)
    ctl.on_press()
    ctl.on_release()
    assert _wait_until(lambda: inserted)
    ctl.shutdown()
    assert "get" in ft.calls
    assert ("is_fg", "win1") in ft.calls
    assert ("activate", "win1") not in ft.calls
    assert inserted == [("привет мир", "clipboard")]


def test_focus_changed_activates_then_inserts():
    ft = FakeTarget(foreground=False, activate_ok=True)
    ctl, rec, tr, ui, inserted, notes, _ = _make(target_fns=ft.fns)
    ctl.on_press()
    ctl.on_release()
    assert _wait_until(lambda: inserted)
    ctl.shutdown()
    assert ("activate", "win1") in ft.calls
    assert inserted == [("привет мир", "clipboard")]


def test_activate_failed_skips_insert_and_notifies():
    ft = FakeTarget(foreground=False, activate_ok=False)
    ctl, rec, tr, ui, inserted, notes, _ = _make(target_fns=ft.fns)
    ctl.on_press()
    ctl.on_release()
    assert _wait_until(lambda: notes)
    ctl.shutdown()
    assert inserted == []
    assert notes[0] == i18n.tr("controller.target_lost")
    assert ctl.last_text() == "привет мир"  # текст спасает трей


def test_get_target_error_degrades_to_old_behavior():
    ft = FakeTarget()
    ft.get_target = lambda: (_ for _ in ()).throw(OSError("no window"))
    ctl, rec, tr, ui, inserted, notes, _ = _make(target_fns=ft.fns)
    ctl.on_press()
    ctl.on_release()
    assert _wait_until(lambda: inserted)
    ctl.shutdown()
    assert inserted == [("привет мир", "clipboard")]


def test_no_target_fns_keeps_old_behavior():
    ctl, rec, tr, ui, inserted, notes, _ = _make()
    ctl.on_press()
    ctl.on_release()
    assert _wait_until(lambda: inserted)
    ctl.shutdown()
    assert inserted == [("привет мир", "clipboard")]
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `.venv\Scripts\python -m pytest tests/test_controller.py -q`
Expected: FAIL — `TypeError: ... unexpected keyword argument 'target_fns'`.

- [ ] **Step 3: Реализация**

`molvi/controller.py`. Конструктор — новый kwarg и распаковка:

```python
    def __init__(self, recorder, transcriber, insert_fn, ui, *,
                 min_duration_sec=0.3, samplerate=16000,
                 paste_mode="clipboard", notify=None, sounds=None,
                 paste_hint="Ctrl+V", target_fns=None):
```

и в теле конструктора:

```python
        # Функции цели вставки (get, is_foreground, activate) — платформенные,
        # передаются снаружи: контроллер не импортирует platform-модули.
        if target_fns is not None:
            self._get_target, self._target_is_foreground, self._activate_target = target_fns
        else:
            self._get_target = self._target_is_foreground = self._activate_target = None
```

`on_release`, вместо `self._jobs.put(audio)`:

```python
        target = None
        if self._get_target is not None:
            try:
                target = self._get_target()
            except Exception:
                # Нет цели — работаем по-старому: вставка в текущее окно.
                log.exception("Не удалось определить целевое окно")
        self._jobs.put((audio, target))
```

`_run` — распаковка задания и решение о вставке:

```python
    def _run(self):
        while True:
            job = self._jobs.get()
            if job is None:
                return
            audio, target = job
            ...
            if text:
                # Сохраняем до вставки: если вставка упадёт или уйдёт не в то
                # окно, текст можно забрать через трей.
                with self._lock:
                    self._last_text = text
                if self._insert_allowed(target):
                    try:
                        self._insert_fn(text, self._paste_mode)
                    except Exception as exc:
                        log.exception("Ошибка вставки текста")
                        self._notify(tr("controller.paste_error",
                                        exc=exc, paste_hint=self._paste_hint))
                else:
                    self._notify(tr("controller.target_lost"))
```

Новый метод (после `last_text`):

```python
    def _insert_allowed(self, target):
        """Фокус там же — вставляем; ушёл — возвращаем; не вышло — не
        вставляем вслепую в чужое окно (текст уже спасён в _last_text)."""
        if target is None or self._target_is_foreground is None:
            return True
        try:
            if self._target_is_foreground(target):
                return True
            return bool(self._activate_target(target))
        except Exception:
            log.exception("Не удалось вернуть фокус целевому окну")
            return False
```

`molvi/i18n.py`, RU после `controller.paste_error`:

```python
    "controller.target_lost": ("Не удалось вернуться в исходное окно — "
                               "текст в трее («Скопировать последний текст»)."),
```

EN после `controller.paste_error`:

```python
    "controller.target_lost": ("Couldn't switch back to the original window — "
                               "the text is in the tray (“Copy last transcript”)."),
```

- [ ] **Step 4: Тесты зелёные**

Run: `.venv\Scripts\python -m pytest tests/test_controller.py tests/test_i18n.py -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add molvi/controller.py molvi/i18n.py tests/test_controller.py
git commit -m "feat(controller): вставка в исходное окно — цель едет с заданием, возврат фокуса"
```

---

### Task 4: Controller.cancel_pending() — Esc-отмена вставки

**Files:**
- Modify: `molvi/controller.py`
- Modify: `molvi/i18n.py` (ключ `controller.paste_cancelled`, RU и EN)
- Test: `tests/test_controller.py` (дописать в конец)

**Interfaces:**
- Consumes: очередь `(audio, target)` из Task 3.
- Produces: `Controller.cancel_pending() -> None` — во время обработки помечает «не вставлять» (текст остаётся в `last_text`), вне обработки no-op. Ключ `controller.paste_cancelled`.

- [ ] **Step 1: Написать падающие тесты**

В конец `tests/test_controller.py`:

```python
def _make_slow(text="текст", delay=0.3):
    audio = np.zeros(16000, dtype=np.float32)
    rec, tr, ui = FakeRecorder(audio), FakeTranscriber(text, delay=delay), FakeUI()
    inserted, notes = [], []
    ctl = Controller(
        rec, tr, lambda t, m: inserted.append((t, m)), ui,
        min_duration_sec=0.3, samplerate=16000, paste_mode="clipboard",
        notify=notes.append,
    )
    ctl.start()
    return ctl, tr, ui, inserted, notes


def test_cancel_pending_skips_insert_keeps_text():
    ctl, tr, ui, inserted, notes = _make_slow()
    ctl.on_press()
    ctl.on_release()
    time.sleep(0.05)          # распознавание началось (delay=0.3)
    ctl.cancel_pending()
    assert _wait_until(lambda: notes)
    ctl.shutdown()
    assert inserted == []
    assert ctl.last_text() == "текст"
    assert notes[0] == i18n.tr("controller.paste_cancelled")


def test_cancel_outside_processing_is_noop():
    ctl, rec, tr, ui, inserted, notes, _ = _make()
    ctl.cancel_pending()      # заданий нет — Esc в обычной работе безвреден
    ctl.on_press()
    ctl.on_release()
    assert _wait_until(lambda: inserted)
    ctl.shutdown()
    assert notes == []
    assert inserted == [("привет мир", "clipboard")]


def test_next_dictation_after_cancel_inserts():
    ctl, tr, ui, inserted, notes = _make_slow()
    ctl.on_press()
    ctl.on_release()
    time.sleep(0.05)
    ctl.cancel_pending()
    assert _wait_until(lambda: notes)
    ctl.on_press()            # новая диктовка — новое намерение вставить
    ctl.on_release()
    assert _wait_until(lambda: inserted)
    ctl.shutdown()
    assert inserted == [("текст", "clipboard")]
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `.venv\Scripts\python -m pytest tests/test_controller.py -q`
Expected: FAIL — `AttributeError: 'Controller' object has no attribute 'cancel_pending'`.

- [ ] **Step 3: Реализация**

`molvi/controller.py`. В конструкторе рядом с `self._last_text`:

```python
        self._pending = 0        # заданий в очереди/обработке — гейт для Esc
        self._cancelled = False  # Esc: пропустить вставку текущих заданий
```

Новый метод после `last_text()`:

```python
    def cancel_pending(self):
        """Esc: не вставлять результат идущей обработки.

        Распознавание доводим до конца — текст останется в last_text
        (Esc отменяет вставку, не работу). Вне обработки — no-op, чтобы
        Esc в обычной жизни пользователя ни на что не влиял.
        """
        with self._lock:
            if self._pending == 0:
                return
            self._cancelled = True
```

`on_release`: перед `self._jobs.put((audio, target))`:

```python
        with self._lock:
            self._pending += 1
            self._cancelled = False  # новая диктовка — новое намерение вставить
```

`_run`: ветка `if text:` становится:

```python
            if text:
                with self._lock:
                    self._last_text = text
                    cancelled = self._cancelled
                if cancelled:
                    self._notify(tr("controller.paste_cancelled"))
                elif self._insert_allowed(target):
                    try:
                        self._insert_fn(text, self._paste_mode)
                    except Exception as exc:
                        log.exception("Ошибка вставки текста")
                        self._notify(tr("controller.paste_error",
                                        exc=exc, paste_hint=self._paste_hint))
                else:
                    self._notify(tr("controller.target_lost"))
```

и в конце каждой итерации цикла (перед проверкой `still_recording`):

```python
            with self._lock:
                self._pending -= 1
                still_recording = self._recording
```

(заменяет существующий блок `with self._lock: still_recording = self._recording`).

`molvi/i18n.py`, RU после `controller.target_lost`:

```python
    "controller.paste_cancelled": ("Вставка отменена — текст в трее "
                                   "(«Скопировать последний текст»)."),
```

EN после `controller.target_lost`:

```python
    "controller.paste_cancelled": ("Paste cancelled — the text is in the tray "
                                   "(“Copy last transcript”)."),
```

- [ ] **Step 4: Тесты зелёные**

Run: `.venv\Scripts\python -m pytest tests/test_controller.py tests/test_i18n.py -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add molvi/controller.py molvi/i18n.py tests/test_controller.py
git commit -m "feat(controller): cancel_pending — Esc отменяет вставку, текст остаётся в трее"
```

---

### Task 5: счётчик остатка на пилюле (Overlay)

**Files:**
- Modify: `molvi/overlay.py` (`show_transcribing`, `_poll`, `_build_scene`, `_animate`; новая чистая функция `eta_text`)
- Modify: `molvi/i18n.py` (ключ `overlay.eta`, RU и EN, рядом с `overlay.transcribing`)
- Test: `tests/test_overlay_anim.py` (дописать в конец)

**Interfaces:**
- Consumes: ничего нового (Task 6 начнёт передавать eta_sec).
- Produces: `Overlay.show_transcribing(eta_sec=None)` — старые вызовы без аргумента валидны; `eta_text(deadline, now) -> str | None` — чистая функция текста счётчика. Ключ `overlay.eta` = «~{sec} с» / "~{sec}s".

- [ ] **Step 1: Написать падающие тесты**

В конец `tests/test_overlay_anim.py` (добавить к импортам файла `from molvi import i18n` и `from molvi.overlay import eta_text`, если их нет; в файле уже импортируется `molvi.overlay`):

```python
def test_eta_text_none_deadline_hidden():
    assert eta_text(None, 100.0) is None


def test_eta_text_counts_down():
    i18n.set_language("ru")
    assert eta_text(110.0, 100.0) == "~10 с"
    assert eta_text(100.2, 100.0) == "~1 с"   # ceil: не обнуляем раньше времени


def test_eta_text_floors_at_zero():
    # Обработка затянулась дольше оценки — «~0 с», в минус не уходим.
    i18n.set_language("ru")
    assert eta_text(95.0, 100.0) == "~0 с"
```

Если в файле нет autouse-фикстуры сброса языка — добавить (образец в `tests/test_controller.py`):

```python
@pytest.fixture(autouse=True)
def _reset_language():
    i18n.set_language("ru")
    yield
    i18n.set_language("ru")
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `.venv\Scripts\python -m pytest tests/test_overlay_anim.py -q`
Expected: FAIL — `ImportError: cannot import name 'eta_text'`.

- [ ] **Step 3: Реализация**

`molvi/overlay.py`. Вверху к импортам добавить `import time`. Модульная функция после `bar_heights`:

```python
def eta_text(deadline, now):
    """Текст счётчика остатка обработки; None — не показывать.

    Оценка может соврать в меньшую сторону — при просрочке показываем
    «~0 с», а не отрицательные числа."""
    if deadline is None:
        return None
    return tr("overlay.eta", sec=max(0, math.ceil(deadline - now)))
```

Конструктор — рядом с `self._t = 0`:

```python
        self._eta_deadline = None   # monotonic-дедлайн счётчика «~N с»
```

`show_transcribing`:

```python
    def show_transcribing(self, eta_sec=None):
        self._queue.put(("transcribing", eta_sec))
```

`_poll` — состояние может быть кортежем; в начале обработки каждого состояния (сразу после `get_nowait`/проверки `quit`):

```python
            eta_sec = None
            if isinstance(state, tuple):
                state, eta_sec = state
```

и в ветке показа анимации (`elif self._canvas is not None:`) перед `self._start_anim(state)`:

```python
                    self._eta_deadline = (None if eta_sec is None
                                          else time.monotonic() + eta_sec)
```

в ветке `elif state == "hide":` добавить `self._eta_deadline = None`.
(Состояние `"recording"` приходит строкой — eta_sec останется None и дедлайн сбросится в ветке показа.)

`_build_scene` — после создания `self._dot`:

```python
        # Счётчик «~N с» — на месте точки: в жёлтом состоянии точка
        # малоинформативна, а места справа от баров нет.
        self._eta_item = self._canvas.create_text(
            h * 0.55, self._cy, text="", anchor="center",
            fill=theme.WARN, font=("Segoe UI", max(8, int(h * 0.18)), "bold"))
```

`_animate` — заменить две строки пульса точки

```python
        pulse = 1.0 + (0.18 * math.sin(self._t * 0.16) if state == "recording" else 0.0)
        r = self._dot_r * pulse
```

на:

```python
        show_eta = state == "transcribing" and self._eta_deadline is not None
        txt = eta_text(self._eta_deadline, time.monotonic()) if show_eta else None
        self._canvas.itemconfigure(self._eta_item, text=txt or "")
        pulse = 1.0 + (0.18 * math.sin(self._t * 0.16) if state == "recording" else 0.0)
        r = 0.0 if show_eta else self._dot_r * pulse   # счётчик вместо точки
```

`molvi/i18n.py`, RU после `overlay.transcribing`:

```python
    "overlay.eta": "~{sec} с",
```

EN после `overlay.transcribing`:

```python
    "overlay.eta": "~{sec}s",
```

- [ ] **Step 4: Тесты зелёные**

Run: `.venv\Scripts\python -m pytest tests/test_overlay_anim.py tests/test_overlay.py tests/test_i18n.py -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add molvi/overlay.py molvi/i18n.py tests/test_overlay_anim.py
git commit -m "feat(overlay): счётчик остатка «~N с» на пилюле при распознавании"
```

---

### Task 6: Controller — RTF-оценка и передача eta_sec оверлею

**Files:**
- Modify: `molvi/controller.py` (`on_release`, `_run`, `finish_model_reload`)
- Test: `tests/test_controller.py` (правка FakeUI; тесты в конец)

**Interfaces:**
- Consumes: `Overlay.show_transcribing(eta_sec=None)` (Task 5).
- Produces: контроллер зовёт `ui.show_transcribing(eta_sec=...)`; RTF — скользящее среднее в памяти (вес нового 0.5), сброс при успешной смене модели.

- [ ] **Step 1: Написать падающие тесты**

В `tests/test_controller.py` заменить FakeUI:

```python
class FakeUI:
    def __init__(self):
        self.events = []
        self.etas = []
    def show_recording(self):
        self.events.append("recording")
    def show_transcribing(self, eta_sec=None):
        self.events.append("transcribing")
        self.etas.append(eta_sec)
    def hide(self):
        self.events.append("hide")
```

В конец файла:

```python
def test_first_dictation_has_no_eta_then_estimated():
    ctl, rec, tr, ui, inserted, notes, _ = _make()
    ctl.on_press()
    ctl.on_release()
    assert _wait_until(lambda: inserted)
    ctl.on_press()
    ctl.on_release()
    assert _wait_until(lambda: len(inserted) == 2)
    ctl.shutdown()
    assert ui.etas[0] is None            # скорость ещё неизвестна
    assert ui.etas[1] is not None        # оценка от первого прогона
    assert ui.etas[1] >= 0


def test_eta_reset_on_model_reload():
    ctl, rec, tr, ui, inserted, notes, _ = _make()
    ctl.on_press()
    ctl.on_release()
    assert _wait_until(lambda: inserted)
    token = ctl.begin_model_reload()
    ctl.finish_model_reload(FakeTranscriber(text="новая"), token)
    ctl.on_press()
    ctl.on_release()
    assert _wait_until(lambda: len(inserted) == 2)
    ctl.shutdown()
    assert ui.etas[1] is None            # новая модель — старый RTF не годится
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `.venv\Scripts\python -m pytest tests/test_controller.py -q`
Expected: два новых теста FAIL (`ui.etas[1] is not None` / `is None`), остальные PASS.

- [ ] **Step 3: Реализация**

`molvi/controller.py`. Вверху добавить `import time`. В конструкторе рядом с `self._pending`:

```python
        self._rtf = None   # скорость распознавания (обработка/аудио) — для «~N с»
```

`on_release`: заменить `self._ui.show_transcribing()` на:

```python
        with self._lock:
            rtf = self._rtf
        eta = (len(audio) / self._samplerate) * rtf if rtf is not None else None
        self._ui.show_transcribing(eta_sec=eta)
```

`_run`: обернуть распознавание замером и обновить среднее при успехе:

```python
            started = time.monotonic()
            try:
                text = self._transcriber.transcribe(audio)
            except Exception as exc:
                log.exception("Ошибка распознавания")
                self._notify(tr("controller.transcribe_error", exc=exc))
                text = None
            if text is not None:
                duration = len(audio) / self._samplerate
                if duration > 0:
                    sample = (time.monotonic() - started) / duration
                    with self._lock:
                        # Вес нового 0.5: быстро сходится, но одиночный
                        # выброс (кэш прогрелся, GC) не ломает оценку.
                        self._rtf = (sample if self._rtf is None
                                     else 0.5 * self._rtf + 0.5 * sample)
                log.info("Распознано %d символов", len(text))
```

`finish_model_reload` — при применении нового transcriber:

```python
            if transcriber is not None:
                self._transcriber = transcriber
                self._rtf = None  # у новой модели своя скорость
```

- [ ] **Step 4: Тесты зелёные**

Run: `.venv\Scripts\python -m pytest tests/test_controller.py -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add molvi/controller.py tests/test_controller.py
git commit -m "feat(controller): RTF-оценка остатка обработки для счётчика пилюли"
```

---

### Task 7: связка в app.py + полный прогон

**Files:**
- Modify: `molvi/app.py` (создание `Controller`, ~строка 149; создание `listener`, ~строка 168)

**Interfaces:**
- Consumes: `Controller(target_fns=...)` (Task 3), `cancel_pending` (Task 4), `typer.get_target/target_is_foreground/activate_target` (Task 2), `hk.HotkeyListener(on_esc=...)` (Task 1).
- Produces: ничего нового наружу.

- [ ] **Step 1: Реализация**

`molvi/app.py`. В вызов `Controller(...)` добавить аргумент:

```python
            target_fns=(typer.get_target, typer.target_is_foreground,
                        typer.activate_target),
```

В вызов `hk.HotkeyListener(...)` добавить:

```python
            on_esc=controller.cancel_pending,
```

(`controller` к моменту создания listener уже присвоен — гонки нет.)

- [ ] **Step 2: Полный прогон + smoke**

Run: `.venv\Scripts\python -m pytest -q` и `.venv\Scripts\python -c "import molvi.app"`
Expected: тесты PASS, импорт без ошибок.

- [ ] **Step 3: Ручная проверка в dev-режиме (если окружение позволяет; иначе — на пользователе)**

`.venv\Scripts\python -m molvi.app`: (1) диктовка без переключения — как раньше; (2) длинная диктовка → во время жёлтого состояния уйти в другое окно → текст вставился в исходное; (3) счётчик «~N с» появляется со второй диктовки; (4) Esc во время обработки → вставки нет, уведомление, текст в трее.

- [ ] **Step 4: Commit**

```bash
git add molvi/app.py
git commit -m "feat(app): связка возврата фокуса, ETA и Esc-отмены"
```
