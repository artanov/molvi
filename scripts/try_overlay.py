"""Ручная проверка: оверлей показывает запись → распознавание → скрывается.
Проверить, что фокус НЕ уходит из активного окна (курсор в Блокноте должен мигать)."""
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from molvi.overlay import Overlay

ov = Overlay()


def scenario():
    time.sleep(1)
    ov.show_recording()
    time.sleep(2)
    ov.show_transcribing()
    time.sleep(2)
    ov.hide()
    time.sleep(1)
    ov.schedule_quit()


threading.Thread(target=scenario, daemon=True).start()
ov.run()
print("OK")
