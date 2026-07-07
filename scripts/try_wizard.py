"""Ручной прогон мастера БЕЗ записи config.json.
Запуск: .venv/Scripts/python scripts/try_wizard.py — пройдите шаги, закройте.
"""
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
logging.basicConfig(level=logging.INFO)

from voiceflow.wizard import Wizard

cfg = Wizard().run()
print("Итоговый cfg:", {k: cfg[k] for k in ("model", "device", "input_device", "hotkey")})
