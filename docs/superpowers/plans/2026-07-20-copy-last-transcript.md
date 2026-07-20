# «Скопировать последний текст» в трее — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Пункт меню трея «Скопировать последний текст», возвращающий последнюю расшифровку в буфер обмена — спасение текста, потерянного при смене фокуса во время обработки.

**Architecture:** `Controller` запоминает последнюю успешную расшифровку в памяти (`last_text()`); платформенные `typer`-модули получают публичный `copy_to_clipboard()`; `Tray` — новый пункт меню с коллбэками `on_copy_last`/`has_last_text`; связка в `app.py`.

**Tech Stack:** Python 3.13, pystray, win32clipboard / NSPasteboard, pytest.

Спека: `docs/superpowers/specs/2026-07-20-copy-last-transcript-design.md`.

## Global Constraints

- Комментарии в коде и сообщения коммитов — по-русски; комментарии объясняют «почему», не «что» (CLAUDE.md).
- Тесты запускаются `.venv\Scripts\python -m pytest -q` (Windows) — все должны быть зелёными.
- Ключи i18n в RU и EN обязаны совпадать (проверяется существующим тестом `test_ru_en_same_keys`).
- Никаких новых зависимостей.
- Текст хранится только в памяти — на диск не пишется.

---

### Task 1: Controller запоминает последнюю расшифровку

**Files:**
- Modify: `molvi/controller.py` (поле в `__init__` ~строка 37, сохранение в `_run()` ~строка 131, новый метод)
- Test: `tests/test_controller.py` (дописать в конец)

**Interfaces:**
- Consumes: ничего нового.
- Produces: `Controller.last_text() -> str | None` — последняя успешная непустая расшифровка; `None`, если диктовок ещё не было. Потокобезопасен (лок внутри).

- [ ] **Step 1: Написать падающие тесты**

В конец `tests/test_controller.py` (хелперы `_make`, `_wait_until`, `FakeRecorder`, `FakeTranscriber`, `FakeUI` уже есть в файле):

```python
def test_last_text_none_before_first_dictation():
    ctl, *_ = _make()
    ctl.shutdown()
    assert ctl.last_text() is None


def test_last_text_saved_after_transcription():
    ctl, rec, tr, ui, inserted, *_ = _make(text="привет мир")
    ctl.on_press()
    ctl.on_release()
    assert _wait_until(lambda: inserted)
    ctl.shutdown()
    assert ctl.last_text() == "привет мир"


def test_last_text_saved_even_if_insert_fails():
    # Смысл фичи: расшифровка не должна пропасть, даже когда вставка упала.
    audio = np.zeros(16000, dtype=np.float32)
    rec, tr, ui = FakeRecorder(audio), FakeTranscriber("важный текст"), FakeUI()
    notes = []

    def failing_insert(t, m):
        raise OSError("SendInput failed")

    ctl = Controller(
        rec, tr, failing_insert, ui, min_duration_sec=0.3,
        samplerate=16000, paste_mode="clipboard", notify=notes.append,
    )
    ctl.start()
    ctl.on_press()
    ctl.on_release()
    assert _wait_until(lambda: notes)
    ctl.shutdown()
    assert ctl.last_text() == "важный текст"


def test_empty_transcription_keeps_previous_last_text():
    ctl, rec, tr, ui, inserted, *_ = _make(text="привет мир")
    ctl.on_press()
    ctl.on_release()
    assert _wait_until(lambda: inserted)
    tr.text = ""   # следующая диктовка распознана в пустоту
    ctl.on_press()
    ctl.on_release()
    assert _wait_until(lambda: ui.events.count("hide") >= 2)
    ctl.shutdown()
    assert ctl.last_text() == "привет мир"
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `.venv\Scripts\python -m pytest tests/test_controller.py -q`
Expected: 4 FAILED с `AttributeError: 'Controller' object has no attribute 'last_text'`, остальные PASS.

- [ ] **Step 3: Реализация**

В `molvi/controller.py`, в `__init__` рядом с `self._reload_token = 0`:

```python
        self._last_text = None  # последняя расшифровка — для «Скопировать последний текст»
```

Новый метод после `set_language()`:

```python
    def last_text(self):
        """Последняя успешная расшифровка (для пункта трея); None — диктовок не было."""
        with self._lock:
            return self._last_text
```

В `_run()`, внутри `if text:` — сохранить ДО вызова `self._insert_fn` (расшифровка не должна пропасть, даже если вставка упадёт):

```python
            if text:
                # Сохраняем до вставки: если вставка упадёт или уйдёт не в то
                # окно, текст можно забрать через трей.
                with self._lock:
                    self._last_text = text
                try:
                    self._insert_fn(text, self._paste_mode)
```

- [ ] **Step 4: Тесты зелёные**

Run: `.venv\Scripts\python -m pytest tests/test_controller.py -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add molvi/controller.py tests/test_controller.py
git commit -m "feat(controller): запоминать последнюю расшифровку (last_text)"
```

---

### Task 2: copy_to_clipboard() в платформенных typer-модулях

**Files:**
- Modify: `molvi/platform/win32/typer.py` (после `paste_text`, ~строка 113)
- Modify: `molvi/platform/darwin/typer.py` (после `paste_text`, ~строка 74)
- Test: `tests/test_typer.py`, `tests/test_typer_darwin.py` (дописать в конец)

**Interfaces:**
- Consumes: приватный `_set_clipboard_text(text)` — уже есть в обоих модулях.
- Produces: `copy_to_clipboard(text: str) -> None` в обоих модулях — кладёт текст в буфер без эмуляции вставки и без восстановления; исключения пробрасывает (буфер занят и т.п.).

- [ ] **Step 1: Написать падающие тесты**

В конец `tests/test_typer.py` (фикстура `fake_env` уже есть):

```python
def test_copy_to_clipboard_sets_without_paste_or_restore(fake_env):
    calls, clipboard = fake_env
    typer.copy_to_clipboard("спасённый текст")
    assert clipboard["text"] == "спасённый текст"
    assert calls == [("set", "спасённый текст")]  # ни ctrl_v, ни восстановления
```

В конец `tests/test_typer_darwin.py` (фикстура `fake_env` уже есть):

```python
def test_copy_to_clipboard_sets_without_paste_or_restore(fake_env):
    calls, clipboard = fake_env
    typer.copy_to_clipboard("спасённый текст")
    assert clipboard["text"] == "спасённый текст"
    assert calls == [("set", "спасённый текст")]  # ни cmd_v, ни восстановления
```

- [ ] **Step 2: Убедиться, что тест падает**

Run: `.venv\Scripts\python -m pytest tests/test_typer.py tests/test_typer_darwin.py -q`
Expected: 1 FAILED (`AttributeError: ... has no attribute 'copy_to_clipboard'`), darwin-файл — SKIP на Windows.

- [ ] **Step 3: Реализация**

В `molvi/platform/win32/typer.py` после `paste_text`:

```python
def copy_to_clipboard(text):
    """Явное копирование по просьбе пользователя (пункт трея) —
    без вставки и без восстановления прежнего буфера."""
    _set_clipboard_text(text)
```

Та же функция (дословно) в `molvi/platform/darwin/typer.py` после `paste_text`.

- [ ] **Step 4: Тесты зелёные**

Run: `.venv\Scripts\python -m pytest tests/test_typer.py tests/test_typer_darwin.py -q`
Expected: PASS (darwin — SKIP на Windows).

- [ ] **Step 5: Commit**

```bash
git add molvi/platform/win32/typer.py molvi/platform/darwin/typer.py tests/test_typer.py tests/test_typer_darwin.py
git commit -m "feat(typer): публичный copy_to_clipboard на обеих платформах"
```

---

### Task 3: Пункт меню в трее + ключи i18n

**Files:**
- Modify: `molvi/tray.py` (конструктор и меню, строки 20–35; новый хендлер)
- Modify: `molvi/i18n.py` (словари RU ~строка 17 и EN ~строка 144)
- Test: `tests/test_tray.py` (новый файл)

**Interfaces:**
- Consumes: `tr()` из `molvi.i18n`.
- Produces: `Tray(on_toggle_pause, on_exit, on_settings=None, on_copy_last=None, has_last_text=None)` — два новых опциональных коллбэка: `on_copy_last: () -> None` (клик по пункту), `has_last_text: () -> bool` (активность пункта). Ключи i18n: `tray.copy_last`, `app.notify.copied`, `app.notify.copy_failed`.

- [ ] **Step 1: Написать падающие тесты**

Новый файл `tests/test_tray.py`:

```python
import pytest

pytest.importorskip("pystray", reason="трей — только при установленном pystray")

from molvi.tray import Tray


def _make_tray(has_text):
    copied = []
    tray = Tray(
        on_toggle_pause=lambda: False,
        on_exit=lambda: None,
        on_copy_last=lambda: copied.append(True),
        has_last_text=lambda: has_text["value"],
    )
    return tray, copied


def test_copy_last_menu_item_calls_callback():
    has_text = {"value": True}
    tray, copied = _make_tray(has_text)
    tray._copy_last(None, None)
    assert copied == [True]


def test_copy_last_enabled_follows_has_last_text():
    has_text = {"value": False}
    tray, copied = _make_tray(has_text)
    # Пункт «Скопировать последний текст» — второй (после «Настройки…»).
    item = tuple(tray._icon.menu.items)[1]
    assert item.enabled is False   # диктовок ещё не было — пункт серый
    has_text["value"] = True
    assert item.enabled is True


def test_default_callbacks_are_safe():
    # Tray создаётся в app.py до загрузки модели — дефолты не должны падать.
    tray = Tray(on_toggle_pause=lambda: False, on_exit=lambda: None)
    tray._copy_last(None, None)
    item = tuple(tray._icon.menu.items)[1]
    assert item.enabled is False
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `.venv\Scripts\python -m pytest tests/test_tray.py -q`
Expected: 3 FAILED (`TypeError: ... unexpected keyword argument 'on_copy_last'` / `AttributeError: _copy_last`).

- [ ] **Step 3: Реализация**

В `molvi/tray.py` — конструктор:

```python
    def __init__(self, on_toggle_pause, on_exit, on_settings=None,
                 on_copy_last=None, has_last_text=None):
        self._on_toggle_pause = on_toggle_pause
        self._on_exit = on_exit
        self._on_settings = on_settings or (lambda: None)
        self._on_copy_last = on_copy_last or (lambda: None)
        self._has_last_text = has_last_text or (lambda: False)
        self._paused = False
        self._icon = pystray.Icon(
            "Molvi", _make_icon_image(), "Molvi",
            menu=pystray.Menu(
                pystray.MenuItem(lambda item: tr("tray.settings"), self._settings),
                pystray.MenuItem(
                    lambda item: tr("tray.copy_last"), self._copy_last,
                    enabled=lambda item: self._has_last_text(),
                ),
                pystray.MenuItem(
                    lambda item: tr("tray.resume") if self._paused else tr("tray.pause"),
                    self._toggle,
                ),
                pystray.MenuItem(lambda item: tr("tray.quit"), self._exit),
            ),
        )
```

Новый хендлер после `_settings`:

```python
    def _copy_last(self, icon, item):
        self._on_copy_last()
```

В `molvi/i18n.py` — в `RU` после `"tray.settings"`:

```python
    "tray.copy_last": "Скопировать последний текст",
```

в `RU` после `"app.notify.settings_failed"`:

```python
    "app.notify.copied": "Текст скопирован в буфер обмена",
    "app.notify.copy_failed": "Не удалось скопировать: {exc}",
```

в `EN` после `"tray.settings"`:

```python
    "tray.copy_last": "Copy last transcript",
```

в `EN` после `"app.notify.settings_failed"`:

```python
    "app.notify.copied": "Text copied to clipboard",
    "app.notify.copy_failed": "Copy failed: {exc}",
```

- [ ] **Step 4: Тесты зелёные (включая паритет ключей RU/EN)**

Run: `.venv\Scripts\python -m pytest tests/test_tray.py tests/test_i18n.py -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add molvi/tray.py molvi/i18n.py tests/test_tray.py
git commit -m "feat(tray): пункт «Скопировать последний текст» + ключи i18n"
```

---

### Task 4: Связка в app.py + полный прогон

**Files:**
- Modify: `molvi/app.py` (создание `Tray(...)`, ~строка 92)

**Interfaces:**
- Consumes: `controller.last_text()` (Task 1), `typer.copy_to_clipboard()` (Task 2), `Tray(on_copy_last=..., has_last_text=...)` (Task 3), `tr("app.notify.copied")` / `tr("app.notify.copy_failed")` (Task 3).
- Produces: ничего нового наружу.

- [ ] **Step 1: Реализация**

В `molvi/app.py` перед созданием `tray` (после `def shutdown():`) добавить коллбэк. `controller` в момент создания трея ещё `None` (модель грузится позже) — защита обязательна, как в `on_toggle_pause`:

```python
        def copy_last_to_clipboard():
            text = controller.last_text() if controller is not None else None
            if text is None:
                return  # гонка: пункт кликнули до первой диктовки
            try:
                typer.copy_to_clipboard(text)
            except Exception as exc:
                log.exception("Не удалось скопировать текст в буфер")
                tray.notify(tr("app.notify.copy_failed", exc=exc))
                return
            tray.notify(tr("app.notify.copied"))
```

И в конструктор `Tray(...)` два новых аргумента:

```python
        tray = Tray(
            on_toggle_pause=lambda: controller.toggle_pause() if controller is not None else False,
            on_exit=shutdown,
            on_settings=overlay.open_settings,
            on_copy_last=copy_last_to_clipboard,
            has_last_text=lambda: controller is not None and controller.last_text() is not None,
        )
```

- [ ] **Step 2: Полный прогон тестов**

Run: `.venv\Scripts\python -m pytest -q`
Expected: all PASS (win-специфичные — как обычно, darwin — SKIP).

- [ ] **Step 3: Ручная проверка в dev-режиме**

Run: `.venv\Scripts\python -m molvi.app`
Проверить: (1) сразу после запуска пункт «Скопировать последний текст» серый; (2) продиктовать фразу в блокнот; (3) кликнуть пункт в трее → уведомление «Текст скопирован в буфер обмена», Ctrl+V в блокноте вставляет фразу; (4) сценарий бага: начать диктовку, во время обработки кликнуть на рабочий стол — текст не вставился, но пункт трея его возвращает.

- [ ] **Step 4: Commit**

```bash
git add molvi/app.py
git commit -m "feat(app): связка «Скопировать последний текст» — controller → typer → tray"
```
