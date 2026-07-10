"""icon.png → molvi.icns для .app-бандла (Pillow умеет ICNS сам)."""
from pathlib import Path

from PIL import Image

src = Path(__file__).resolve().parents[1] / "molvi" / "assets" / "icon.png"
dst = Path(__file__).parent / "molvi.icns"
img = Image.open(src)
if img.size != (1024, 1024):  # ICNS хочет квадрат степени двойки
    img = img.resize((1024, 1024), Image.LANCZOS)
img.save(dst, sizes=[(16, 16), (32, 32), (64, 64), (128, 128),
                     (256, 256), (512, 512), (1024, 1024)])
print(f"wrote {dst}")
