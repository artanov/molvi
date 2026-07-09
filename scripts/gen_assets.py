"""Генерирует звуковые ассеты: start.wav/stop.wav (синус-тики).

Пилюля оверлея с v1.2 рисуется на лету (molvi/overlay.py) — PNG не нужны.
Запуск: .venv/Scripts/python scripts/gen_assets.py
"""
import math
import struct
import wave
from pathlib import Path

ASSETS = Path(__file__).resolve().parents[1] / "molvi" / "assets"
ASSETS.mkdir(exist_ok=True)


def make_wav(path, freq, ms=70, rate=22050, volume=0.35):
    n = int(rate * ms / 1000)
    frames = bytearray()
    for i in range(n):
        fade = min(1.0, (n - i) / (n * 0.4), i / (n * 0.1) if n else 1.0)
        val = int(32767 * volume * fade * math.sin(2 * math.pi * freq * i / rate))
        frames += struct.pack("<h", val)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(frames))
    print(f"wrote {path}")


make_wav(ASSETS / "start.wav", freq=880)
make_wav(ASSETS / "stop.wav", freq=523)
