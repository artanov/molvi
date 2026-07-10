# Порт Molvi на macOS — бриф для работы на маке

Статус: **не начат**. Железо: MacBook M1 (RAM уточнить: `sysctl -n hw.memsize`).
Написано сессией на Windows-машине 2026-07-10 — здесь всё, что я выяснил,
оценивая порт, чтобы сессия на маке не выясняла заново.

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
