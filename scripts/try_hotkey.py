"""Ручная проверка хука: зажмите/отпустите правый Ctrl, Ctrl+C для выхода."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from molvi.hotkey import HotkeyListener

hl = HotkeyListener(
    on_press=lambda: print("PRESS  (запись бы началась)"),
    on_release=lambda: print("RELEASE (распознавание бы началось)"),
)
print("Слушаю правый Ctrl... Ctrl+C — выход.")
try:
    hl.run()
except KeyboardInterrupt:
    pass
