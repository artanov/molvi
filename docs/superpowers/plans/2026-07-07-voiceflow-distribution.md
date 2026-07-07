# VoiceFlow Distribution (спека B) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Установщик VoiceFlow-Setup.exe (~100–150 МБ) + мастер первого запуска + публичный GitHub с автосборкой релизов — приложение для людей без Python.

**Architecture:** PyInstaller (onedir, windowed) замораживает приложение; Inno Setup заворачивает в per-user установщик (`%LOCALAPPDATA%`, без админ-прав). Новый `paths.py` разводит dev/frozen пути (frozen-данные в `%APPDATA%\VoiceFlow`). Мастер (`wizard.py`, tkinter) при отсутствии config.json: GPU-детект → докачка CUDA-DLL (wheels с PyPI) и модели (HF-кэш) → микрофон с индикатором уровня → hotkey. GitHub Actions: тесты на push, установщик + Release на тег `v*`.

**Tech Stack:** как V2 + PyInstaller>=6, Inno Setup 6 (iscc), huggingface_hub (уже есть как зависимость faster-whisper), GitHub Actions (windows-latest), gh CLI.

## Global Constraints

- Спека: `docs/superpowers/specs/2026-07-07-voiceflow-distribution-design.md` — точные значения оттуда.
- Установщик БЕЗ nvidia-пакетов и моделей; PrivilegesRequired=lowest; DefaultDirName `{localappdata}\VoiceFlow`; деинсталлятор спрашивает про удаление `%APPDATA%\VoiceFlow`.
- Frozen-данные: config/лог в `%APPDATA%\VoiceFlow\`, докачанные DLL в `%APPDATA%\VoiceFlow\cuda\`, модели — стандартный HF-кэш. Dev-режим (venv) не меняется: всё в корне репозитория.
- Рекомендация железа: NVIDIA с VRAM ≥ 6000 МБ → large-v3/auto; иначе base/cpu.
- CUDA-докачка: win_amd64-wheels `nvidia-cublas-cu12`, `nvidia-cudnn-cu12` с PyPI JSON API; wheel=zip; извлекаются только `*/bin/*.dll`; частичные скачивания удаляются.
- Ошибки мастера не роняют запуск: log + дефолты; закрытие крестиком = дефолты выбранного шага.
- Автозапуск-команда: frozen → `sys.executable`, dev → `<repo>/voiceflow.bat` (и в настройках, и в Inno-галочке — одно и то же значение реестра `VoiceFlow`).
- Все команды — Git Bash из `F:/voiceflow`; тесты `.venv/Scripts/python -m pytest`; сейчас 63 passed. PowerShell-инструмент сломан — только Bash.
- Живой экземпляр VoiceFlow не трогать; смок замороженного exe создаёт СВОЙ лог в %APPDATA% и не конфликтует.
- Коммиты с трейлером `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

## File Structure

```
voiceflow/paths.py        # Task 1 (create): dev/frozen пути + autostart_command
voiceflow/gpu.py          # Task 2 (create): detect_nvidia(), recommend()
voiceflow/fetch.py        # Task 3 (create): wheels PyPI + DLL + модель + размеры
voiceflow/wizard.py       # Task 4 (create): мастер первого запуска
voiceflow/app.py          # Task 1, 4 (modify): paths, запуск мастера
voiceflow/transcriber.py  # Task 1 (modify): cuda_dir() в поиск DLL
packaging/entry.py        # Task 5 (create)
packaging/make_ico.py     # Task 5 (create)
packaging/voiceflow.spec  # Task 5 (create)
packaging/installer.iss   # Task 5 (create)
packaging/build.bat       # Task 5 (create)
requirements-ci.txt       # Task 6 (create): зависимости без nvidia (для CI)
.github/workflows/ci.yml       # Task 6 (create)
.github/workflows/release.yml  # Task 6 (create)
README.md                 # Task 6 (modify): раздел «Установка (для пользователей)»
scripts/try_wizard.py     # Task 4 (create): ручной прогон мастера
tests/test_paths.py       # Task 1
tests/test_gpu.py         # Task 2
tests/test_fetch.py       # Task 3
```

---

### Task 1: paths.py — dev/frozen пути

**Files:**
- Create: `voiceflow/paths.py`
- Modify: `voiceflow/app.py` (все использования `ROOT`), `voiceflow/transcriber.py` (`_add_cuda_dll_dirs`)
- Test: `tests/test_paths.py`

**Interfaces:**
- Produces: `is_frozen() -> bool`; `repo_root() -> Path`; `data_dir() -> Path` (создаёт каталог); `config_path() -> Path`; `log_path() -> Path`; `cuda_dir() -> Path` (НЕ создаёт); `autostart_command() -> str`.

- [ ] **Step 1: Написать падающий тест**

`tests/test_paths.py`:
```python
import sys
from pathlib import Path

import voiceflow.paths as paths


def test_dev_mode_uses_repo_root(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert paths.is_frozen() is False
    root = paths.repo_root()
    assert (root / "voiceflow").is_dir()
    assert paths.config_path() == root / "config.json"
    assert paths.log_path() == root / "voiceflow.log"
    assert paths.cuda_dir() == root / "cuda"
    assert paths.autostart_command() == str(root / "voiceflow.bat")


def test_frozen_mode_uses_appdata(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", r"C:\Apps\VoiceFlow\VoiceFlow.exe", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert paths.is_frozen() is True
    d = paths.data_dir()
    assert d == tmp_path / "VoiceFlow"
    assert d.is_dir()  # data_dir создаёт каталог
    assert paths.config_path() == d / "config.json"
    assert paths.cuda_dir() == d / "cuda"
    assert not paths.cuda_dir().exists()  # cuda_dir НЕ создаёт
    assert paths.autostart_command() == r"C:\Apps\VoiceFlow\VoiceFlow.exe"
```

- [ ] **Step 2: Убедиться, что падает** — `.venv/Scripts/python -m pytest tests/test_paths.py -v` → FAIL `ModuleNotFoundError`

- [ ] **Step 3: Реализация**

`voiceflow/paths.py`:
```python
"""Пути данных: dev-режим — корень репозитория, frozen (PyInstaller) — %APPDATA%."""
import os
import sys
from pathlib import Path

APP_NAME = "VoiceFlow"


def is_frozen():
    return bool(getattr(sys, "frozen", False))


def repo_root():
    return Path(__file__).resolve().parents[1]


def data_dir():
    if is_frozen():
        base = Path(os.environ.get("APPDATA", str(Path.home()))) / APP_NAME
    else:
        base = repo_root()
    base.mkdir(parents=True, exist_ok=True)
    return base


def config_path():
    return data_dir() / "config.json"


def log_path():
    return data_dir() / "voiceflow.log"


def cuda_dir():
    return data_dir() / "cuda"


def autostart_command():
    if is_frozen():
        return sys.executable
    return str(repo_root() / "voiceflow.bat")
```

- [ ] **Step 4: Перевести app.py на paths.** В `voiceflow/app.py`:
  - строку `ROOT = Path(__file__).resolve().parents[1]` заменить на `from voiceflow import paths` (импорт `Path` из pathlib оставить, если используется ещё где-то; если нет — убрать);
  - в `_setup_logging()`: `ROOT / "voiceflow.log"` → `paths.log_path()`;
  - `cfg = load_config(ROOT / "config.json")` → `cfg = load_config(paths.config_path())`;
  - оба вызова `save_config(ROOT / "config.json", cfg)` (в `apply_settings` и в failure-ветке `_reload_model`) → `save_config(paths.config_path(), cfg)`;
  - `autostart.enable(str(ROOT / "voiceflow.bat"))` → `autostart.enable(paths.autostart_command())`.

- [ ] **Step 5: Перевести transcriber.py.** В `_add_cuda_dll_dirs()` в `voiceflow/transcriber.py` после цикла по site-packages добавить:
```python
    from voiceflow import paths
    app_cuda = paths.cuda_dir()
    if app_cuda.is_dir():
        os.add_dll_directory(str(app_cuda))
        os.environ["PATH"] = str(app_cuda) + os.pathsep + os.environ["PATH"]
```

- [ ] **Step 6: Тесты зелёные** — `.venv/Scripts/python -m pytest tests/test_paths.py -v` → 2 passed; полный прогон → 65 passed; sanity `.venv/Scripts/python -c "import voiceflow.app"` → чисто.

- [ ] **Step 7: Commit** — `git add voiceflow/paths.py voiceflow/app.py voiceflow/transcriber.py tests/test_paths.py && git commit -m "feat: dev/frozen data paths module"`

---

### Task 2: gpu.py — определение NVIDIA и рекомендация модели

**Files:**
- Create: `voiceflow/gpu.py`
- Test: `tests/test_gpu.py`

**Interfaces:**
- Produces: `detect_nvidia() -> dict | None` (`{"name": str, "vram_mb": int}`); `recommend(gpu: dict | None) -> tuple[str, str]` (`(model, device)`).

- [ ] **Step 1: Написать падающий тест**

`tests/test_gpu.py`:
```python
import subprocess
from types import SimpleNamespace

import voiceflow.gpu as gpu


def _fake_run(stdout, returncode=0):
    def run(*a, **kw):
        return SimpleNamespace(stdout=stdout, returncode=returncode)
    return run


def test_detect_parses_nvidia_smi(monkeypatch):
    monkeypatch.setattr(gpu.subprocess, "run",
                        _fake_run("NVIDIA GeForce RTX 4080, 16376\n"))
    assert gpu.detect_nvidia() == {"name": "NVIDIA GeForce RTX 4080", "vram_mb": 16376}


def test_detect_no_nvidia_smi(monkeypatch):
    def raise_oserror(*a, **kw):
        raise OSError("not found")
    monkeypatch.setattr(gpu.subprocess, "run", raise_oserror)
    assert gpu.detect_nvidia() is None


def test_detect_bad_output(monkeypatch):
    monkeypatch.setattr(gpu.subprocess, "run", _fake_run("garbage"))
    assert gpu.detect_nvidia() is None
    monkeypatch.setattr(gpu.subprocess, "run", _fake_run("", returncode=1))
    assert gpu.detect_nvidia() is None


def test_recommend():
    assert gpu.recommend({"name": "RTX 4080", "vram_mb": 16376}) == ("large-v3", "auto")
    assert gpu.recommend({"name": "GT 1030", "vram_mb": 2048}) == ("base", "cpu")
    assert gpu.recommend(None) == ("base", "cpu")
```

- [ ] **Step 2: Убедиться, что падает** — `.venv/Scripts/python -m pytest tests/test_gpu.py -v` → FAIL `ModuleNotFoundError`

- [ ] **Step 3: Реализация**

`voiceflow/gpu.py`:
```python
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
```

- [ ] **Step 4: Тесты зелёные** — 4 passed; полный прогон → 69 passed.

- [ ] **Step 5: Смок на реальной машине** — `.venv/Scripts/python -c "from voiceflow.gpu import detect_nvidia, recommend; g = detect_nvidia(); print(g, recommend(g))"` → Expected: RTX 4080 с 16376 МБ, `('large-v3', 'auto')`.

- [ ] **Step 6: Commit** — `git add voiceflow/gpu.py tests/test_gpu.py && git commit -m "feat: NVIDIA detection and model recommendation"`

---

### Task 3: fetch.py — докачка CUDA-wheels и модели

**Files:**
- Create: `voiceflow/fetch.py`
- Test: `tests/test_fetch.py`

**Interfaces:**
- Consumes: `paths.cuda_dir()` (Task 1).
- Produces: `pick_wheel_url(pypi_json: dict) -> str`; `download(url, dest, progress_cb=None)` (`progress_cb(done_bytes, total_bytes)`); `extract_dlls(wheel_path, target_dir) -> list[str]`; `fetch_cuda(target_dir, tmp_dir, progress_cb=None)` (`progress_cb(pkg_name, done, total)`); `fetch_model(model: str)` (блокирующая, качает в HF-кэш); константы `CUDA_PACKAGES`, `MODEL_REPOS`, `MODEL_SIZES` (примерные байты: large-v3 3_100_000_000, small 490_000_000, base 150_000_000); `hf_cache_size() -> int` (байты в кэше HF — для прогресса модели по росту кэша).

- [ ] **Step 1: Написать падающий тест**

`tests/test_fetch.py`:
```python
import io
import zipfile

import voiceflow.fetch as fetch


def test_pick_wheel_url_latest_win64():
    pypi = {"releases": {
        "1.0.0": [{"filename": "pkg-1.0.0-py3-none-win_amd64.whl", "url": "http://old"}],
        "2.0.1": [
            {"filename": "pkg-2.0.1-py3-none-manylinux.whl", "url": "http://linux"},
            {"filename": "pkg-2.0.1-py3-none-win_amd64.whl", "url": "http://new"},
        ],
        "2.0.2": [{"filename": "pkg-2.0.2-py3-none-manylinux.whl", "url": "http://linux-only"}],
    }}
    assert fetch.pick_wheel_url(pypi) == "http://new"


def test_pick_wheel_url_skips_yanked_and_raises():
    pypi = {"releases": {"1.0": [
        {"filename": "p-1.0-win_amd64.whl", "url": "http://y", "yanked": True},
    ]}}
    import pytest
    with pytest.raises(LookupError):
        fetch.pick_wheel_url(pypi)


def test_extract_dlls(tmp_path):
    whl = tmp_path / "fake.whl"
    with zipfile.ZipFile(whl, "w") as z:
        z.writestr("nvidia/cublas/bin/cublas64_12.dll", b"DLL1")
        z.writestr("nvidia/cublas/bin/readme.txt", b"nope")
        z.writestr("nvidia/cublas/lib/other.dll", b"not-bin")
    out = tmp_path / "cuda"
    names = fetch.extract_dlls(whl, out)
    assert names == ["cublas64_12.dll"]
    assert (out / "cublas64_12.dll").read_bytes() == b"DLL1"
    assert not (out / "readme.txt").exists()


def test_download_reports_progress(monkeypatch, tmp_path):
    chunks = [b"aa", b"bb", b""]

    class FakeResp:
        headers = {"Content-Length": "4"}
        def read(self, n):
            return chunks.pop(0)
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False

    monkeypatch.setattr(fetch.urllib.request, "urlopen", lambda *a, **kw: FakeResp())
    progress = []
    dest = tmp_path / "f.bin"
    fetch.download("http://x", dest, lambda d, t: progress.append((d, t)))
    assert dest.read_bytes() == b"aabb"
    assert progress == [(2, 4), (4, 4)]


def test_model_constants():
    assert fetch.MODEL_REPOS["large-v3"] == "Systran/faster-whisper-large-v3"
    assert set(fetch.MODEL_REPOS) == set(fetch.MODEL_SIZES) == {"large-v3", "small", "base"}
```

- [ ] **Step 2: Убедиться, что падает** — FAIL `ModuleNotFoundError`

- [ ] **Step 3: Реализация**

`voiceflow/fetch.py`:
```python
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
```

- [ ] **Step 4: Тесты зелёные** — `.venv/Scripts/python -m pytest tests/test_fetch.py -v` → 5 passed; полный прогон → 74 passed.

- [ ] **Step 5: Смок реального PyPI (сеть, без скачивания)** — `.venv/Scripts/python -c "import json, urllib.request; from voiceflow.fetch import pick_wheel_url; meta = json.load(urllib.request.urlopen('https://pypi.org/pypi/nvidia-cublas-cu12/json')); print(pick_wheel_url(meta))"` → Expected: URL, оканчивающийся на `win_amd64.whl`.

- [ ] **Step 6: Commit** — `git add voiceflow/fetch.py tests/test_fetch.py && git commit -m "feat: CUDA wheel and model download helpers"`

---

### Task 4: wizard.py — мастер первого запуска + wiring

**Files:**
- Create: `voiceflow/wizard.py`, `scripts/try_wizard.py`
- Modify: `voiceflow/app.py` (запуск мастера при отсутствии config.json)

**Interfaces:**
- Consumes: `gpu.detect_nvidia/recommend` (Task 2), `fetch.*` (Task 3), `paths.*` (Task 1), `settings.QUALITY_PRESETS/quality_index_for_model/dedupe_input_devices`, `hotkey.HotkeyListener/human_label/names_to_vks`, `config.DEFAULTS`.
- Produces: `class Wizard` c методом `run() -> dict` (готовый cfg; блокирует до закрытия окна). GUI без юнит-тестов (конвенция); проверка `scripts/try_wizard.py`.

- [ ] **Step 1: Реализация**

`voiceflow/wizard.py`:
```python
"""Мастер первого запуска: железо → докачка → микрофон → клавиша.

Любая ошибка шага не роняет мастер: шаг можно пропустить, действуют дефолты.
Окно закрыто крестиком — возвращаются накопленные к этому моменту значения.
"""
import logging
import tempfile
import threading
import tkinter as tk
from tkinter import ttk

import numpy as np
import sounddevice as sd

from voiceflow import fetch, gpu, paths
from voiceflow import hotkey as hk
from voiceflow.config import DEFAULTS
from voiceflow.settings import QUALITY_PRESETS, dedupe_input_devices, quality_index_for_model

log = logging.getLogger(__name__)


class Wizard:
    def __init__(self):
        self._cfg = dict(DEFAULTS)
        self._gpu = gpu.detect_nvidia()
        model, device = gpu.recommend(self._gpu)
        self._cfg["model"], self._cfg["device"] = model, device
        self._need_cuda = device == "auto"

        self._root = tk.Tk()
        self._root.title("VoiceFlow — первый запуск")
        self._root.resizable(False, False)
        self._root.attributes("-topmost", True)
        self._body = ttk.Frame(self._root, padding=20, width=560, height=330)
        self._body.pack(fill="both", expand=True)
        self._body.pack_propagate(False)
        nav = ttk.Frame(self._root, padding=(20, 0, 20, 16))
        nav.pack(fill="x")
        self._back_btn = ttk.Button(nav, text="Назад", command=self._go_back)
        self._back_btn.pack(side="left")
        self._next_btn = ttk.Button(nav, text="Далее", command=self._go_next)
        self._next_btn.pack(side="right")

        self._steps = [self._step_welcome, self._step_hardware,
                       self._step_download, self._step_mic,
                       self._step_hotkey, self._step_done]
        self._idx = 0
        self._download_thread = None
        self._download_error = None
        self._progress = {"text": "", "percent": 0.0, "done": False}
        self._mic_stream = None
        self._mic_level = 0.0
        self._listener = None
        self._listener_thread = None
        self._capture_state = "idle"

        self._root.protocol("WM_DELETE_WINDOW", self._finish)
        self._show_step()

    # --- каркас ---
    def run(self):
        self._root.mainloop()
        return self._cfg

    def _clear(self):
        self._close_mic()
        for child in self._body.winfo_children():
            child.destroy()

    def _show_step(self):
        self._clear()
        self._back_btn.config(state="normal" if self._idx > 0 else "disabled")
        self._next_btn.config(text="Готово" if self._idx == len(self._steps) - 1 else "Далее",
                              state="normal")
        try:
            self._steps[self._idx]()
        except Exception:
            log.exception("Шаг мастера %d упал — пропускаю", self._idx)
            ttk.Label(self._body, text="Этот шаг не удался — нажмите «Далее», "
                      "настройку можно закончить позже в Настройках.").pack()

    def _go_next(self):
        if self._idx == len(self._steps) - 1:
            self._finish()
            return
        self._idx += 1
        self._show_step()

    def _go_back(self):
        if self._idx > 0:
            self._idx -= 1
            self._show_step()

    def _finish(self):
        self._close_mic()
        if self._listener is not None:
            self._listener.stop()
        self._root.destroy()

    def _title(self, text):
        ttk.Label(self._body, text=text, font=("Segoe UI", 13, "bold")).pack(
            anchor="w", pady=(0, 12))

    # --- шаги ---
    def _step_welcome(self):
        self._title("Добро пожаловать в VoiceFlow")
        ttk.Label(self._body, wraplength=500, justify="left", text=(
            "VoiceFlow печатает вашим голосом: зажмите клавишу, говорите, "
            "отпустите — текст появится там, где стоит курсор. Распознавание "
            "работает полностью на вашем компьютере, без интернета и подписок.\n\n"
            "Сейчас мы за пару минут всё настроим.")).pack(anchor="w")

    def _step_hardware(self):
        self._title("Оборудование")
        if self._gpu:
            found = (f"Найдена видеокарта {self._gpu['name']} "
                     f"({self._gpu['vram_mb'] // 1024} ГБ) — рекомендуем "
                     "максимальное качество.")
        else:
            found = ("Видеокарта NVIDIA не найдена — распознавание будет на "
                     "процессоре, рекомендуем быструю модель.")
        ttk.Label(self._body, text=found, wraplength=500, justify="left").pack(
            anchor="w", pady=(0, 10))
        self._quality_var = tk.IntVar(value=quality_index_for_model(self._cfg["model"]))
        for i, (label, _model) in enumerate(QUALITY_PRESETS):
            ttk.Radiobutton(self._body, text=label, variable=self._quality_var,
                            value=i, command=self._on_quality).pack(anchor="w", pady=2)

    def _on_quality(self):
        self._cfg["model"] = QUALITY_PRESETS[self._quality_var.get()][1]

    def _step_download(self):
        self._title("Загрузка компонентов")
        need_dlls = self._need_cuda and not any(paths.cuda_dir().glob("*.dll"))
        size_note = fetch.MODEL_SIZES[self._cfg["model"]] / 1e9
        parts = [f"модель ({size_note:.1f} ГБ)"]
        if need_dlls:
            parts.insert(0, "библиотеки NVIDIA (~0.6 ГБ)")
        ttk.Label(self._body, wraplength=500, justify="left",
                  text="Будут загружены: " + ", ".join(parts) + ".").pack(anchor="w")
        self._bar = ttk.Progressbar(self._body, maximum=100)
        self._bar.pack(fill="x", pady=12)
        self._status_var = tk.StringVar(value="")
        ttk.Label(self._body, textvariable=self._status_var).pack(anchor="w")
        self._dl_btn = ttk.Button(self._body, text="Начать загрузку",
                                  command=lambda: self._start_download(need_dlls))
        self._dl_btn.pack(pady=8)
        ttk.Label(self._body, foreground="#666", wraplength=500, justify="left", text=(
            "Можно нажать «Далее» и пропустить — тогда всё скачается при первом "
            "распознавании (придётся подождать).")).pack(anchor="w")

    def _start_download(self, need_dlls):
        self._dl_btn.config(state="disabled")
        self._next_btn.config(state="disabled")
        self._download_error = None
        self._progress = {"text": "Готовлюсь…", "percent": 0.0, "done": False}

        def work():
            try:
                if need_dlls:
                    paths.cuda_dir().mkdir(parents=True, exist_ok=True)
                    with tempfile.TemporaryDirectory() as tmp:
                        fetch.fetch_cuda(
                            paths.cuda_dir(), tmp,
                            lambda pkg, d, t: self._progress.update(
                                text=f"NVIDIA: {pkg} {d // 1048576} / {max(t, 1) // 1048576} МБ",
                                percent=(d / t * 40) if t else 0.0))
                base = fetch.hf_cache_size()
                total = fetch.MODEL_SIZES[self._cfg["model"]]
                watcher_stop = threading.Event()

                def watch():
                    while not watcher_stop.wait(0.5):
                        grown = fetch.hf_cache_size() - base
                        self._progress.update(
                            text=f"Модель: {grown // 1048576} / ~{total // 1048576} МБ",
                            percent=40 + min(60.0, grown / total * 60))

                threading.Thread(target=watch, daemon=True).start()
                try:
                    fetch.fetch_model(self._cfg["model"])
                finally:
                    watcher_stop.set()
                self._progress.update(text="Готово!", percent=100.0, done=True)
            except Exception as exc:
                log.exception("Ошибка загрузки в мастере")
                self._download_error = exc
                self._progress["done"] = True

        self._download_thread = threading.Thread(target=work, daemon=True)
        self._download_thread.start()
        self._poll_download()

    def _poll_download(self):
        if not self._bar.winfo_exists():
            return
        p = self._progress
        self._bar["value"] = p["percent"]
        self._status_var.set(p["text"])
        if not p["done"]:
            self._root.after(200, self._poll_download)
            return
        self._next_btn.config(state="normal")
        if self._download_error is not None:
            self._status_var.set(f"Не получилось: {self._download_error}")
            self._dl_btn.config(text="Повторить", state="normal")

    def _step_mic(self):
        self._title("Микрофон")
        devices = ["Системный по умолчанию"] + dedupe_input_devices(sd.query_devices())
        self._mic_box = ttk.Combobox(self._body, values=devices, state="readonly", width=45)
        cur = self._cfg["input_device"]
        self._mic_box.current(devices.index(cur) if cur in devices else 0)
        self._mic_box.pack(anchor="w", pady=(0, 10))
        self._mic_box.bind("<<ComboboxSelected>>", lambda e: self._open_mic())
        ttk.Label(self._body, text="Скажите что-нибудь — полоска должна дёргаться:").pack(anchor="w")
        self._level_bar = ttk.Progressbar(self._body, maximum=100)
        self._level_bar.pack(fill="x", pady=8)
        self._open_mic()
        self._poll_mic()

    def _mic_device(self):
        val = self._mic_box.get()
        return None if val == "Системный по умолчанию" else val

    def _open_mic(self):
        self._close_mic()
        self._cfg["input_device"] = self._mic_device()
        try:
            def cb(indata, frames, t, status):
                self._mic_level = float(np.sqrt((indata ** 2).mean()))
            self._mic_stream = sd.InputStream(
                samplerate=16000, channels=1, dtype="float32",
                device=self._cfg["input_device"], callback=cb)
            self._mic_stream.start()
        except Exception:
            log.exception("Не удалось открыть микрофон в мастере")
            self._mic_stream = None

    def _close_mic(self):
        if self._mic_stream is not None:
            try:
                self._mic_stream.stop()
                self._mic_stream.close()
            except Exception:
                pass
            self._mic_stream = None

    def _poll_mic(self):
        if not self._level_bar.winfo_exists():
            return
        self._level_bar["value"] = min(100.0, self._mic_level * 700)
        self._root.after(80, self._poll_mic)

    def _step_hotkey(self):
        self._title("Клавиша диктовки")
        self._hotkey_var = tk.StringVar(value=hk.human_label(self._cfg["hotkey"]))
        ttk.Label(self._body, textvariable=self._hotkey_var,
                  font=("Segoe UI", 11)).pack(anchor="w", pady=(0, 8))
        self._hk_btn = ttk.Button(self._body, text="Изменить", command=self._capture)
        self._hk_btn.pack(anchor="w")
        ttk.Label(self._body, foreground="#666", wraplength=500, justify="left", text=(
            "Зажмите эту клавишу (или комбинацию) — идёт запись; отпустите — "
            "текст напечатается. Изменить можно в любой момент в Настройках.")).pack(
            anchor="w", pady=(10, 0))

    def _ensure_listener(self):
        if self._listener is None:
            self._listener = hk.HotkeyListener(
                on_press=lambda: None, on_release=lambda: None,
                combo=hk.names_to_vks(self._cfg["hotkey"]))
            self._listener_thread = threading.Thread(
                target=self._listener.run, daemon=True)
            self._listener_thread.start()

    def _capture(self):
        self._ensure_listener()
        self._hk_btn.config(state="disabled")
        self._next_btn.config(state="disabled")
        self._back_btn.config(state="disabled")
        self._hotkey_var.set("Нажмите комбинацию… (Esc — отмена)")
        self._capture_state = "wait"
        self._listener.start_capture(
            lambda names: setattr(self, "_capture_state", names or "cancel"))
        self._poll_capture()

    def _poll_capture(self):
        state = self._capture_state
        if state == "wait":
            self._root.after(100, self._poll_capture)
            return
        if isinstance(state, list):
            self._cfg["hotkey"] = state
        self._capture_state = "idle"
        self._hotkey_var.set(hk.human_label(self._cfg["hotkey"]))
        self._hk_btn.config(state="normal")
        self._next_btn.config(state="normal")
        self._back_btn.config(state="normal")

    def _step_done(self):
        self._title("Всё готово")
        ttk.Label(self._body, wraplength=500, justify="left", text=(
            "После нажатия «Готово» загрузится модель распознавания — дождитесь "
            "уведомления «Готов» в трее (значок у часов).\n\n"
            f"Затем зажмите {hk.human_label(self._cfg['hotkey'])} и говорите — "
            "текст появится там, где стоит курсор.\n\n"
            "Настройки в любой момент: правый клик по значку в трее → «Настройки…».")).pack(anchor="w")
```

- [ ] **Step 2: Wiring в app.py.** В `main()` заменить строку `cfg = load_config(paths.config_path())` на:

```python
        cfg_file = paths.config_path()
        if not cfg_file.exists():
            log.info("config.json не найден — запускаю мастер первого запуска")
            try:
                from voiceflow.wizard import Wizard
                cfg = Wizard().run()
            except Exception:
                log.exception("Мастер первого запуска упал — значения по умолчанию")
                cfg = load_config(cfg_file)
            save_config(cfg_file, cfg)
        else:
            cfg = load_config(cfg_file)
```

- [ ] **Step 3: Ручной скрипт**

`scripts/try_wizard.py`:
```python
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
```

- [ ] **Step 4: Смок мастера** — `.venv/Scripts/python scripts/try_wizard.py` с таймаутом ~60 c: окно мастера появится на экране пользователя; исполнитель проверяет, что процесс стартовал без трейсбека, шаги переключаются программно нельзя — поэтому только: окно открылось (лог «шаг…» отсутствует = не упало) и после закрытия окна пользователем ИЛИ по таймауту убить процесс; вывод не должен содержать Traceback. Полный интерактивный прогон — за пользователем в финальном чек-листе. НЕ нажимать «Начать загрузку» программно.

- [ ] **Step 5: Полный прогон тестов** — 74 passed; `.venv/Scripts/python -c "import voiceflow.wizard, voiceflow.app"` → чисто.

- [ ] **Step 6: Commit** — `git add voiceflow/wizard.py voiceflow/app.py scripts/try_wizard.py && git commit -m "feat: first-run wizard"`

---

### Task 5: packaging/ — PyInstaller + Inno Setup

**Files:**
- Create: `packaging/entry.py`, `packaging/make_ico.py`, `packaging/voiceflow.spec`, `packaging/installer.iss`, `packaging/build.bat`
- Modify: `requirements-dev.txt` (добавить `pyinstaller>=6`), `.gitignore` (добавить `packaging/build/`, `packaging/dist/`, `packaging/voiceflow.ico`)

**Interfaces:**
- Consumes: `voiceflow/assets/icon.png` (есть), приложение целиком.
- Produces: локальная сборка `packaging/dist/VoiceFlow/VoiceFlow.exe`; файлы для CI (Task 6 вызывает те же spec/iss).

- [ ] **Step 1: entry и иконка**

`packaging/entry.py`:
```python
from voiceflow.app import main

if __name__ == "__main__":
    main()
```

`packaging/make_ico.py`:
```python
"""icon.png → voiceflow.ico (мультиразмер) для exe и установщика."""
from pathlib import Path

from PIL import Image

src = Path(__file__).resolve().parents[1] / "voiceflow" / "assets" / "icon.png"
dst = Path(__file__).parent / "voiceflow.ico"
Image.open(src).save(dst, sizes=[(16, 16), (24, 24), (32, 32), (48, 48),
                                 (64, 64), (128, 128), (256, 256)])
print(f"wrote {dst}")
```

- [ ] **Step 2: PyInstaller spec**

`packaging/voiceflow.spec`:
```python
# -*- mode: python -*-
# Сборка: packaging/build.bat (или см. .github/workflows/release.yml)
from PyInstaller.utils.hooks import collect_all, collect_data_files

ct2_datas, ct2_binaries, ct2_hidden = collect_all("ctranslate2")

a = Analysis(
    ["entry.py"],
    pathex=[".."],
    binaries=ct2_binaries,
    datas=[("../voiceflow/assets", "voiceflow/assets")]
          + collect_data_files("faster_whisper")
          + ct2_datas,
    hiddenimports=["pystray._win32", "PIL.ImageTk", "sounddevice"] + ct2_hidden,
    excludes=["nvidia", "torch", "pytest", "tkinter.test"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
    name="VoiceFlow",
    console=False,
    icon="voiceflow.ico",
)
coll = COLLECT(exe, a.binaries, a.datas, name="VoiceFlow")
```

- [ ] **Step 3: Inno Setup script**

`packaging/installer.iss`:
```ini
#define MyAppName "VoiceFlow"
#define MyAppVersion GetEnv("VF_VERSION")
#if MyAppVersion == ""
  #define MyAppVersion "0.0-dev"
#endif

[Setup]
AppId={{7E4A2C31-9B0D-4F5E-8A67-C3D1E5F70012}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
DefaultDirName={localappdata}\{#MyAppName}
PrivilegesRequired=lowest
OutputDir=dist
OutputBaseFilename=VoiceFlow-Setup-{#MyAppVersion}
SetupIconFile=voiceflow.ico
UninstallDisplayIcon={app}\VoiceFlow.exe
DisableProgramGroupPage=yes
Compression=lzma2
SolidCompression=yes

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "Ярлык на рабочем столе"
Name: "autostart"; Description: "Запускать вместе с Windows"

[Files]
Source: "dist\VoiceFlow\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{userprograms}\VoiceFlow"; Filename: "{app}\VoiceFlow.exe"
Name: "{userdesktop}\VoiceFlow"; Filename: "{app}\VoiceFlow.exe"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; \
  ValueType: string; ValueName: "VoiceFlow"; ValueData: """{app}\VoiceFlow.exe"""; \
  Tasks: autostart; Flags: uninsdeletevalue

[Run]
Filename: "{app}\VoiceFlow.exe"; Description: "Запустить VoiceFlow"; \
  Flags: postinstall nowait skipifsilent

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: string;
begin
  if CurUninstallStep = usPostUninstall then begin
    DataDir := ExpandConstant('{userappdata}\VoiceFlow');
    if DirExists(DataDir) then
      if MsgBox('Удалить настройки и загруженные компоненты VoiceFlow ('
                + DataDir + ')?', mbConfirmation, MB_YESNO) = IDYES then
        DelTree(DataDir, True, True, True);
  end;
end;
```

- [ ] **Step 4: build.bat**

`packaging/build.bat`:
```bat
@echo off
cd /d "%~dp0"
if not exist voiceflow.ico ..\.venv\Scripts\python make_ico.py
cd ..
.venv\Scripts\python -m PyInstaller packaging\voiceflow.spec --noconfirm ^
  --distpath packaging\dist --workpath packaging\build
where iscc >nul 2>nul
if %errorlevel%==0 (
  cd packaging && iscc installer.iss && cd ..
) else (
  echo [!] iscc не найден - установщик не собран, только dist\VoiceFlow
)
```

- [ ] **Step 5: Зависимость и gitignore.** В `requirements-dev.txt` добавить строку `pyinstaller>=6`; установить: `.venv/Scripts/python -m pip install "pyinstaller>=6"`. В `.gitignore` добавить: `packaging/build/`, `packaging/dist/`, `packaging/voiceflow.ico`.

- [ ] **Step 6: Локальная сборка (PyInstaller-часть)** — из Git Bash: `.venv/Scripts/python packaging/make_ico.py && cd /f/voiceflow && .venv/Scripts/python -m PyInstaller packaging/voiceflow.spec --noconfirm --distpath packaging/dist --workpath packaging/build` (таймаут 10 мин). Expected: `packaging/dist/VoiceFlow/VoiceFlow.exe` существует; в `packaging/dist/VoiceFlow/_internal/voiceflow/assets/` лежат png/wav; каталог НЕ содержит `nvidia`.

- [ ] **Step 7: Смок frozen exe.** Запустить `packaging/dist/VoiceFlow/VoiceFlow.exe` (detached), подождать ~10 c: на экране пользователя появится окно мастера (config.json в %APPDATA%\VoiceFlow отсутствует) — это ожидаемо. Проверить `%APPDATA%/VoiceFlow/voiceflow.log` содержит «Запуск VoiceFlow» и «мастер», затем завершить процесс (`taskkill /IM VoiceFlow.exe /F`) и удалить каталог `%APPDATA%/VoiceFlow` (чтобы не мешал финальной приёмке). Traceback в логе = падение задачи.

- [ ] **Step 8: Commit** — `git add packaging requirements-dev.txt .gitignore && git commit -m "feat: PyInstaller + Inno Setup packaging"`

---

### Task 6: CI/CD + README

**Files:**
- Create: `requirements-ci.txt`, `.github/workflows/ci.yml`, `.github/workflows/release.yml`
- Modify: `README.md` (раздел «Установка (для пользователей)» в начало, после заголовка)

**Interfaces:**
- Consumes: `packaging/*` (Task 5), pytest-набор.
- Produces: рабочие workflow-файлы (проверяются после публикации в Task 7).

- [ ] **Step 1: requirements-ci.txt** (без nvidia-пакетов — CI не гоняет GPU):
```
faster-whisper>=1.1
sounddevice>=0.5
numpy
pystray>=0.19
Pillow
pywin32>=306
pytest
```

- [ ] **Step 2: ci.yml**

`.github/workflows/ci.yml`:
```yaml
name: CI
on:
  push:
    branches: ["main"]
  pull_request:

jobs:
  test:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
      - run: pip install -r requirements-ci.txt
      - run: pytest -q
```

- [ ] **Step 3: release.yml**

`.github/workflows/release.yml`:
```yaml
name: Release
on:
  push:
    tags: ["v*"]

permissions:
  contents: write

jobs:
  build:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
      - run: pip install -r requirements-ci.txt "pyinstaller>=6"
      - run: pytest -q
      - run: python packaging/make_ico.py
      - run: pyinstaller packaging/voiceflow.spec --noconfirm --distpath packaging/dist --workpath packaging/build
      - name: Install Inno Setup
        run: choco install innosetup -y --no-progress
      - name: Build installer
        shell: pwsh
        run: |
          $env:VF_VERSION = "${{ github.ref_name }}"
          & "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" packaging/installer.iss
      - name: Create release
        uses: softprops/action-gh-release@v2
        with:
          files: packaging/dist/VoiceFlow-Setup-*.exe
          generate_release_notes: true
```

- [ ] **Step 4: README.** Сразу после первого абзаца (описание приложения) вставить раздел:

```markdown
## Установка (для пользователей)

1. Скачайте `VoiceFlow-Setup-…exe` из [последнего релиза](../../releases/latest).
2. Запустите. Windows покажет «Windows защитил ваш компьютер» (у бесплатных
   программ нет платной цифровой подписи) — нажмите **Подробнее → Выполнить
   в любом случае**.
3. Пройдите установку и мастер первого запуска: он сам определит вашу
   видеокарту, скачает модель распознавания, поможет выбрать микрофон и клавишу.
4. Готово: зажмите клавишу диктовки, говорите, отпустите — текст появится
   там, где стоит курсор.

Требования: Windows 10/11 x64. Для максимального качества — видеокарта
NVIDIA (6+ ГБ видеопамяти); без неё работает быстрая модель на процессоре.
```

Существующие разделы (venv-установка и т.д.) озаглавить `## Разработка` (если заголовок другой — переименовать).

- [ ] **Step 5: Проверки** — `.venv/Scripts/python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/ci.yml')); yaml.safe_load(open('.github/workflows/release.yml')); print('YAML OK')"` (если pyyaml нет в venv — `pip install pyyaml` в venv допустим); полный прогон тестов → 74 passed.

- [ ] **Step 6: Commit** — `git add requirements-ci.txt .github README.md && git commit -m "feat: CI and release workflows, user install docs"`

---

### Task 7: Публикация (выполняет контроллер — внешние действия)

**Files:** нет новых (git push, тег).

- [ ] **Step 1:** `gh auth status` — если не залогинен, попросить пользователя выполнить `! gh auth login`.
- [ ] **Step 2:** `gh repo create voiceflow --public --source=. --push --description "Локальная голосовая диктовка для Windows: push-to-talk, Whisper на вашей видеокарте, без подписок"` (после merge ветки в main).
- [ ] **Step 3:** Дождаться зелёного CI: `gh run watch` (или `gh run list --limit 1`).
- [ ] **Step 4:** Тег релиза: `git tag v1.0.0 && git push origin v1.0.0`; следить: `gh run watch`; проверить релиз: `gh release view v1.0.0` — в assets есть `VoiceFlow-Setup-v1.0.0.exe`.
- [ ] **Step 5:** Финальная приёмка пользователем: скачать установщик со страницы релиза, поставить, пройти мастер, продиктовать. (Контрольные точки: SmartScreen-обход по README; на этой машине мастер должен найти RTX 4080 и рекомендовать large-v3; модель уже в кэше — скачивание пропустится быстро.)
