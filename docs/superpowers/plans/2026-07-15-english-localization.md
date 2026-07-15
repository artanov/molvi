# Английская версия Molvi — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Интерфейс приложения на двух языках (RU/EN, переключение в настройках, автоопределение при первом запуске) + англоязычная версия сайта на molvi.tech/en/.

**Architecture:** Свой модуль-словарь `molvi/i18n.py` (без gettext): словари `RU`/`EN` с одинаковыми ключами, функция `tr(key, **fmt)`, язык из конфига (`ui_language: auto|ru|en`). Все видимые пользователю строки в 9 файлах заменяются на `tr()`. Сайт — статичные EN-копии 5 страниц в `docs/site/en/` + перекрёстный hreflang.

**Tech Stack:** Python 3.13, tkinter, pystray; статичный HTML. Новых зависимостей НЕТ.

**Spec:** `docs/superpowers/specs/2026-07-15-english-localization-design.md`

## Global Constraints

- Новые зависимости не добавлять; `requirements-base.txt` не трогать.
- Комментарии в коде — по-русски, объясняют «почему», не «что».
- Логи (`log.*`) остаются по-русски — их читает разработчик (вне рамок).
- Настройку языка распознавания (`language: auto|ru|en`) не трогать — она уже работает.
- После каждой задачи тесты зелёные: `.venv\Scripts\python -m pytest -q` (Windows).
- Дефолтный язык i18n до вызова `set_language` — `ru` (существующее поведение не меняется).
- Ошибка `ValueError("Неизвестное имя клавиши…")` в `hotkey.py` — dev-facing, НЕ переводить.
- Коммиты — по-русски, в стиле репозитория (`feat:`, `site:`, `docs:` …).

---

### Task 1: Модуль i18n со словарями RU/EN

**Files:**
- Create: `molvi/i18n.py`
- Test: `tests/test_i18n.py`

**Interfaces:**
- Produces: `tr(key: str, **fmt) -> str`; `set_language(lang: str) -> None` (принимает `"auto"|"ru"|"en"`); `current_language() -> str` (`"ru"|"en"`); `system_language() -> str` (`"ru"|"en"`); словари `RU: dict[str, str]`, `EN: dict[str, str]`. Все последующие задачи используют ключи, определённые здесь.

- [ ] **Step 1: Написать падающие тесты**

Создать `tests/test_i18n.py`:

```python
import re

import pytest

from molvi import i18n


@pytest.fixture(autouse=True)
def _reset_language():
    # Каждый тест начинает с ru — как приложение до чтения конфига.
    i18n.set_language("ru")
    yield
    i18n.set_language("ru")


def test_ru_en_same_keys():
    assert set(i18n.RU) == set(i18n.EN)


def test_en_has_no_cyrillic():
    for key, value in i18n.EN.items():
        assert not re.search("[А-Яа-яЁё]", value), f"кириллица в EN[{key}]"


def test_tr_returns_russian_by_default():
    assert i18n.tr("tray.quit") == "Выход"


def test_tr_switches_to_english():
    i18n.set_language("en")
    assert i18n.tr("tray.quit") == "Quit"


def test_tr_formats_placeholders():
    i18n.set_language("en")
    assert "boom" in i18n.tr("controller.mic_unavailable", exc="boom")


def test_tr_unknown_key_returns_key():
    assert i18n.tr("no.such.key") == "no.such.key"


def test_tr_missing_format_arg_returns_raw():
    # Опечатка в имени параметра не должна ронять UI.
    raw = i18n.tr("controller.mic_unavailable")
    assert "{exc}" in raw


def test_set_language_auto_uses_system(monkeypatch):
    monkeypatch.setattr(i18n, "system_language", lambda: "en")
    i18n.set_language("auto")
    assert i18n.current_language() == "en"


def test_set_language_unknown_falls_back_to_en():
    i18n.set_language("de")
    assert i18n.current_language() == "en"
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `.venv\Scripts\python -m pytest tests/test_i18n.py -q`
Expected: FAIL / ошибка импорта `molvi.i18n`.

- [ ] **Step 3: Создать `molvi/i18n.py`**

Полный код модуля (словари — единственный источник всех строк UI; ключи ниже используются задачами 3–7 — не переименовывать):

```python
"""Строки интерфейса RU/EN — единый источник (как theme.py для палитры).

Ключи в RU и EN обязаны совпадать (тест test_ru_en_same_keys). Логи и
dev-ошибки сюда не выносятся — их читает разработчик, а не пользователь.
"""
import logging
import os
import sys

log = logging.getLogger(__name__)

RU = {
    # --- трей ---
    "tray.settings": "Настройки…",
    "tray.pause": "Пауза",
    "tray.resume": "Возобновить",
    "tray.quit": "Выход",
    # --- оверлей (текстовый fallback) ---
    "overlay.recording": "●  Запись…",
    "overlay.transcribing": "⏳  Распознаю…",
    # --- controller ---
    "controller.mic_unavailable": "Микрофон недоступен: {exc}",
    "controller.record_error": "Ошибка записи: {exc}",
    "controller.transcribe_error": "Ошибка распознавания: {exc}",
    "controller.paste_error": ("Не удалось вставить текст: {exc}. Распознанный "
                               "текст — в буфере обмена ({paste_hint})."),
    # --- transcriber ---
    "transcriber.cuda_missing": (
        "Библиотеки NVIDIA (cublas64_12.dll/cudnn64_9.dll) не найдены — "
        "device=cuda невозможен. Пройдите загрузку в мастере или "
        "поставьте device=auto."),
    # --- app (уведомления) ---
    "app.notify.cuda_download": "Скачиваю библиотеки NVIDIA (~0.6 ГБ) — разовая загрузка…",
    "app.notify.cuda_failed": ("Не удалось скачать библиотеки NVIDIA — "
                               "распознавание будет на процессоре."),
    "app.notify.loading_model": "Загружаю модель распознавания…",
    "app.notify.hotkey_broken": "Клавиша диктовки не работает: {exc}. Подробности в molvi.log",
    "app.notify.model_ready": "Готов. Модель: {model}",
    "app.notify.model_failed": "Не удалось загрузить модель: {exc}. Возвращены прежние настройки.",
    "app.notify.model_reloading": "Загружаю модель… Диктовка временно недоступна.",
    "app.notify.autostart_failed": "Не удалось изменить автозапуск: {exc}",
    "app.notify.settings_failed": "Не удалось применить настройки: {exc}",
    "app.notify.ready": "Готов. Зажмите {hotkey} и говорите{suffix}",
    "app.notify.cpu_suffix": " (CPU — медленный режим!)",
    "app.fatal": "Molvi не запустился: {exc}\n\nПодробности в журнале:\n{log_path}",
    # --- автозапуск ---
    "autostart.windows": "Запускать вместе с Windows",
    "autostart.mac": "Запускать при входе в систему",
    # --- настройки ---
    "settings.title": "Molvi — настройки",
    "settings.hotkey": "Клавиша диктовки:",
    "settings.change": "Изменить",
    "settings.microphone": "Микрофон:",
    "settings.language": "Язык распознавания:",
    "settings.ui_language": "Язык интерфейса:",
    "settings.quality": "Качество:",
    "settings.sounds": "Звуки записи",
    "settings.save": "Сохранить",
    "settings.cancel": "Отмена",
    "settings.press_combo": "Нажмите комбинацию… (Esc — отмена)",
    "settings.current_device": "Текущее: {name}",
    "settings.default_device": "Системный по умолчанию",
    "settings.lang.auto": "Авто",
    "settings.lang.ru": "Русский",
    "settings.lang.en": "English",
    "settings.ui_lang.auto": "Авто (как в системе)",
    "settings.quality.max_win": "Максимальное — large-v3 (нужна NVIDIA, ~3 ГБ)",
    "settings.quality.max_mac": "Максимальное — large-v3-turbo (~1.6 ГБ)",
    "settings.quality.small": "Среднее — small (~500 МБ)",
    "settings.quality.base": "Быстрое — base (~150 МБ)",
    # --- единицы ---
    "unit.gb": "ГБ",
    "unit.mb": "МБ",
    # --- мастер ---
    "wizard.title": "Molvi — первый запуск",
    "wizard.back": "Назад",
    "wizard.next": "Далее",
    "wizard.finish": "Готово",
    "wizard.step_failed": ("Этот шаг не удался — нажмите «Далее», "
                           "настройку можно закончить позже в Настройках."),
    "wizard.confirm_quit": "Идёт загрузка. Прервать и выйти?",
    "wizard.language.title": "Язык / Language",
    "wizard.welcome.title": "Добро пожаловать в Molvi",
    "wizard.welcome.body": (
        "Molvi печатает вашим голосом: зажмите клавишу, говорите, "
        "отпустите — текст появится там, где стоит курсор. Распознавание "
        "работает полностью на вашем компьютере, без интернета и подписок.\n\n"
        "Сейчас мы за пару минут всё настроим."),
    "wizard.hw.title": "Оборудование",
    "wizard.hw.mac": ("Apple Silicon: распознавание работает через Metal "
                      "(mlx-whisper) — рекомендуем максимальное качество."),
    "wizard.hw.gpu": ("Найдена видеокарта {name} ({vram}) — рекомендуем "
                      "максимальное качество."),
    "wizard.hw.nogpu": ("Видеокарта NVIDIA не найдена — распознавание будет на "
                        "процессоре, рекомендуем быструю модель."),
    "wizard.dl.title": "Загрузка компонентов",
    "wizard.dl.will_download": "Будут загружены: {parts}.",
    "wizard.dl.part_model": "модель ({size} ГБ)",
    "wizard.dl.part_cuda": "библиотеки NVIDIA (~0.6 ГБ)",
    "wizard.dl.start": "Начать загрузку",
    "wizard.dl.skip_note": ("Можно нажать «Далее» и пропустить — тогда недостающее докачается "
                            "само при следующем запуске Molvi (придётся подождать)."),
    "wizard.dl.preparing": "Готовлюсь…",
    "wizard.dl.progress_cuda": "NVIDIA: {pkg} {done} / {total} МБ",
    "wizard.dl.progress_model": "Модель: {done} / ~{total} МБ",
    "wizard.dl.done": "Готово!",
    "wizard.dl.failed": "Не получилось: {exc}",
    "wizard.dl.retry": "Повторить",
    "wizard.mic.title": "Микрофон",
    "wizard.mic.speak": "Скажите что-нибудь — полоска должна дёргаться:",
    "wizard.mic.failed": "Не удалось открыть микрофон: {exc}",
    "wizard.perm.title": "Разрешения macOS",
    "wizard.perm.body": (
        "Molvi слушает клавишу диктовки и вставляет текст в активное "
        "окно — macOS требует явно разрешить и то, и другое. "
        "В режиме разработки разрешения выдаются Терминалу."),
    "wizard.perm.listen": "Мониторинг ввода (клавиша диктовки)",
    "wizard.perm.post": "Универсальный доступ (вставка текста)",
    "wizard.perm.grant": "Выдать…",
    "wizard.perm.restart_note": ("Если после выдачи разрешения галочка не появилась — "
                                 "перезапустите Molvi, macOS применяет их при старте."),
    "wizard.hk.title": "Клавиша диктовки",
    "wizard.hk.hint": ("Зажмите эту клавишу (или комбинацию) — идёт запись; отпустите — "
                       "текст напечатается. Изменить можно в любой момент в Настройках."),
    "wizard.hk.unavailable": ("Клавиша недоступна: выдайте разрешение «Мониторинг "
                              "ввода» и перезапустите Molvi"),
    "wizard.done.title": "Всё готово",
    "wizard.done.where_mac": "в строке меню (справа сверху)",
    "wizard.done.where_win": "в трее (значок у часов)",
    "wizard.done.how_mac": "Настройки в любой момент: значок в строке меню → «Настройки…».",
    "wizard.done.how_win": "Настройки в любой момент: правый клик по значку в трее → «Настройки…».",
    "wizard.done.body": (
        "После нажатия «Готово» загрузится модель распознавания — дождитесь "
        "уведомления «Готов» {where}.\n\n"
        "Затем зажмите {hotkey} и говорите — текст появится там, где стоит "
        "курсор.\n\n{how}"),
}

EN = {
    "tray.settings": "Settings…",
    "tray.pause": "Pause",
    "tray.resume": "Resume",
    "tray.quit": "Quit",
    "overlay.recording": "●  Recording…",
    "overlay.transcribing": "⏳  Transcribing…",
    "controller.mic_unavailable": "Microphone unavailable: {exc}",
    "controller.record_error": "Recording error: {exc}",
    "controller.transcribe_error": "Recognition error: {exc}",
    "controller.paste_error": ("Couldn't paste the text: {exc}. The recognized "
                               "text is in the clipboard ({paste_hint})."),
    "transcriber.cuda_missing": (
        "NVIDIA libraries (cublas64_12.dll/cudnn64_9.dll) not found — "
        "device=cuda is impossible. Run the download in the setup wizard or "
        "set device=auto."),
    "app.notify.cuda_download": "Downloading NVIDIA libraries (~0.6 GB) — one-time download…",
    "app.notify.cuda_failed": ("Couldn't download the NVIDIA libraries — "
                               "recognition will run on the CPU."),
    "app.notify.loading_model": "Loading the speech recognition model…",
    "app.notify.hotkey_broken": "The dictation key isn't working: {exc}. See molvi.log for details",
    "app.notify.model_ready": "Ready. Model: {model}",
    "app.notify.model_failed": "Couldn't load the model: {exc}. Previous settings restored.",
    "app.notify.model_reloading": "Loading the model… Dictation is temporarily unavailable.",
    "app.notify.autostart_failed": "Couldn't change autostart: {exc}",
    "app.notify.settings_failed": "Couldn't apply the settings: {exc}",
    "app.notify.ready": "Ready. Hold {hotkey} and speak{suffix}",
    "app.notify.cpu_suffix": " (CPU — slow mode!)",
    "app.fatal": "Molvi failed to start: {exc}\n\nDetails in the log:\n{log_path}",
    "autostart.windows": "Start with Windows",
    "autostart.mac": "Start at login",
    "settings.title": "Molvi — Settings",
    "settings.hotkey": "Dictation key:",
    "settings.change": "Change",
    "settings.microphone": "Microphone:",
    "settings.language": "Speech language:",
    "settings.ui_language": "Interface language:",
    "settings.quality": "Quality:",
    "settings.sounds": "Recording sounds",
    "settings.save": "Save",
    "settings.cancel": "Cancel",
    "settings.press_combo": "Press a key combination… (Esc to cancel)",
    "settings.current_device": "Current: {name}",
    "settings.default_device": "System default",
    "settings.lang.auto": "Auto",
    "settings.lang.ru": "Russian",
    "settings.lang.en": "English",
    "settings.ui_lang.auto": "Auto (system)",
    "settings.quality.max_win": "Best — large-v3 (requires NVIDIA, ~3 GB)",
    "settings.quality.max_mac": "Best — large-v3-turbo (~1.6 GB)",
    "settings.quality.small": "Medium — small (~500 MB)",
    "settings.quality.base": "Fast — base (~150 MB)",
    "unit.gb": "GB",
    "unit.mb": "MB",
    "wizard.title": "Molvi — First Run",
    "wizard.back": "Back",
    "wizard.next": "Next",
    "wizard.finish": "Finish",
    "wizard.step_failed": ("This step failed — click “Next”; you can finish "
                           "setup later in Settings."),
    "wizard.confirm_quit": "A download is in progress. Abort and exit?",
    "wizard.language.title": "Язык / Language",
    "wizard.welcome.title": "Welcome to Molvi",
    "wizard.welcome.body": (
        "Molvi types with your voice: hold a key, speak, release — the text "
        "appears right where your cursor is. Recognition runs entirely on "
        "your computer, with no internet and no subscriptions.\n\n"
        "Let's get everything set up in a couple of minutes."),
    "wizard.hw.title": "Hardware",
    "wizard.hw.mac": ("Apple Silicon: recognition runs on Metal "
                      "(mlx-whisper) — we recommend the best quality."),
    "wizard.hw.gpu": ("Found GPU {name} ({vram}) — we recommend "
                      "the best quality."),
    "wizard.hw.nogpu": ("No NVIDIA GPU found — recognition will run on the "
                        "CPU; we recommend the fast model."),
    "wizard.dl.title": "Downloading components",
    "wizard.dl.will_download": "Will be downloaded: {parts}.",
    "wizard.dl.part_model": "the model ({size} GB)",
    "wizard.dl.part_cuda": "NVIDIA libraries (~0.6 GB)",
    "wizard.dl.start": "Start download",
    "wizard.dl.skip_note": ("You can click “Next” to skip — anything missing will be "
                            "downloaded automatically the next time Molvi starts "
                            "(it will take a while)."),
    "wizard.dl.preparing": "Preparing…",
    "wizard.dl.progress_cuda": "NVIDIA: {pkg} {done} / {total} MB",
    "wizard.dl.progress_model": "Model: {done} / ~{total} MB",
    "wizard.dl.done": "Done!",
    "wizard.dl.failed": "Failed: {exc}",
    "wizard.dl.retry": "Retry",
    "wizard.mic.title": "Microphone",
    "wizard.mic.speak": "Say something — the bar should move:",
    "wizard.mic.failed": "Couldn't open the microphone: {exc}",
    "wizard.perm.title": "macOS permissions",
    "wizard.perm.body": (
        "Molvi listens for the dictation key and pastes text into the active "
        "window — macOS requires you to explicitly allow both. "
        "In dev mode the permissions are granted to Terminal."),
    "wizard.perm.listen": "Input Monitoring (dictation key)",
    "wizard.perm.post": "Accessibility (text pasting)",
    "wizard.perm.grant": "Grant…",
    "wizard.perm.restart_note": ("If the checkmark doesn't appear after granting — "
                                 "restart Molvi; macOS applies permissions at startup."),
    "wizard.hk.title": "Dictation key",
    "wizard.hk.hint": ("Hold this key (or combination) to record; release it and "
                       "the text will be typed. You can change it anytime in Settings."),
    "wizard.hk.unavailable": ("Key unavailable: grant the “Input Monitoring” "
                              "permission and restart Molvi"),
    "wizard.done.title": "All set",
    "wizard.done.where_mac": "in the menu bar (top right)",
    "wizard.done.where_win": "in the tray (icon near the clock)",
    "wizard.done.how_mac": "Settings anytime: menu bar icon → “Settings…”.",
    "wizard.done.how_win": "Settings anytime: right-click the tray icon → “Settings…”.",
    "wizard.done.body": (
        "After you click “Finish”, the recognition model will load — wait for "
        "the “Ready” notification {where}.\n\n"
        "Then hold {hotkey} and speak — the text will appear where your "
        "cursor is.\n\n{how}"),
}

_DICTS = {"ru": RU, "en": EN}
_current = "ru"


def system_language():
    """Язык системы → "ru"|"en". Любой сбой — молча en (мировой дефолт)."""
    try:
        if sys.platform == "win32":
            import ctypes
            # LANG_RUSSIAN = 0x19; язык UI пользователя, а не системная локаль.
            return "ru" if (ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0xFF) == 0x19 else "en"
        if sys.platform == "darwin":
            # Frozen .app из Finder не получает LANG — спрашиваем NSLocale.
            from Foundation import NSLocale
            langs = NSLocale.preferredLanguages()
            if langs:
                return "ru" if str(langs[0]).lower().startswith("ru") else "en"
        lang = os.environ.get("LC_ALL") or os.environ.get("LANG") or ""
        return "ru" if lang.lower().startswith("ru") else "en"
    except Exception:
        log.warning("Не удалось определить язык системы", exc_info=True)
        return "en"


def set_language(lang):
    """lang: "auto" → язык системы; неизвестный код → en."""
    global _current
    if lang == "auto":
        lang = system_language()
    _current = lang if lang in _DICTS else "en"


def current_language():
    return _current


def tr(key, **fmt):
    s = _DICTS[_current].get(key)
    if s is None:
        log.warning("Нет перевода для ключа %r (%s)", key, _current)
        return key
    if not fmt:
        return s
    try:
        return s.format(**fmt)
    except (KeyError, IndexError):
        # Опечатка в параметрах не должна ронять UI — покажем шаблон как есть.
        log.warning("Неверные параметры формата для %r: %r", key, fmt)
        return s
```

- [ ] **Step 4: Прогнать тесты**

Run: `.venv\Scripts\python -m pytest tests/test_i18n.py -q`
Expected: PASS (все тесты зелёные).

- [ ] **Step 5: Полный прогон и коммит**

Run: `.venv\Scripts\python -m pytest -q` — зелёный.

```bash
git add molvi/i18n.py tests/test_i18n.py
git commit -m "feat(i18n): модуль строк RU/EN — единый источник текстов интерфейса"
```

---

### Task 2: Конфиг — ключ `ui_language`

**Files:**
- Modify: `molvi/config.py:9-25` (DEFAULTS)
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `load_config(path)["ui_language"]` — `"auto"|"ru"|"en"`, дефолт `"auto"`. Валидация типов уже покрывается существующим `_valid_type` (str).

- [ ] **Step 1: Падающий тест** — добавить в `tests/test_config.py`:

```python
def test_ui_language_default_auto(tmp_path):
    cfg = load_config(tmp_path / "config.json")
    assert cfg["ui_language"] == "auto"
```

(Импорт `load_config` в файле уже есть — проверить и переиспользовать стиль существующих тестов.)

- [ ] **Step 2: Прогнать** — `.venv\Scripts\python -m pytest tests/test_config.py -q` → FAIL (KeyError).

- [ ] **Step 3: Реализация** — в `DEFAULTS` после строки `"language": "auto",` добавить:

```python
    "ui_language": "auto",      # язык интерфейса: auto (по системе) | ru | en
```

- [ ] **Step 4: Прогнать** — `.venv\Scripts\python -m pytest tests/test_config.py -q` → PASS.

- [ ] **Step 5: Коммит**

```bash
git add molvi/config.py tests/test_config.py
git commit -m "feat(config): ключ ui_language — язык интерфейса (auto|ru|en)"
```

---

### Task 3: Подписи клавиш RU/EN (win32 + darwin)

**Files:**
- Modify: `molvi/hotkey.py:50-89` (`_DISPLAY`, `KeyTable`, `human_label`)
- Modify: `molvi/platform/darwin/hotkey.py:52-64` (`_DISPLAY`, `TABLE`)
- Test: `tests/test_hotkey.py`, `tests/test_hotkey_darwin.py`

**Interfaces:**
- Consumes: `i18n.current_language()` из Task 1.
- Produces: `KeyTable.display` теперь `{"ru": {...}, "en": {...}}`; сигнатуры `human_label(names, table=TABLE)`, `KeyTable(names, modifiers, display, escape_vk)` не меняются.

- [ ] **Step 1: Падающие тесты** — в `tests/test_hotkey.py` добавить:

```python
def test_human_label_english():
    from molvi import i18n
    i18n.set_language("en")
    try:
        assert human_label(["ctrl_left", "space"]) == "Left Ctrl + Space"
    finally:
        i18n.set_language("ru")


def test_human_label_russian_default():
    assert human_label(["ctrl_left", "space"]) == "Ctrl слева + Пробел"
```

В `tests/test_hotkey_darwin.py` добавить (стиль импортов взять из существующих тестов файла):

```python
def test_human_label_english_darwin():
    from molvi import i18n
    i18n.set_language("en")
    try:
        assert human_label(["win_right", "space"]) == "⌘ Right Cmd + Space"
    finally:
        i18n.set_language("ru")
```

- [ ] **Step 2: Прогнать** — `.venv\Scripts\python -m pytest tests/test_hotkey.py tests/test_hotkey_darwin.py -q` → новые FAIL.

- [ ] **Step 3: Реализация в `molvi/hotkey.py`**

Добавить `from molvi import i18n` к импортам. `_DISPLAY` переименовать в `_DISPLAY_RU`, добавить `_DISPLAY_EN` и собрать двухъязычный словарь:

```python
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
```

Комментарий у `KeyTable.display` обновить: «подписи по языкам {"ru": {...}, "en": {...}}». `human_label`:

```python
def human_label(names, table=TABLE):
    labels = table.display.get(i18n.current_language(), {})
    return " + ".join(labels.get(n, n.upper()) for n in names)
```

- [ ] **Step 4: Реализация в `molvi/platform/darwin/hotkey.py`**

Аналогично: `_DISPLAY` → `_DISPLAY_RU` + `_DISPLAY_EN` + сборка:

```python
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
```

`TABLE = KeyTable(VK_NAMES, MODIFIER_NAMES, _DISPLAY, VK_ESCAPE)` — без изменений (структура display поменялась внутри).

- [ ] **Step 5: Прогнать всё** — `.venv\Scripts\python -m pytest -q` → PASS. Если существующие тесты обращались к `table.display[...]` напрямую — поправить на `table.display["ru"][...]`.

- [ ] **Step 6: Коммит**

```bash
git add molvi/hotkey.py molvi/platform/darwin/hotkey.py tests/test_hotkey.py tests/test_hotkey_darwin.py
git commit -m "feat(i18n): подписи клавиш RU/EN в таблицах win32 и darwin"
```

---

### Task 4: Трей, controller, overlay, transcriber → tr()

**Files:**
- Modify: `molvi/tray.py:24-34,50-54`
- Modify: `molvi/controller.py:87,104,125,134-137`
- Modify: `molvi/overlay.py:13-16,229-231`
- Modify: `molvi/transcriber.py:53-58`
- Test: `tests/test_controller.py` (проверить, не завязаны ли ассерты на русские строки), `tests/test_overlay.py`

**Interfaces:**
- Consumes: `tr()` из Task 1; ключи `tray.*`, `controller.*`, `overlay.*`, `transcriber.cuda_missing`.
- Produces: `Tray.refresh()` — перерисовать меню после смены языка (используется Task 7).

- [ ] **Step 1: `molvi/tray.py`** — добавить `from molvi.i18n import tr`; пункты меню сделать callable (pystray перечитывает их при `update_menu()` и открытии меню):

```python
        self._icon = pystray.Icon(
            "Molvi", _make_icon_image(), "Molvi",
            menu=pystray.Menu(
                pystray.MenuItem(lambda item: tr("tray.settings"), self._settings),
                pystray.MenuItem(
                    lambda item: tr("tray.resume") if self._paused else tr("tray.pause"),
                    self._toggle,
                ),
                pystray.MenuItem(lambda item: tr("tray.quit"), self._exit),
            ),
        )
```

Добавить метод:

```python
    def refresh(self):
        """Перечитать подписи меню (после смены языка интерфейса)."""
        try:
            self._icon.update_menu()
        except Exception:
            pass  # как и notify — best effort
```

- [ ] **Step 2: `molvi/controller.py`** — добавить `from molvi.i18n import tr`; заменить четыре f-строки notify:

```python
                self._notify(tr("controller.mic_unavailable", exc=exc))
```
```python
                self._notify(tr("controller.record_error", exc=exc))
```
```python
                self._notify(tr("controller.transcribe_error", exc=exc))
```
```python
                    self._notify(tr("controller.paste_error",
                                    exc=exc, paste_hint=self._paste_hint))
```

- [ ] **Step 3: `molvi/overlay.py`** — добавить `from molvi.i18n import tr`; `_TEXT_STATES` хранит ключи (перевод берётся при показе — язык мог смениться):

```python
_TEXT_STATES = {
    "recording": ("overlay.recording", theme.RECORDING),
    "transcribing": ("overlay.transcribing", theme.TRANSCRIBING),
}
```

В `_poll` (ветка текстового fallback):

```python
                else:
                    key, bg = _TEXT_STATES[state]
                    self._label.config(text=tr(key), bg=bg)
```

- [ ] **Step 4: `molvi/transcriber.py`** — добавить `from molvi.i18n import tr` (после блока `_add_cuda_dll_dirs`); заменить RuntimeError:

```python
                raise RuntimeError(tr("transcriber.cuda_missing"))
```

То же в `molvi/platform/darwin/transcriber.py`, если там есть аналогичная пользовательская ошибка (проверить grep'ом по кириллице; ошибки только в логи — не трогать).

- [ ] **Step 5: Прогнать всё** — `.venv\Scripts\python -m pytest -q`. Тесты, завязанные на русские тексты уведомлений (grep по `Микрофон недоступен` и т.п. в tests/), переписать через `tr()` c явным `i18n.set_language("ru")`.

- [ ] **Step 6: Коммит**

```bash
git add molvi/tray.py molvi/controller.py molvi/overlay.py molvi/transcriber.py molvi/platform/darwin/transcriber.py tests/
git commit -m "feat(i18n): трей, controller, оверлей и transcriber через tr()"
```

---

### Task 5: Окно настроек — tr() + комбобокс языка интерфейса

**Files:**
- Modify: `molvi/settings.py` (весь файл — пресеты, языки, окно)
- Modify: `molvi/platform/win32/autostart.py:3`, `molvi/platform/darwin/autostart.py:15`
- Test: `tests/test_settings.py`, `tests/test_autostart.py`, `tests/test_autostart_darwin.py`, `tests/test_wizard.py` (импортирует QUALITY_PRESETS)

**Interfaces:**
- Consumes: `tr()`, ключи `settings.*`, `autostart.*`.
- Produces: `quality_presets() -> list[tuple[str, str]]` (замена константы `QUALITY_PRESETS`); `language_choices() -> list[tuple[str, str]]` (замена `LANGUAGES`); `ui_language_choices() -> list[tuple[str, str]]`; `quality_index_for_model(model)`, `language_index(code)`, `ui_language_index(code)`; `device_choices(device_names, current)` (сигнатура прежняя); в платформенных autostart: `LABEL_KEY: str` (ключ i18n) вместо `LABEL`. Wizard (Task 6) использует `quality_presets()` и `tr("settings.default_device")`. `SettingsWindow._save` кладёт в cfg ключ `ui_language`.

- [ ] **Step 1: Падающие тесты** — в `tests/test_settings.py` добавить:

```python
def test_quality_presets_english():
    from molvi import i18n
    i18n.set_language("en")
    try:
        labels = [label for label, _ in quality_presets()]
        assert any("Best" in l for l in labels)
    finally:
        i18n.set_language("ru")


def test_ui_language_choices_codes():
    assert [code for _, code in ui_language_choices()] == ["auto", "ru", "en"]


def test_device_choices_english_default_label():
    from molvi import i18n
    i18n.set_language("en")
    try:
        values, idx, mapping = device_choices(["Mic A"], None)
        assert values[0] == "System default"
        assert mapping["System default"] is None
    finally:
        i18n.set_language("ru")
```

Существующие импорты `QUALITY_PRESETS`/`LANGUAGES` в тестах поменять на функции.

- [ ] **Step 2: Прогнать** — `.venv\Scripts\python -m pytest tests/test_settings.py -q` → FAIL.

- [ ] **Step 3: Реализация `molvi/settings.py`**

Добавить `from molvi.i18n import tr`. Заменить модульные константы функциями (перевод берётся в момент вызова — окно всегда открывается на текущем языке):

```python
def quality_presets():
    if sys.platform == "darwin":
        return [
            (tr("settings.quality.max_mac"), "large-v3-turbo"),
            (tr("settings.quality.small"), "small"),
            (tr("settings.quality.base"), "base"),
        ]
    return [
        (tr("settings.quality.max_win"), "large-v3"),
        (tr("settings.quality.small"), "small"),
        (tr("settings.quality.base"), "base"),
    ]


def language_choices():
    return [(tr("settings.lang.auto"), "auto"),
            (tr("settings.lang.ru"), "ru"),
            (tr("settings.lang.en"), "en")]


def ui_language_choices():
    # Названия языков — на самом языке: «Русский» ищет русскоязычный.
    return [(tr("settings.ui_lang.auto"), "auto"), ("Русский", "ru"), ("English", "en")]


def quality_index_for_model(model):
    for i, (_label, m) in enumerate(quality_presets()):
        if m == model:
            return i
    return 0


def language_index(code):
    for i, (_label, c) in enumerate(language_choices()):
        if c == code:
            return i
    return 0


def ui_language_index(code):
    for i, (_label, c) in enumerate(ui_language_choices()):
        if c == code:
            return i
    return 0
```

`device_choices` — убрать `_DEFAULT_DEVICE_LABEL`, внутри:

```python
def device_choices(device_names, current):
    """→ (values_list, initial_index, mapping) для комбобокса микрофона."""
    default_label = tr("settings.default_device")
    values = [default_label] + list(device_names)
    mapping = {default_label: None}
    for name in device_names:
        mapping[name] = name
    if current is not None and current not in device_names:
        label = tr("settings.current_device", name=current)
        values.insert(1, label)
        mapping[label] = current
        return values, 1, mapping
    idx = values.index(current) if current in values else 0
    return values, idx, mapping
```

В `SettingsWindow.__init__` заменить все литералы: `win.title(tr("settings.title"))`, метки `tr("settings.hotkey")`, `tr("settings.microphone")`, `tr("settings.language")`, `tr("settings.quality")`, кнопки `tr("settings.change")`, `tr("settings.save")`, `tr("settings.cancel")`, чекбокс `tr("settings.sounds")`, автозапуск `tr(autostart.LABEL_KEY)`. `LANGUAGES`/`QUALITY_PRESETS` → локальные `self._languages = language_choices()` / `self._presets = quality_presets()` (индексы в `_save` берут из них же).

Добавить строку «Язык интерфейса» после строки «Язык распознавания» (сдвинуть row качества и ниже на +1):

```python
        ttk.Label(frm, text=tr("settings.ui_language")).grid(row=3, column=0, sticky="w", pady=4)
        self._ui_langs = ui_language_choices()
        self._ui_lang = ttk.Combobox(
            frm, values=[label for label, _ in self._ui_langs], state="readonly"
        )
        self._ui_lang.current(ui_language_index(cfg.get("ui_language", "auto")))
        self._ui_lang.grid(row=3, column=1, columnspan=2, sticky="we")
```

В `_change_hotkey`: `self._hotkey_var.set(tr("settings.press_combo"))`.

В `_save` добавить:

```python
        cfg["ui_language"] = self._ui_langs[self._ui_lang.current()][1]
```

- [ ] **Step 4: Платформенные autostart** — в `molvi/platform/win32/autostart.py` заменить `LABEL = "Запускать вместе с Windows"` на:

```python
LABEL_KEY = "autostart.windows"   # ключ i18n: подпись чекбокса в настройках
```

В `molvi/platform/darwin/autostart.py`: `LABEL = ...` → `LABEL_KEY = "autostart.mac"`. Поправить все обращения `autostart.LABEL` (grep по репо: settings.py, тесты).

- [ ] **Step 5: Прогнать всё** — `.venv\Scripts\python -m pytest -q` → PASS (тесты wizard тоже: он импортирует пресеты — на этом шаге поправить импорт в `molvi/wizard.py` механически: `QUALITY_PRESETS` → `quality_presets` с вызовами `quality_presets()` в `_step_hardware`/`_on_quality`; полная локализация мастера — Task 6).

- [ ] **Step 6: Коммит**

```bash
git add molvi/settings.py molvi/wizard.py molvi/platform/win32/autostart.py molvi/platform/darwin/autostart.py tests/
git commit -m "feat(i18n): окно настроек — tr() и выбор языка интерфейса"
```

---

### Task 6: Мастер первого запуска — tr() + шаг выбора языка

**Files:**
- Modify: `molvi/wizard.py` (весь файл)
- Test: `tests/test_wizard.py`

**Interfaces:**
- Consumes: `tr()`, `i18n.set_language()`, `i18n.current_language()`, ключи `wizard.*`, `unit.*`, `settings.default_device`; `quality_presets()` из Task 5.
- Produces: `Wizard.run()` возвращает cfg, включающий `ui_language` (`"ru"|"en"`, если пользователь выбрал; иначе `"auto"`); `vram_label(vram_mb)` — сигнатура прежняя, единицы через tr.

- [ ] **Step 1: Падающие тесты** — в `tests/test_wizard.py` добавить:

```python
def test_vram_label_english():
    from molvi import i18n
    i18n.set_language("en")
    try:
        assert vram_label(8192) == "8 GB"
        assert vram_label(512) == "512 MB"
    finally:
        i18n.set_language("ru")


def test_vram_label_russian():
    assert vram_label(8192) == "8 ГБ"
```

- [ ] **Step 2: Прогнать** — `.venv\Scripts\python -m pytest tests/test_wizard.py -q` → FAIL.

- [ ] **Step 3: Реализация**

Добавить импорты: `from molvi import i18n` и `from molvi.i18n import tr`.

`vram_label`:

```python
def vram_label(vram_mb):
    """Человекочитаемый объём видеопамяти («8 ГБ», «512 МБ» — не «0 ГБ»)."""
    if vram_mb >= 1024:
        return f"{vram_mb // 1024} {tr('unit.gb')}"
    return f"{vram_mb} {tr('unit.mb')}"
```

В `__init__`: `self._root.title(tr("wizard.title"))`; кнопки создать без текста (текст ставит `_show_step`); первым шагом — язык:

```python
        self._steps = [self._step_language, self._step_welcome, self._step_hardware,
                       self._step_download, self._step_mic]
```

`_show_step` — подписи кнопок на текущем языке при каждой отрисовке:

```python
    def _show_step(self):
        self._clear()
        self._back_btn.config(text=tr("wizard.back"),
                              state="normal" if self._idx > 0 else "disabled")
        self._next_btn.config(
            text=tr("wizard.finish") if self._idx == len(self._steps) - 1 else tr("wizard.next"),
            state="normal")
        try:
            self._steps[self._idx]()
        except Exception:
            log.exception("Шаг мастера %d упал — пропускаю", self._idx)
            ttk.Label(self._body, text=tr("wizard.step_failed")).pack()
```

Новый шаг (радиокнопки на родных названиях, смена — мгновенная перерисовка):

```python
    def _step_language(self):
        self._title(tr("wizard.language.title"))
        self._lang_var = tk.StringVar(value=i18n.current_language())
        for label, code in (("Русский", "ru"), ("English", "en")):
            ttk.Radiobutton(self._body, text=label, variable=self._lang_var,
                            value=code, command=self._on_language).pack(anchor="w", pady=2)

    def _on_language(self):
        code = self._lang_var.get()
        self._cfg["ui_language"] = code
        i18n.set_language(code)
        self._root.title(tr("wizard.title"))
        self._show_step()  # перерисовать шаг и кнопки уже на новом языке
```

Замены строк по шагам (все `text=`-литералы):

- `_finish`: `messagebox.askyesno("Molvi", tr("wizard.confirm_quit"))`
- `_step_welcome`: `self._title(tr("wizard.welcome.title"))`; тело → `text=tr("wizard.welcome.body")`
- `_step_hardware`: `self._title(tr("wizard.hw.title"))`; ветки:
  `found = tr("wizard.hw.mac")` / `found = tr("wizard.hw.gpu", name=self._gpu["name"], vram=vram_label(self._gpu["vram_mb"]))` / `found = tr("wizard.hw.nogpu")`; `QUALITY_PRESETS` → `quality_presets()` (и в `_on_quality`)
- `_step_download`: заголовок `tr("wizard.dl.title")`; список:

```python
        parts = [tr("wizard.dl.part_model", size=f"{size_note:.1f}")]
        if need_dlls:
            parts.insert(0, tr("wizard.dl.part_cuda"))
        ttk.Label(self._body, wraplength=500, justify="left",
                  text=tr("wizard.dl.will_download", parts=", ".join(parts))).pack(anchor="w")
```

  кнопка `tr("wizard.dl.start")`, серая подсказка `tr("wizard.dl.skip_note")`
- `_start_download`: `self._progress = {"text": tr("wizard.dl.preparing"), ...}`; прогресс CUDA:

```python
                                text=tr("wizard.dl.progress_cuda", pkg=pkg,
                                        done=d // 1048576, total=max(t, 1) // 1048576),
```

  прогресс модели:

```python
                        self._progress.update(
                            text=tr("wizard.dl.progress_model",
                                    done=grown // 1048576, total=total // 1048576),
                            percent=40 + min(60.0, grown / total * 60))
```

  финал: `self._progress.update(text=tr("wizard.dl.done"), percent=100.0, done=True)`
- `_poll_download`: `self._status_var.set(tr("wizard.dl.failed", exc=self._download_error))`; `self._dl_btn.config(text=tr("wizard.dl.retry"), state="normal")`
- `_step_mic`: заголовок `tr("wizard.mic.title")`; `devices = [tr("settings.default_device")] + ...`; подсказка `tr("wizard.mic.speak")`
- `_mic_device`: `return None if val == tr("settings.default_device") else val`
- `_open_mic`: `self._mic_status_var.set(tr("wizard.mic.failed", exc=exc))`
- `_step_permissions`: заголовок `tr("wizard.perm.title")`, тело `tr("wizard.perm.body")`, пары `(tr("wizard.perm.listen"), "listen")`, `(tr("wizard.perm.post"), "post")`, кнопка `tr("wizard.perm.grant")`, примечание `tr("wizard.perm.restart_note")`
- `_step_hotkey`: заголовок `tr("wizard.hk.title")`, кнопка `tr("settings.change")`, подсказка `tr("wizard.hk.hint")`
- `_capture`: `self._hotkey_var.set(tr("settings.press_combo"))`
- `_poll_capture` (ветка dead): `self._hotkey_var.set(tr("wizard.hk.unavailable"))`
- `_step_done`:

```python
    def _step_done(self):
        self._title(tr("wizard.done.title"))
        if sys.platform == "darwin":
            where, how = tr("wizard.done.where_mac"), tr("wizard.done.how_mac")
        else:
            where, how = tr("wizard.done.where_win"), tr("wizard.done.how_win")
        ttk.Label(self._body, wraplength=500, justify="left",
                  text=tr("wizard.done.body", where=where,
                          hotkey=hk.human_label(self._cfg["hotkey"]), how=how)).pack(anchor="w")
```

- [ ] **Step 4: Прогнать всё** — `.venv\Scripts\python -m pytest -q` → PASS.

- [ ] **Step 5: Ручная проверка мастера** (только если есть дисплей): временно переименовать `%APPDATA%\Molvi\config.json`, запустить `.venv\Scripts\python -m molvi.app`, пройти первый шаг на обоих языках (заголовки, кнопки, радио), закрыть крестиком, вернуть конфиг.

- [ ] **Step 6: Коммит**

```bash
git add molvi/wizard.py tests/test_wizard.py
git commit -m "feat(i18n): мастер первого запуска — tr() и шаг выбора языка"
```

---

### Task 7: app.py — уведомления, инициализация языка, применение смены

**Files:**
- Modify: `molvi/app.py:34-283`
- Test: существующие (`tests/test_std_streams.py` и smoke в CI)

**Interfaces:**
- Consumes: `tr()`, `i18n.set_language()`, `Tray.refresh()` (Task 4), cfg `ui_language` (Task 2).

- [ ] **Step 1: Инициализация языка** — в `main()` после `_setup_logging()`/`log = ...`:

```python
        from molvi import i18n
```

Перед запуском мастера (ветка «config.json не найден»), первой строкой ветки:

```python
            i18n.set_language("auto")   # мастер стартует на языке системы
```

После получения cfg в обеих ветках (сразу после if/else блока загрузки конфига):

```python
        i18n.set_language(cfg.get("ui_language", "auto"))
```

Добавить `from molvi.i18n import tr` к локальным импортам main().

- [ ] **Step 2: Заменить уведомления в main()**

```python
                tray.notify(tr("app.notify.cuda_download"))
```
```python
                    tray.notify(tr("app.notify.cuda_failed"))
```
```python
        tray.notify(tr("app.notify.loading_model"))
```
```python
                tray.notify(tr("app.notify.hotkey_broken", exc=exc))
```
```python
                    tray.notify(tr("app.notify.model_ready", model=snapshot["model"]))
```
```python
                    tray.notify(tr("app.notify.model_failed", exc=exc))
```
```python
                    tray.notify(tr("app.notify.autostart_failed", exc=exc))
```
```python
                    tray.notify(tr("app.notify.model_reloading"))
```
```python
                tray.notify(tr("app.notify.settings_failed", exc=exc))
```

Финальное «Готов»:

```python
        suffix = ("" if transcriber.device in ("cuda", "mlx")
                  else tr("app.notify.cpu_suffix"))
        tray.notify(tr("app.notify.ready",
                       hotkey=hk.human_label(cfg["hotkey"]), suffix=suffix))
```

- [ ] **Step 3: Смена языка из настроек** — в `apply_settings`, внутри критической секции `with cfg_lock:` запомнить `old_ui_language = cfg["ui_language"]` (рядом с `old_model`/`old_language`), после `cfg.update(new_cfg)`/`save_config` добавить:

```python
                    if cfg["ui_language"] != old_ui_language:
                        # Меню трея перечитает подписи; открытые окна
                        # перерисуются при следующем открытии.
                        i18n.set_language(cfg["ui_language"])
                        tray.refresh()
```

- [ ] **Step 4: Фатальное окно** — `_show_fatal_error`:

```python
        from molvi.i18n import tr
        messagebox.showerror(
            "Molvi",
            tr("app.fatal", exc=exc, log_path=paths.log_path()),
        )
```

- [ ] **Step 5: Проверить остаток кириллицы в UI-строках**

Run: `.venv\Scripts\python -c "import re,pathlib; [print(p,i+1,l.rstrip()) for p in pathlib.Path('molvi').rglob('*.py') for i,l in enumerate(p.read_text(encoding='utf-8').splitlines()) if re.search('[А-Яа-яЁё]', l) and ('tray.notify' in l or 'messagebox' in l or 'text=' in l or '_notify(' in l)]"`
Expected: пусто (кириллица осталась только в комментариях, логах и i18n.py).

- [ ] **Step 6: Прогнать всё + dev-запуск**

Run: `.venv\Scripts\python -m pytest -q` → PASS. Затем `.venv\Scripts\python -m molvi.app` — переключить язык интерфейса в настройках на English, убедиться: меню трея на английском, уведомление «Ready. Hold …» после смены модели/языка приходит по-английски. Вернуть русский.

- [ ] **Step 7: Коммит**

```bash
git add molvi/app.py
git commit -m "feat(i18n): app — уведомления через tr(), инициализация и смена языка UI"
```

---

### Task 8: Английские страницы сайта (docs/site/en/)

**Files:**
- Create: `docs/site/en/index.html`, `docs/site/en/install.html`, `docs/site/en/install-mac.html`, `docs/site/en/geek/index.html`, `docs/site/en/geek/mac/index.html`

**Interfaces:**
- Consumes: русские страницы `docs/site/*.html`, `docs/site/geek/**` как источник структуры и контента.
- Produces: EN-страницы по тем же относительным путям под `en/`; Task 9 ссылается на них из hreflang RU-страниц.

Правила перевода (для каждой страницы):

- Скопировать RU-страницу в `en/<тот же путь>`, перевести ВЕСЬ видимый текст и meta на естественный маркетинговый английский (не дословно, но без отсебятины: те же факты, та же структура). Бренд «Molvi», названия продуктов (Wispr Flow, Aqua Voice, Claude Code, Whisper, faster-whisper, mlx-whisper) не переводить. HTML-структуру, CSS и JS не менять.
- `<html lang="ru">` → `<html lang="en">`.
- Относительные пути поправить на +1 уровень вложенности: в `en/index.html` `./assets/…` → `../assets/…`; в `en/geek/…` — проверить каждый `src`/`href` на разрешимость.
- Внутренние ссылки между страницами → на EN-версии (`install.html` → `/en/install.html` и т.д.). Кнопки «Скачать» (github.com/artanov/molvi/releases) — без изменений.
- Скриншоты остаются русскими (осознанно, см. спеку) — но `alt`-тексты перевести.
- Тексты `<script>`-анимаций (если печатают русские фразы в демо-поле) — перевести печатаемые фразы.

Точные title/description/OG (вставить как есть):

| Файл | `<title>` | `meta description` |
|---|---|---|
| `en/index.html` | `Molvi — voice typing for Windows and Mac, local and free` | `Molvi is local voice typing for Windows and macOS — a free alternative to Wispr Flow and Aqua Voice. Dictate into any window or terminal (Claude Code, Codex). Whisper runs on your computer: no cloud, no subscription.` |
| `en/install.html` | `How to install Molvi on Windows — step-by-step guide` | `How to install Molvi on Windows: the download, SmartScreen, the installer, the first-run wizard — what to choose and why. With screenshots of every step.` |
| `en/install-mac.html` | `How to install Molvi on Mac — step-by-step guide` | `How to install Molvi on macOS (Apple Silicon): DMG, Gatekeeper, the first-run wizard, the Input Monitoring and Accessibility permissions.` |
| `en/geek/index.html` | `molvi(1) — voice input for the terminal` | `The geek version of molvi.tech: a man page, a side-by-side diff with Wispr Flow and Aqua Voice, a 4-step install. Local voice typing for Windows and Claude Code.` |
| `en/geek/mac/index.html` | `molvi(1) for Mac — voice input in the terminal` | `The geek version of molvi.tech for macOS: a zsh session in Terminal.app, mlx-whisper on Metal, dictation with the right ⌘ into any window — local and free.` |

Для `en/index.html` дополнительно: `og:title` = `Molvi — speak, don't type`; `og:description` = `Local voice typing for Windows and macOS. No cloud, no subscription, open source.`; добавить `<meta property="og:locale" content="en_US">`.

hreflang-блок в `<head>` каждой EN-страницы (пример для `en/index.html`; на остальных — те же три строки с соответствующими путями, `x-default` всегда указывает на русскую версию):

```html
<link rel="canonical" href="https://molvi.tech/en/">
<link rel="alternate" hreflang="ru" href="https://molvi.tech/">
<link rel="alternate" hreflang="en" href="https://molvi.tech/en/">
<link rel="alternate" hreflang="x-default" href="https://molvi.tech/">
```

Пары путей: `/` ↔ `/en/`, `/install.html` ↔ `/en/install.html`, `/install-mac.html` ↔ `/en/install-mac.html`, `/geek/` ↔ `/en/geek/`, `/geek/mac/` ↔ `/en/geek/mac/`.

Переключатель языка на EN-страницах: в `.nav-links` (для geek-страниц — в аналогичном месте шапки, в стиле страницы) первой ссылкой:

```html
<a href="/" lang="ru" title="Русская версия">RU</a>
```

(на внутренних страницах — на соответствующую RU-страницу: `/install.html` и т.д.)

- [ ] **Step 1: Перевести `en/index.html`** по правилам выше.
- [ ] **Step 2: Перевести `en/install.html`** по правилам выше.
- [ ] **Step 3: Перевести `en/install-mac.html`** по правилам выше.
- [ ] **Step 4: Перевести `en/geek/index.html`** по правилам выше.
- [ ] **Step 5: Перевести `en/geek/mac/index.html`** по правилам выше.
- [ ] **Step 6: Проверка на остаточную кириллицу**

Run (Git Bash): `grep -rlP '[А-Яа-яЁё]' docs/site/en/ || echo CLEAN`
Expected: `CLEAN` (метка «RU» в переключателе — латиница, комментарии HTML перевести или убрать).

- [ ] **Step 7: Локальный просмотр** — `cd docs/site && ..\..\.venv\Scripts\python -m http.server 8080`, открыть `http://localhost:8080/en/` и все 4 внутренние страницы: вёрстка не поехала, картинки грузятся, ссылки ведут на EN-версии, переключатель RU ведёт на русскую страницу. Остановить сервер.

- [ ] **Step 8: Коммит**

```bash
git add docs/site/en/
git commit -m "site(en): англоязычная версия сайта — 5 страниц на molvi.tech/en/"
```

---

### Task 9: RU-страницы — hreflang и переключатель; sitemap; smoke-check

**Files:**
- Modify: `docs/site/index.html`, `docs/site/install.html`, `docs/site/install-mac.html`, `docs/site/geek/index.html`, `docs/site/geek/mac/index.html` (только `<head>` и шапка)
- Modify: `docs/site/sitemap.xml` (полная замена)
- Modify: `.github/workflows/deploy-site.yml:30-37`

**Interfaces:**
- Consumes: пары URL из Task 8.

- [ ] **Step 1: hreflang на RU-страницах** — в `<head>` каждой из 5 страниц (после `meta description`) вставить блок со СВОИМИ путями; для `index.html`:

```html
<link rel="canonical" href="https://molvi.tech/">
<link rel="alternate" hreflang="ru" href="https://molvi.tech/">
<link rel="alternate" hreflang="en" href="https://molvi.tech/en/">
<link rel="alternate" hreflang="x-default" href="https://molvi.tech/">
```

Для остальных — заменить пути по таблице пар из Task 8 (canonical — на саму RU-страницу).

- [ ] **Step 2: Переключатель EN на RU-страницах** — в `.nav-links` (geek-страницы — в шапке в стиле страницы) первой ссылкой, для `index.html`:

```html
<a href="/en/" lang="en" title="English version">EN</a>
```

(на внутренних — `/en/install.html`, `/en/install-mac.html`, `/en/geek/`, `/en/geek/mac/`).

- [ ] **Step 3: `docs/site/sitemap.xml`** — заменить целиком:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
        xmlns:xhtml="http://www.w3.org/1999/xhtml">
  <url>
    <loc>https://molvi.tech/</loc>
    <xhtml:link rel="alternate" hreflang="ru" href="https://molvi.tech/"/>
    <xhtml:link rel="alternate" hreflang="en" href="https://molvi.tech/en/"/>
    <lastmod>2026-07-15</lastmod>
    <priority>1.0</priority>
  </url>
  <url>
    <loc>https://molvi.tech/en/</loc>
    <xhtml:link rel="alternate" hreflang="ru" href="https://molvi.tech/"/>
    <xhtml:link rel="alternate" hreflang="en" href="https://molvi.tech/en/"/>
    <lastmod>2026-07-15</lastmod>
    <priority>1.0</priority>
  </url>
  <url>
    <loc>https://molvi.tech/install.html</loc>
    <xhtml:link rel="alternate" hreflang="ru" href="https://molvi.tech/install.html"/>
    <xhtml:link rel="alternate" hreflang="en" href="https://molvi.tech/en/install.html"/>
    <lastmod>2026-07-15</lastmod>
    <priority>0.8</priority>
  </url>
  <url>
    <loc>https://molvi.tech/en/install.html</loc>
    <xhtml:link rel="alternate" hreflang="ru" href="https://molvi.tech/install.html"/>
    <xhtml:link rel="alternate" hreflang="en" href="https://molvi.tech/en/install.html"/>
    <lastmod>2026-07-15</lastmod>
    <priority>0.8</priority>
  </url>
  <url>
    <loc>https://molvi.tech/install-mac.html</loc>
    <xhtml:link rel="alternate" hreflang="ru" href="https://molvi.tech/install-mac.html"/>
    <xhtml:link rel="alternate" hreflang="en" href="https://molvi.tech/en/install-mac.html"/>
    <lastmod>2026-07-15</lastmod>
    <priority>0.8</priority>
  </url>
  <url>
    <loc>https://molvi.tech/en/install-mac.html</loc>
    <xhtml:link rel="alternate" hreflang="ru" href="https://molvi.tech/install-mac.html"/>
    <xhtml:link rel="alternate" hreflang="en" href="https://molvi.tech/en/install-mac.html"/>
    <lastmod>2026-07-15</lastmod>
    <priority>0.8</priority>
  </url>
  <url>
    <loc>https://molvi.tech/geek/</loc>
    <xhtml:link rel="alternate" hreflang="ru" href="https://molvi.tech/geek/"/>
    <xhtml:link rel="alternate" hreflang="en" href="https://molvi.tech/en/geek/"/>
    <lastmod>2026-07-15</lastmod>
    <priority>0.5</priority>
  </url>
  <url>
    <loc>https://molvi.tech/en/geek/</loc>
    <xhtml:link rel="alternate" hreflang="ru" href="https://molvi.tech/geek/"/>
    <xhtml:link rel="alternate" hreflang="en" href="https://molvi.tech/en/geek/"/>
    <lastmod>2026-07-15</lastmod>
    <priority>0.5</priority>
  </url>
  <url>
    <loc>https://molvi.tech/geek/mac/</loc>
    <xhtml:link rel="alternate" hreflang="ru" href="https://molvi.tech/geek/mac/"/>
    <xhtml:link rel="alternate" hreflang="en" href="https://molvi.tech/en/geek/mac/"/>
    <lastmod>2026-07-15</lastmod>
    <priority>0.5</priority>
  </url>
  <url>
    <loc>https://molvi.tech/en/geek/mac/</loc>
    <xhtml:link rel="alternate" hreflang="ru" href="https://molvi.tech/geek/mac/"/>
    <xhtml:link rel="alternate" hreflang="en" href="https://molvi.tech/en/geek/mac/"/>
    <lastmod>2026-07-15</lastmod>
    <priority>0.5</priority>
  </url>
</urlset>
```

- [ ] **Step 4: Smoke-check в воркфлоу** — в конец шага `Smoke check` в `.github/workflows/deploy-site.yml` добавить:

```yaml
          code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 15 https://molvi.tech/en/)
          echo "https://molvi.tech/en/ → HTTP $code"
          test "$code" = "200"
```

- [ ] **Step 5: Локальная проверка** — снова `http.server`: с RU-главной клик EN → EN-главная, обратно RU; выборочно внутренние страницы. Проверить sitemap на well-formedness: `.venv\Scripts\python -c "import xml.etree.ElementTree as ET; ET.parse('docs/site/sitemap.xml'); print('OK')"` → `OK` (файл собственный, из репозитория — парсим только его, недоверенный XML сюда не попадает; defusedxml не тянем, чтобы не добавлять зависимость).

- [ ] **Step 6: Коммит**

```bash
git add docs/site/index.html docs/site/install.html docs/site/install-mac.html docs/site/geek/index.html docs/site/geek/mac/index.html docs/site/sitemap.xml .github/workflows/deploy-site.yml
git commit -m "site(seo): hreflang RU/EN, переключатель языка, sitemap с альтернативами, smoke-check /en/"
```

---

## Финальная проверка

- [ ] `.venv\Scripts\python -m pytest -q` — всё зелёное.
- [ ] `.venv\Scripts\python -m molvi.app` — переключение Русский ↔ English в настройках: трей, уведомления, повторно открытое окно настроек — на выбранном языке.
- [ ] Пуш в main → деплой сайта отработал, `https://molvi.tech/en/` отвечает 200, hreflang виден в исходнике страниц.
- [ ] Вне рамок (зафиксировано в спеке): английские скриншоты для EN-страниц — после релиза локализованного приложения.
