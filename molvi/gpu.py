"""Определение NVIDIA-GPU через nvidia-smi и рекомендация модели."""
import logging
import subprocess
import sys

log = logging.getLogger(__name__)

MIN_VRAM_MB = 6000


def detect_nvidia():
    """→ {"name": str, "vram_mb": int} или None, если NVIDIA не найдена."""
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0 or not out.stdout.strip():
        return None
    first = out.stdout.strip().splitlines()[0]
    name, sep, mem = first.rpartition(",")
    if not sep:
        return None
    try:
        return {"name": name.strip(), "vram_mb": int(mem.strip())}
    except ValueError:
        return None


def recommend(gpu):
    """→ (model, device): NVIDIA с VRAM ≥ 6 ГБ → large-v3/auto, иначе base/cpu.

    На маке — всегда large-v3-turbo: mlx-whisper через Metal тянет её даже
    на M1 с 8 ГБ (RTF ~0.2, пик памяти 0.7 ГБ — бенчмарк в docs/macos-port.md)."""
    if sys.platform == "darwin":
        return "large-v3-turbo", "auto"
    if gpu and gpu.get("vram_mb", 0) >= MIN_VRAM_MB:
        return "large-v3", "auto"
    return "base", "cpu"
