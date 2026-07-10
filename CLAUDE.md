# Molvi — заметки для Claude

Локальный голосовой ввод (аналог Wispr Flow): зажал хоткей → говоришь → отпустил →
текст напечатан в активное окно. Python 3.13, faster-whisper (large-v3/CUDA на
Windows), tkinter (оверлей/настройки/мастер), pystray (трей). Всё локально,
без телеметрии. Сайт: https://molvi.tech (исходник в `docs/site/`, автодеплой
из GitHub Actions при пуше в main).

## Работаешь на macOS?

Читай **`docs/macos-port.md`** — там полный бриф порта: что переносимо,
что переписывать, известные грабли и порядок работ. Windows-специфичные
модули (`hotkey`, `typer`, `autostart`, win-часть `overlay`) на маке не
импортируются — это ожидаемо, начни с брифа.

## Структура

- `molvi/controller.py` — оркестрация hotkey→запись→ASR→вставка (кроссплатформенный)
- `molvi/hotkey.py` — глобальный push-to-talk, WinAPI low-level hook (win-only)
- `molvi/typer.py` — вставка текста: Ctrl+V или посимвольно в консоль (win-only)
- `molvi/overlay.py` — пилюля с живым эквалайзером, tkinter (`-transparentcolor` — win-only)
- `molvi/transcriber.py` — обёртка faster-whisper + проверка CUDA-DLL
- `molvi/recorder.py` — запись с микрофона + RMS-уровень для эквалайзера
- `molvi/wizard.py` — мастер первого запуска; `molvi/settings.py` — окно настроек
- `molvi/theme.py` — палитра бренда (единый источник, совпадает с CSS сайта)
- `packaging/` — PyInstaller spec + Inno Setup; `docs/site/` — сайт

## Команды

```
.venv\Scripts\python -m pytest -q          # тесты (112+, должны быть зелёными)
.venv\Scripts\python -m molvi.app          # запуск в dev-режиме
packaging\build.bat                        # локальная frozen-сборка
```

## Процессы

- **Релиз**: тег `v*` → GitHub Actions собирает установщик и публикует релиз.
  Перед тегом CI должен быть зелёным (тесты + frozen-сборка + smoke).
- **Сайт**: правки в `docs/site/**` → push в main → автодеплой на molvi.tech.
- Версии зависимостей запинены (`requirements-base.txt`) — поднимать осознанно.
- Коммиты и комментарии в коде — по-русски; комментарии объясняют «почему», не «что».
