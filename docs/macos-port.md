# Порт Molvi на macOS — бриф для работы на маке

Статус: **фазы 0–1 сделаны** (2026-07-10, сессия на маке). Железо:
MacBook Pro M1, **8 ГБ RAM**, macOS 15.3.
Написано сессией на Windows-машине 2026-07-10; обновляется по ходу порта.

- Фаза 0 ✅ — платформенный слой `molvi/platform/{win32,darwin}`; pytest на
  маке зелёный, win-тесты скипаются.
- Фаза 1 ✅ — движок выбран: **mlx-whisper + large-v3-turbo** (бенчмарк ниже);
  обёртка `molvi/platform/darwin/transcriber.py`, дефолты/пресеты/рекомендации
  обновлены. ВАЖНО: distil-large-v3 из первоначального плана не годится — он
  English-only, а нам нужен русский.
- Фаза 2 ✅ — event tap (ListenOnly; модификаторы из flagsChanged по
  device-битам; свои Cmd+V метятся kCGEventSourceUserData=INJECT_MAGIC),
  вставка NSPasteboard+CGEventPost, activationPolicy Accessory (фокус не
  крадётся, Dock-иконки нет), LaunchAgent, TCC-шаг в мастере
  (CGPreflight/CGRequest*Access). Грабли: winfo_id на маке — НЕ NSView,
  оборачивать в objc нельзя (segfault); NSWindow.level не трогаем,
  tk -topmost достаточно. capslock исключён из таблицы клавиш (toggle).
- Фаза 3 ✅ — molvi-mac.spec (.app: LSUIElement, NSMicrophoneUsageDescription,
  bundle id tech.molvi.app), build-mac.sh (DMG через hdiutil), CI-джобы
  test-mac/build-mac (macos-14) + DMG в релизе. Грабли: в entry.py обязателен
  multiprocessing.freeze_support() — иначе resource_tracker на маке
  перезапускает весь бандл; torch исключён (нужен mlx_whisper только для
  конвертации весов).

После мультиагентного ревью порта дочинено: импорт autostart в migrate.py
(терялся автозапуск при миграции VoiceFlow на Windows), VAD-эквивалент для
mlx (фильтр сегментов по no_speech_prob/avg_logprob — у mlx-whisper нет
vad_filter), preflight Accessibility перед Cmd+V (иначе CGEventPost молча
глотается и буфер затирает распознанное), анти-зависание захвата хоткея при
мёртвом event tap (listener.dead), единый каталог моделей
platform/darwin/models.py (fetch и transcriber больше не разъедутся),
WorkingDirectory в dev-LaunchAgent, ленивый molvi.platform (Quartz не
грузится ради звука).

Известные компромиссы (сознательно не трогаем):
- Смена модели на mlx кратко держит две модели в unified memory (как VRAM-
  замечание в app.py) — на 8 ГБ при turbo+small это ок; ModelHolder mlx
  кэширует одну модель, после отката первая диктовка перечитает веса с диска.
- Звуки на маке — afplay-процесс (~100 мс задержки сигнала); NSSound
  in-process — возможная полировка.
- paste/insert-логика продублирована в win32/darwin typer (генерализация в
  ядро — отдельная задача; поведение зафиксировано парными тестами).

Осталось владельцу: живая проверка диктовки с реальными TCC-разрешениями,
страница «Molvi для Mac» на сайте после первого релиза с DMG, решение о
нотаризации (Apple Developer, $99/год).

## Бенчмарк движков (M1 8 ГБ, русская фраза 10.9 с, TTS Milena)

| Движок | Модель | Тёплая расшифровка | RTF | Пик RSS | Текст |
|---|---|---|---|---|---|
| mlx-whisper 0.4.3 | large-v3-turbo | **1.9 с** | 0.18 | 0.7 ГБ | идеально |
| pywhispercpp 1.5.0 | large-v3-turbo | 2.1 с | 0.19 | 0.7 ГБ | идеально |
| faster-whisper CPU int8 | small | 3.6 с | 0.33 | 1.2 ГБ | идеально |

Выбор: mlx-whisper — паритет по скорости с whisper.cpp, но чистый Python
(проще PyInstaller-сборка) и веса через тот же HF-кэш, что у fetch.py.
large-v3 (не turbo) на 8 ГБ не пробовали и не нужно: turbo даёт качество
уровня large при 0.7 ГБ. Прогрев модели при старте ~15 с (в конструкторе
обёртки — первая диктовка не ждёт).

## Первые шаги на маке

1. `python3 --version` (нужен 3.12+; ставить через brew, если старый).
2. `python3 -m venv .venv && .venv/bin/pip install -r requirements-base.txt pytest`
   — **упадёт на pywin32**: он win-only. Начни с фазы 0 (см. ниже), либо
   поставь пакеты выборочно без pywin32.
3. `pytest -q` сейчас на маке **упадёт на импортах** (`ctypes.windll`,
   `win32clipboard`, `winreg`, `winsound`) — это ожидаемо и есть первая задача.

## План по фазам

### Фаза 0 — платформенный слой (можно на любой ОС)
Вынести платформенное за интерфейсы, не меняя поведение Windows-версии:
```
molvi/platform/__init__.py   # выбор реализации по sys.platform
molvi/platform/win32/...     # текущий код hotkey/typer/autostart/sounds
molvi/platform/darwin/...    # заглушки → реализации в фазе 2
```
Критерий: на Windows все тесты зелёные как раньше; на маке `pytest` собирает
и проходит кроссплатформенные тесты (win-специфичные — `skipif sys.platform`).

### Фаза 1 — спайк движка (главный риск, делать рано)
ctranslate2 (наш faster-whisper) на Apple Silicon — **CPU-only**, large-v3
будет мучительно медленным. Кандидаты с Metal/ANE:
- `mlx-whisper` (Apple MLX) — родной для M-чипов;
- `pywhispercpp` (whisper.cpp + Metal).

Бенчмарк на реальном M1: WER на русской речи + секунды на 10-сек фразу
для large-v3 и medium. Интерфейс для обёртки уже тонкий (см. `transcriber.py`):
`__init__(model, device, compute_type, language)`, `transcribe(np.float32 mono
16kHz) -> str`, `set_language(str)`. Если large-v3 не тянет по RAM/скорости —
дефолт medium/distil, качество проверить ушами.

### Фаза 2 — darwin-реализации
| Модуль | Что делать | Грабли |
|---|---|---|
| hotkey | Quartz Event Tap (pynput или PyObjC). **Сохранить нашу логику** armed/полного отпускания/анти-автоповтора (`hotkey.py`, покрыта `test_hotkey.py` — тесты платформонезависимы, гонять их против новой обвязки) | Наш Ctrl+V-инжект не должен дёргать PTT: на Windows фильтруем LLKHF_INJECTED; на маке смотреть `kCGEventSourceStateID`/`CGEventSourceGetSourceStateID` — исследовать |
| typer | paste: NSPasteboard + CGEventPost(Cmd+V); посимвольно: `CGEventKeyboardSetUnicodeString` (умеет юникод сразу, суррогатный костыль не нужен) | Восстановление pasteboard после вставки — как в win-версии |
| overlay | tk на маке: `-transparentcolor` **не существует**. Путь: `root.attributes('-transparent', True)` + `bg='systemTransparent'` + overrideredirect; уровень поверх окон через PyObjC (NSWindow.level) | Не красть фокус: на маке это NSApp activationPolicy, а не WS_EX_NOACTIVATE. Логика эквалайзера (`bar_heights`, envelope) переносится как есть |
| autostart | LaunchAgent plist `~/Library/LaunchAgents/tech.molvi.app.plist` | — |
| sounds | `afplay` subprocess или NSSound | winsound-флаги убрать за интерфейс |
| paths | `~/Library/Application Support/Molvi` | migrate.py — win-only, на маке no-op |
| gpu.py | не нужен (нет NVIDIA); `recommend()` для мака: модель по RAM | — |

**Разрешения TCC** (ключевой UX): Microphone (спросит система), Input
Monitoring (event tap), Accessibility (CGEventPost). В dev-режиме разрешения
выдаются Терминалу. В мастер добавить экраны «выдай разрешение → кнопка
открыть System Settings» (`x-apple.systempreferences:com.apple.preference.security?Privacy_...`).

### Фаза 3 — дистрибуция
PyInstaller `.app` + DMG; CI job на `macos-14` (arm64). Gatekeeper: без
подписи пользователю нужно right-click→Open или `xattr -cr` — задокументировать
на сайте; нотаризация (Apple Developer, $99/год) — отдельное решение владельца.

## Что НЕ трогать

- `controller.py`, `config.py`, `fetch.py`, логика `wizard/settings` — кроссплатформенны.
- Протокол перезагрузки модели с токенами (controller+app) — хрупкое место,
  покрыто тестами, не переписывать.
- Windows-поведение и релизный процесс — порт не должен ничего сломать
  (CI Windows-job обязан оставаться зелёным на каждом коммите порта).

## Контекст владельца

- Основная машина — Windows (2×2560 монитора), там же прод-установка Molvi.
- Хоткей пользователя: Shift+Ctrl; на маке продумать дефолт (правый Cmd?
  Ctrl конфликтует с системными жестами меньше, чем на Windows).
- Сайт molvi.tech деплоится сам при пуше `docs/site/**` в main — страницу
  «Molvi для Mac» добавлять только когда будет рабочий DMG.
