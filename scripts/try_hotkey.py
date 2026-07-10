"""Ручная проверка хука: зажмите/отпустите хоткей по умолчанию, Ctrl+C для выхода."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from molvi.platform import hotkey as hk

hl = hk.HotkeyListener(
    on_press=lambda: print("PRESS  (запись бы началась)"),
    on_release=lambda: print("RELEASE (распознавание бы началось)"),
    combo=hk.names_to_vks(hk.DEFAULT_HOTKEY),
)
print(f"Слушаю {hk.human_label(hk.DEFAULT_HOTKEY)}... Ctrl+C — выход.")
try:
    hl.run()
except KeyboardInterrupt:
    pass
