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
    "tray.copy_last": "Скопировать последний текст",
    "tray.pause": "Пауза",
    "tray.resume": "Возобновить",
    "tray.quit": "Выход",
    # --- оверлей (текстовый fallback) ---
    "overlay.recording": "●  Запись…",
    "overlay.transcribing": "⏳  Распознаю…",
    "overlay.eta": "~{sec} с",
    # --- controller ---
    "controller.mic_unavailable": "Микрофон недоступен: {exc}",
    "controller.record_error": "Ошибка записи: {exc}",
    "controller.transcribe_error": "Ошибка распознавания: {exc}",
    "controller.paste_error": ("Не удалось вставить текст: {exc}. Распознанный "
                               "текст — в буфере обмена ({paste_hint})."),
    "controller.target_lost": ("Не удалось вернуться в исходное окно — "
                               "текст в трее («Скопировать последний текст»)."),
    "controller.paste_cancelled": ("Вставка отменена — текст в трее "
                                   "(«Скопировать последний текст»)."),
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
    "app.notify.copied": "Текст скопирован в буфер обмена",
    "app.notify.copy_failed": "Не удалось скопировать: {exc}",
    "app.notify.nothing_to_copy": "Пока нечего копировать — продиктуйте что-нибудь",
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
    "tray.copy_last": "Copy last transcript",
    "tray.pause": "Pause",
    "tray.resume": "Resume",
    "tray.quit": "Quit",
    "overlay.recording": "●  Recording…",
    "overlay.transcribing": "⏳  Transcribing…",
    "overlay.eta": "~{sec}s",
    "controller.mic_unavailable": "Microphone unavailable: {exc}",
    "controller.record_error": "Recording error: {exc}",
    "controller.transcribe_error": "Recognition error: {exc}",
    "controller.paste_error": ("Couldn't paste the text: {exc}. The recognized "
                               "text is in the clipboard ({paste_hint})."),
    "controller.target_lost": ("Couldn't switch back to the original window — "
                               "the text is in the tray (\"Copy last transcript\")."),
    "controller.paste_cancelled": ("Paste cancelled — the text is in the tray "
                                   "(\"Copy last transcript\")."),
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
    "app.notify.copied": "Text copied to clipboard",
    "app.notify.copy_failed": "Copy failed: {exc}",
    "app.notify.nothing_to_copy": "Nothing to copy yet — dictate something first",
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
