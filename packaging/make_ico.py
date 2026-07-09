"""icon.png → molvi.ico (мультиразмер) для exe и установщика."""
from pathlib import Path

from PIL import Image

src = Path(__file__).resolve().parents[1] / "molvi" / "assets" / "icon.png"
dst = Path(__file__).parent / "molvi.ico"
Image.open(src).save(dst, sizes=[(16, 16), (24, 24), (32, 32), (48, 48),
                                 (64, 64), (128, 128), (256, 256)])
print(f"wrote {dst}")
