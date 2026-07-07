"""Определение NVIDIA-GPU через nvidia-smi и рекомендация модели."""
import logging
import subprocess

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
    """→ (model, device): NVIDIA с VRAM ≥ 6 ГБ → large-v3/auto, иначе base/cpu."""
    if gpu and gpu.get("vram_mb", 0) >= MIN_VRAM_MB:
        return "large-v3", "auto"
    return "base", "cpu"
