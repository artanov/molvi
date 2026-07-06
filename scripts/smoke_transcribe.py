"""Ручная проверка: записывает 4 секунды с микрофона и распознаёт на GPU.

Первый запуск скачивает модель large-v3 (~3 ГБ) с HuggingFace.
Запуск: .venv/Scripts/python scripts/smoke_transcribe.py
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import sounddevice as sd

from voiceflow.recorder import Recorder
from voiceflow.transcriber import Transcriber

print("Загружаю модель (первый раз — скачивание ~3 ГБ)...")
t0 = time.time()
tr = Transcriber("large-v3", "auto", "int8_float16", "auto")
print(f"Модель загружена за {time.time() - t0:.1f} c, устройство: {tr.device}")

rec = Recorder()
print("Говорите — записываю 4 секунды...")
rec.start()
sd.sleep(4000)
audio = rec.stop()
print(f"Записано {len(audio) / 16000:.1f} c")

t0 = time.time()
text = tr.transcribe(audio)
print(f"Распознано за {time.time() - t0:.1f} c: {text!r}")
