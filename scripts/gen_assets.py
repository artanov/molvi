"""Генерирует ассеты: start.wav/stop.wav (синус-тики) и PNG-плейсхолдеры оверлея.

PNG — временные заглушки; пользователь заменит их картинками из Gemini
(400x128, RGBA, те же имена). Запуск: .venv/Scripts/python scripts/gen_assets.py
"""
import math
import struct
import sys
import wave
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ASSETS = Path(__file__).resolve().parents[1] / "voiceflow" / "assets"
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


def make_png(path, bg, icon, text):
    img = Image.new("RGBA", (400, 128), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, 399, 127), radius=64, fill=bg)
    if icon == "dot":
        d.ellipse((36, 44, 76, 84), fill="white")
    else:  # hourglass
        d.polygon([(40, 40), (72, 40), (56, 64), (40, 88), (72, 88), (56, 64)], fill="white")
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/segoeuib.ttf", 40)
    except OSError:
        font = ImageFont.load_default()
    d.text((100, 64), text, fill="white", font=font, anchor="lm")
    img.save(path)
    print(f"wrote {path}")


make_wav(ASSETS / "start.wav", freq=880)
make_wav(ASSETS / "stop.wav", freq=523)
make_png(ASSETS / "recording.png", (192, 57, 43, 235), "dot", "Запись…")
make_png(ASSETS / "transcribing.png", (44, 62, 80, 235), "hourglass", "Распознаю…")
