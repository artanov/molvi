# VoiceFlow

Локальный аналог Wispr Flow для Windows: зажмите **правый Ctrl**, говорите,
отпустите — текст напечатается в активном окне. Распознавание — Whisper large-v3
локально на GPU (faster-whisper/CUDA), без облака и подписок.

## Установка

```
py -3.13 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

Первый запуск скачает модель (~3 ГБ).

## Запуск

Двойной клик по `voiceflow.bat` (или `.venv\Scripts\python -m voiceflow.app` для
запуска с консолью и видимыми ошибками). Иконка появится в трее; после
уведомления «Готов» можно диктовать.

## Автозагрузка

Win+R → `shell:startup` → создать там ярлык на `voiceflow.bat`.

## Настройка — config.json

| Ключ | По умолчанию | Значения |
|---|---|---|
| model | large-v3 | любая модель faster-whisper |
| device | auto | auto / cuda / cpu |
| compute_type | int8_float16 | float16, int8, … |
| language | auto | auto / ru / en |
| min_duration_sec | 0.3 | минимальная длительность записи |
| paste_mode | clipboard | clipboard (Ctrl+V) / type (посимвольно) |
| input_device | null | имя или индекс микрофона (см. `python -m sounddevice`) |
| samplerate | 16000 | не менять без необходимости |

## Диагностика

Ошибки пишутся в `voiceflow.log`. Если распознавание медленное — проверьте в логе,
что устройство `cuda`, а не `cpu`.
