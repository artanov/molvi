"""Докачка тяжёлых компонентов: CUDA-DLL (wheels с PyPI) и модели Whisper (HF-кэш)."""
import json
import logging
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

log = logging.getLogger(__name__)

CUDA_PACKAGES = ("nvidia-cublas-cu12", "nvidia-cudnn-cu12")

MODEL_REPOS = {
    "large-v3": "Systran/faster-whisper-large-v3",
    "small": "Systran/faster-whisper-small",
    "base": "Systran/faster-whisper-base",
}
MODEL_SIZES = {  # примерный полный размер, байты — для прогресса по росту кэша
    "large-v3": 3_100_000_000,
    "small": 490_000_000,
    "base": 150_000_000,
}


def _version_key(v):
    parts = []
    for p in v.split("."):
        try:
            parts.append(int(p))
        except ValueError:
            parts.append(0)
    return parts


def pick_wheel_url(pypi_json):
    """Из ответа PyPI JSON API — URL win_amd64-wheel самой новой версии, где он есть."""
    releases = pypi_json["releases"]
    for version in sorted(releases, key=_version_key, reverse=True):
        for f in releases[version]:
            if f["filename"].endswith("win_amd64.whl") and not f.get("yanked"):
                return f["url"]
    raise LookupError("win_amd64 wheel не найден")


def download(url, dest, progress_cb=None, chunk=1 << 18):
    """Скачать url в dest; progress_cb(done_bytes, total_bytes). Частичный файл удаляется."""
    dest = Path(dest)
    req = urllib.request.Request(url, headers={"User-Agent": "VoiceFlow"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp, open(dest, "wb") as f:
            total = int(resp.headers.get("Content-Length") or 0)
            done = 0
            while True:
                block = resp.read(chunk)
                if not block:
                    break
                f.write(block)
                done += len(block)
                if progress_cb:
                    progress_cb(done, total)
    except Exception:
        dest.unlink(missing_ok=True)
        raise


def extract_dlls(wheel_path, target_dir):
    """Распаковать все */bin/*.dll из wheel (это zip) в target_dir; → имена файлов."""
    target = Path(target_dir)
    target.mkdir(parents=True, exist_ok=True)
    names = []
    with zipfile.ZipFile(wheel_path) as z:
        for info in z.infolist():
            p = PurePosixPath(info.filename)
            if p.suffix.lower() == ".dll" and p.parent.name == "bin":
                (target / p.name).write_bytes(z.read(info))
                names.append(p.name)
    return sorted(names)


def fetch_cuda(target_dir, tmp_dir, progress_cb=None):
    """Скачать оба nvidia-пакета и извлечь DLL; progress_cb(pkg, done, total)."""
    for pkg in CUDA_PACKAGES:
        with urllib.request.urlopen(
            f"https://pypi.org/pypi/{pkg}/json", timeout=30
        ) as resp:
            meta = json.load(resp)
        url = pick_wheel_url(meta)
        whl = Path(tmp_dir) / f"{pkg}.whl"
        try:
            download(url, whl,
                     (lambda d, t: progress_cb(pkg, d, t)) if progress_cb else None)
            extract_dlls(whl, target_dir)
        finally:
            whl.unlink(missing_ok=True)


def hf_cache_size():
    """Суммарный размер кэша HuggingFace в байтах (для прогресса модели)."""
    from huggingface_hub.constants import HF_HUB_CACHE
    root = Path(HF_HUB_CACHE)
    if not root.exists():
        return 0
    return sum(f.stat().st_size for f in root.rglob("*") if f.is_file())


def fetch_model(model):
    """Скачать модель в стандартный HF-кэш (блокирующая)."""
    from huggingface_hub import snapshot_download
    snapshot_download(MODEL_REPOS[model])
