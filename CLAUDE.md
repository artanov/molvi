# Molvi — заметки для Claude

Локальный голосовой ввод (аналог Wispr Flow): зажал хоткей → говоришь → отпустил →
текст напечатан в активное окно. Python 3.13, faster-whisper (large-v3/CUDA на
Windows), tkinter (оверлей/настройки/мастер), pystray (трей). Всё локально,
без телеметрии. Сайт: https://molvi.tech (исходник в `docs/site/`, автодеплой
из GitHub Actions при пуше в main).

## Работаешь на macOS?

Порт готов (фазы 0–3), детали и грабли — в **`docs/macos-port.md`**.
Движок на маке — mlx-whisper (large-v3-turbo), платформенное — в
`molvi/platform/darwin/`.

## Структура

- `molvi/controller.py` — оркестрация hotkey→запись→ASR→вставка (кроссплатформенный)
- `molvi/hotkey.py` — ядро push-to-talk: автомат комбо + таблицы клавиш (кроссплатформенное)
- `molvi/platform/` — платформенный слой, выбор по sys.platform:
  - `win32/` — WinAPI-хук, Ctrl+V/SendInput, winreg-автозапуск, winsound, `-transparentcolor`
  - `darwin/` — Quartz event tap, NSPasteboard+Cmd+V, LaunchAgent, afplay,
    альфа-прозрачность, mlx-обёртка транскрайбера
- `molvi/overlay.py` — пилюля с живым эквалайзером, tkinter (платформенное — за интерфейсом)
- `molvi/transcriber.py` — обёртка faster-whisper + проверка CUDA-DLL (Windows)
- `molvi/recorder.py` — запись с микрофона + RMS-уровень для эквалайзера
- `molvi/wizard.py` — мастер первого запуска (на маке + шаг разрешений TCC);
  `molvi/settings.py` — окно настроек
- `molvi/theme.py` — палитра бренда (единый источник, совпадает с CSS сайта)
- `packaging/` — PyInstaller spec'и (`molvi.spec` win, `molvi-mac.spec` mac),
  Inno Setup, `build-mac.sh` (DMG); `docs/site/` — сайт

## Команды

Windows:

```
.venv\Scripts\python -m pytest -q          # тесты (135+, должны быть зелёными)
.venv\Scripts\python -m molvi.app          # запуск в dev-режиме
packaging\build.bat                        # локальная frozen-сборка
```

macOS:

```
.venv/bin/python -m pytest -q              # тесты (win-специфичные скипаются)
.venv/bin/python -m molvi.app              # запуск в dev-режиме
packaging/build-mac.sh                     # локальная сборка .app + DMG
```

## Процессы

- **Релиз**: тег `v*` → GitHub Actions собирает установщик и публикует релиз.
  Перед тегом CI должен быть зелёным (тесты + frozen-сборка + smoke).
- **Сайт**: правки в `docs/site/**` → push в main → автодеплой на molvi.tech.
- Версии зависимостей запинены (`requirements-base.txt`) — поднимать осознанно.
- Коммиты и комментарии в коде — по-русски; комментарии объясняют «почему», не «что».

## SMM

Продвижением занимается SMM-агент: база знаний — `docs/smm/` (локальная,
в .gitignore), персона — `.claude/agents/smm-manager.md`, ежедневный запуск —
задача планировщика Windows «Molvi SMM Daily» в 10:00
(`docs/smm/run-daily.cmd` → `docs/smm/daily-prompt.md`). Сообщения из Telegram
про публикации и правки постов — это ответы SMM-агенту: действуй по его персоне
и обновляй журнал `docs/smm/log.md`.
