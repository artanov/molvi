# VoiceFlow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Локальный аналог Wispr Flow для Windows: зажал правый Ctrl → запись голоса → faster-whisper на CUDA → текст вставляется в активное окно.

**Architecture:** Один фоновый Python-процесс. Главный поток — tkinter (оверлей-индикатор); хук клавиатуры (WH_KEYBOARD_LL) — в своём потоке; распознавание — в рабочем потоке через очередь; pystray — detached-поток. Вставка текста через буфер обмена + эмуляция Ctrl+V с восстановлением буфера.

**Tech Stack:** Python 3.13 (venv), faster-whisper (CTranslate2, CUDA), sounddevice, numpy, pystray + Pillow, pywin32, tkinter (stdlib), pytest.

## Global Constraints

- Платформа: Windows 10, GPU RTX 4080 (16 ГБ), драйвер 576.80 (CUDA 12).
- Модель: `large-v3`, `compute_type="int8_float16"`, device `auto` (cuda → откат на cpu/int8).
- Языки: автоопределение (config `language: "auto"` → `language=None` в faster-whisper).
- Hotkey: правый Ctrl (VK_RCONTROL = 0xA3), режим push-to-talk.
- Записи короче `min_duration_sec` (0.3 сек) игнорируются.
- Аудио: 16000 Гц, моно, float32.
- Конфиг: `config.json` в корне проекта; лог: `voiceflow.log` (ротация 1 МБ).
- Все команды в плане — для Git Bash из корня `F:/voiceflow`; интерпретатор venv — `.venv/Scripts/python`.
- Оверлей НЕ должен забирать фокус (WS_EX_NOACTIVATE), иначе вставка уйдёт не в то окно.
- Коммит после каждой задачи.

## File Structure

```
F:/voiceflow/
├── config.json                  # создаётся при первом запуске (Task 8)
├── requirements.txt             # Task 1
├── requirements-dev.txt         # Task 1
├── voiceflow.bat                # Task 8
├── README.md                    # Task 8
├── voiceflow/
│   ├── __init__.py              # Task 1
│   ├── config.py                # Task 1 — загрузка config.json с дефолтами
│   ├── recorder.py              # Task 2 — запись с микрофона в numpy-буфер
│   ├── transcriber.py           # Task 3 — обёртка faster-whisper (+CUDA DLL)
│   ├── typer.py                 # Task 4 — вставка текста (clipboard / SendInput)
│   ├── controller.py            # Task 5 — состояние, очередь, рабочий поток
│   ├── hotkey.py                # Task 6 — WH_KEYBOARD_LL хук правого Ctrl
│   ├── overlay.py               # Task 7 — tkinter-индикатор поверх окон
│   ├── tray.py                  # Task 7 — иконка в трее (pystray)
│   └── app.py                   # Task 8 — точка входа, wiring, логирование
├── scripts/
│   ├── smoke_transcribe.py      # Task 3 — ручная проверка GPU-распознавания
│   ├── try_hotkey.py            # Task 6 — ручная проверка хука
│   └── try_overlay.py           # Task 7 — ручная проверка оверлея
└── tests/
    ├── test_config.py           # Task 1
    ├── test_recorder.py         # Task 2
    ├── test_transcriber.py      # Task 3
    ├── test_typer.py            # Task 4
    ├── test_controller.py       # Task 5
    └── test_hotkey.py           # Task 6
```

---

### Task 1: Каркас проекта + config.py

**Files:**
- Create: `requirements.txt`, `requirements-dev.txt`, `.gitignore`, `voiceflow/__init__.py`, `voiceflow/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `config.load_config(path: str | Path) -> dict` — читает JSON, накладывает на `config.DEFAULTS`, неизвестные ключи отбрасывает, отсутствующий файл → копия дефолтов. `config.DEFAULTS: dict`.

- [ ] **Step 1: Создать venv и файлы зависимостей**

`requirements.txt`:
```
faster-whisper>=1.1
sounddevice>=0.5
numpy
pystray>=0.19
Pillow
pywin32>=306
nvidia-cublas-cu12
nvidia-cudnn-cu12>=9
```

`requirements-dev.txt`:
```
-r requirements.txt
pytest
```

`.gitignore`:
```
.venv/
__pycache__/
*.log
config.json
```

Команды:
```bash
py -3.13 -m venv .venv
.venv/Scripts/python -m pip install --upgrade pip
.venv/Scripts/python -m pip install -r requirements-dev.txt
```
Expected: все пакеты установились без ошибок сборки (у всех есть бинарные колёса cp313/win_amd64).
**Fallback:** если pip не найдёт колесо `ctranslate2` под 3.13 — установить Python 3.12 (`winget install Python.Python.3.12`), пересоздать venv через `py -3.12 -m venv .venv` и повторить установку.

- [ ] **Step 2: Написать падающий тест**

`tests/test_config.py`:
```python
import json

from voiceflow.config import DEFAULTS, load_config


def test_missing_file_returns_defaults(tmp_path):
    cfg = load_config(tmp_path / "nope.json")
    assert cfg == DEFAULTS
    assert cfg is not DEFAULTS  # копия, а не ссылка


def test_partial_file_merges_over_defaults(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"language": "ru"}), encoding="utf-8")
    cfg = load_config(p)
    assert cfg["language"] == "ru"
    assert cfg["model"] == DEFAULTS["model"]


def test_unknown_keys_ignored(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"bogus": 1, "device": "cpu"}), encoding="utf-8")
    cfg = load_config(p)
    assert "bogus" not in cfg
    assert cfg["device"] == "cpu"
```

- [ ] **Step 3: Убедиться, что тест падает**

Run: `.venv/Scripts/python -m pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'voiceflow'`

- [ ] **Step 4: Реализация**

`voiceflow/__init__.py` — пустой файл.

`voiceflow/config.py`:
```python
import json
from pathlib import Path

DEFAULTS = {
    "model": "large-v3",
    "device": "auto",           # auto | cuda | cpu
    "compute_type": "int8_float16",
    "language": "auto",         # auto | ru | en
    "min_duration_sec": 0.3,
    "paste_mode": "clipboard",  # clipboard | type
    "input_device": None,       # имя/индекс устройства sounddevice; None = системное
    "samplerate": 16000,
}


def load_config(path):
    path = Path(path)
    cfg = dict(DEFAULTS)
    if not path.exists():
        return cfg
    data = json.loads(path.read_text(encoding="utf-8"))
    cfg.update({k: v for k, v in data.items() if k in DEFAULTS})
    return cfg
```

- [ ] **Step 5: Тесты зелёные**

Run: `.venv/Scripts/python -m pytest tests/test_config.py -v`
Expected: 3 passed

- [ ] **Step 6: Commit**

```bash
git add .gitignore requirements.txt requirements-dev.txt voiceflow tests
git commit -m "feat: project scaffolding and config loader"
```

---

### Task 2: recorder.py — запись с микрофона

**Files:**
- Create: `voiceflow/recorder.py`
- Test: `tests/test_recorder.py`

**Interfaces:**
- Consumes: config-ключи `samplerate`, `input_device`.
- Produces: `class Recorder(samplerate: int = 16000, device=None)` с методами `start() -> None` (открывает `sounddevice.InputStream`, копит чанки) и `stop() -> np.ndarray` (закрывает поток, возвращает одномерный float32-массив; пустой массив, если данных нет). Повторный `stop()` без `start()` безопасен.

- [ ] **Step 1: Написать падающий тест**

`tests/test_recorder.py`:
```python
import numpy as np

from voiceflow.recorder import Recorder


def _feed(rec, n_chunks, chunk_len=160):
    for i in range(n_chunks):
        chunk = np.full((chunk_len, 1), float(i), dtype=np.float32)
        rec._callback(chunk, chunk_len, None, None)


def test_callback_accumulates_and_stop_concatenates():
    rec = Recorder()
    rec._chunks = []
    _feed(rec, 3)
    audio = rec.stop()
    assert audio.dtype == np.float32
    assert audio.ndim == 1
    assert len(audio) == 3 * 160
    assert audio[0] == 0.0 and audio[-1] == 2.0


def test_stop_without_data_returns_empty():
    rec = Recorder()
    audio = rec.stop()
    assert isinstance(audio, np.ndarray)
    assert len(audio) == 0


def test_start_opens_stream_and_resets_buffer(monkeypatch):
    created = {}

    class FakeStream:
        def __init__(self, **kwargs):
            created.update(kwargs)
        def start(self):
            created["started"] = True
        def stop(self):
            pass
        def close(self):
            pass

    import voiceflow.recorder as r
    monkeypatch.setattr(r.sd, "InputStream", FakeStream)
    rec = Recorder(samplerate=16000, device=None)
    rec._chunks = [np.zeros((10, 1), dtype=np.float32)]  # мусор от прошлой записи
    rec.start()
    assert created["samplerate"] == 16000
    assert created["channels"] == 1
    assert created["started"] is True
    assert rec._chunks == []
```

- [ ] **Step 2: Убедиться, что тест падает**

Run: `.venv/Scripts/python -m pytest tests/test_recorder.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'voiceflow.recorder'`

- [ ] **Step 3: Реализация**

`voiceflow/recorder.py`:
```python
import numpy as np
import sounddevice as sd


class Recorder:
    """Записывает звук с микрофона в память между start() и stop()."""

    def __init__(self, samplerate=16000, device=None):
        self.samplerate = samplerate
        self.device = device
        self._chunks = []
        self._stream = None

    def _callback(self, indata, frames, time_info, status):
        self._chunks.append(indata.copy())

    def start(self):
        self._chunks = []
        self._stream = sd.InputStream(
            samplerate=self.samplerate,
            channels=1,
            dtype="float32",
            device=self.device,
            callback=self._callback,
        )
        self._stream.start()

    def stop(self):
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        if not self._chunks:
            return np.zeros(0, dtype=np.float32)
        audio = np.concatenate(self._chunks)[:, 0]
        self._chunks = []
        return audio
```

- [ ] **Step 4: Тесты зелёные**

Run: `.venv/Scripts/python -m pytest tests/test_recorder.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add voiceflow/recorder.py tests/test_recorder.py
git commit -m "feat: microphone recorder"
```

---

### Task 3: transcriber.py — обёртка faster-whisper

**Files:**
- Create: `voiceflow/transcriber.py`, `scripts/smoke_transcribe.py`
- Test: `tests/test_transcriber.py`

**Interfaces:**
- Consumes: config-ключи `model`, `device`, `compute_type`, `language`.
- Produces: `class Transcriber(model_name: str, device: str, compute_type: str, language: str)` — конструктор загружает модель (device `"auto"`/`"cuda"` → пробует CUDA, при исключении откатывается на CPU + `compute_type="int8"`); свойство `device: str` — фактическое устройство (`"cuda"`/`"cpu"`); метод `transcribe(audio: np.ndarray) -> str` — текст одной строкой, `""` для тишины. `language="auto"` транслируется в `language=None`.

- [ ] **Step 1: Написать падающий тест**

`tests/test_transcriber.py`:
```python
import types

import numpy as np
import pytest


class FakeSegment:
    def __init__(self, text):
        self.text = text


def _fake_model_factory(calls, fail_on_cuda=False, segments=()):
    class FakeWhisperModel:
        def __init__(self, model_name, device=None, compute_type=None):
            calls.append({"device": device, "compute_type": compute_type})
            if fail_on_cuda and device == "cuda":
                raise RuntimeError("CUDA driver not found")
        def transcribe(self, audio, **kwargs):
            calls.append({"transcribe_kwargs": kwargs})
            info = types.SimpleNamespace(language="ru")
            return iter(segments), info
    return FakeWhisperModel


@pytest.fixture
def patch_model(monkeypatch):
    def _patch(**kw):
        calls = []
        import voiceflow.transcriber as t
        monkeypatch.setattr(t, "WhisperModel", _fake_model_factory(calls, **kw))
        return calls
    return _patch


def test_joins_segments_and_strips(patch_model):
    from voiceflow.transcriber import Transcriber
    calls = patch_model(segments=[FakeSegment(" Привет,"), FakeSegment(" мир! ")])
    tr = Transcriber("large-v3", "cpu", "int8", "auto")
    text = tr.transcribe(np.zeros(16000, dtype=np.float32))
    assert text == "Привет, мир!"


def test_empty_segments_give_empty_string(patch_model):
    from voiceflow.transcriber import Transcriber
    patch_model(segments=[])
    tr = Transcriber("large-v3", "cpu", "int8", "auto")
    assert tr.transcribe(np.zeros(16000, dtype=np.float32)) == ""


def test_auto_language_passed_as_none(patch_model):
    from voiceflow.transcriber import Transcriber
    calls = patch_model(segments=[])
    tr = Transcriber("large-v3", "cpu", "int8", "auto")
    tr.transcribe(np.zeros(16000, dtype=np.float32))
    kwargs = calls[-1]["transcribe_kwargs"]
    assert kwargs["language"] is None


def test_fixed_language_passed_through(patch_model):
    from voiceflow.transcriber import Transcriber
    calls = patch_model(segments=[])
    tr = Transcriber("large-v3", "cpu", "int8", "ru")
    tr.transcribe(np.zeros(16000, dtype=np.float32))
    assert calls[-1]["transcribe_kwargs"]["language"] == "ru"


def test_cuda_failure_falls_back_to_cpu(patch_model):
    from voiceflow.transcriber import Transcriber
    calls = patch_model(fail_on_cuda=True)
    tr = Transcriber("large-v3", "auto", "int8_float16", "auto")
    assert tr.device == "cpu"
    assert calls[0]["device"] == "cuda"
    assert calls[1] == {"device": "cpu", "compute_type": "int8"}
```

- [ ] **Step 2: Убедиться, что тест падает**

Run: `.venv/Scripts/python -m pytest tests/test_transcriber.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'voiceflow.transcriber'`

- [ ] **Step 3: Реализация**

`voiceflow/transcriber.py`:
```python
import logging
import os
import sys
from pathlib import Path

log = logging.getLogger(__name__)


def _add_cuda_dll_dirs():
    """cuBLAS/cuDNN ставятся pip-пакетами nvidia-*; их DLL надо добавить в поиск."""
    for sub in ("nvidia/cublas/bin", "nvidia/cudnn/bin"):
        p = Path(sys.prefix) / "Lib" / "site-packages" / Path(sub)
        if p.is_dir():
            os.add_dll_directory(str(p))


_add_cuda_dll_dirs()

from faster_whisper import WhisperModel  # noqa: E402


class Transcriber:
    def __init__(self, model_name, device, compute_type, language):
        self._language = None if language == "auto" else language
        if device in ("auto", "cuda"):
            try:
                self._model = WhisperModel(model_name, device="cuda", compute_type=compute_type)
                self.device = "cuda"
                return
            except Exception:
                if device == "cuda":
                    raise
                log.warning("CUDA недоступна, откатываюсь на CPU", exc_info=True)
        self._model = WhisperModel(model_name, device="cpu", compute_type="int8")
        self.device = "cpu"

    def transcribe(self, audio):
        segments, _info = self._model.transcribe(
            audio,
            language=self._language,
            beam_size=5,
            vad_filter=True,
        )
        return " ".join(s.text.strip() for s in segments).strip()
```

- [ ] **Step 4: Тесты зелёные**

Run: `.venv/Scripts/python -m pytest tests/test_transcriber.py -v`
Expected: 5 passed

- [ ] **Step 5: Скрипт дымовой проверки GPU**

`scripts/smoke_transcribe.py`:
```python
"""Ручная проверка: записывает 4 секунды с микрофона и распознаёт на GPU.

Первый запуск скачивает модель large-v3 (~3 ГБ) с HuggingFace.
Запуск: .venv/Scripts/python scripts/smoke_transcribe.py
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import sounddevice as sd

from voiceflow.recorder import Recorder
from voiceflow.transcriber import Transcriber

print("Загружаю модель (первый раз — скачивание ~3 ГБ)...")
t0 = time.time()
tr = Transcriber("large-v3", "auto", "int8_float16", "auto")
print(f"Модель загружена за {time.time() - t0:.1f} c, устройство: {tr.device}")

rec = Recorder()
print("Говорите — записываю 4 секунды...")
rec.start()
sd.sleep(4000)
audio = rec.stop()
print(f"Записано {len(audio) / 16000:.1f} c")

t0 = time.time()
text = tr.transcribe(audio)
print(f"Распознано за {time.time() - t0:.1f} c: {text!r}")
```

- [ ] **Step 6: Запустить дымовую проверку**

Run: `.venv/Scripts/python scripts/smoke_transcribe.py` — произнести фразу вслух, например «Привет, это тест VoiceFlow, commit and push».
Expected: `устройство: cuda`, распознавание ≤ ~2 c, текст соответствует сказанному (включая английские слова).
Если `устройство: cpu` — смотреть лог: обычно не найдены DLL cuDNN; проверить, что пакеты `nvidia-cublas-cu12`/`nvidia-cudnn-cu12` установлены и каталоги `nvidia/cublas/bin`, `nvidia/cudnn/bin` существуют в `site-packages`.
(Шаг требует микрофона и голоса — если исполнитель работает без ручного доступа, попросить пользователя запустить и прислать вывод.)

- [ ] **Step 7: Commit**

```bash
git add voiceflow/transcriber.py tests/test_transcriber.py scripts/smoke_transcribe.py
git commit -m "feat: faster-whisper transcriber with CUDA fallback"
```

---

### Task 4: typer.py — вставка текста в активное окно

**Files:**
- Create: `voiceflow/typer.py`
- Test: `tests/test_typer.py`

**Interfaces:**
- Consumes: config-ключ `paste_mode`.
- Produces: `paste_text(text: str, restore_delay: float = 0.3) -> None` — сохранить буфер → положить текст → Ctrl+V → пауза → восстановить буфер; `type_text_direct(text: str) -> None` — посимвольный ввод через SendInput (KEYEVENTF_UNICODE); `insert_text(text: str, mode: str) -> None` — диспетчер (`"clipboard"` → paste_text, `"type"` → type_text_direct). При ошибке вставки текст остаётся в буфере (восстановление пропускается), исключение пробрасывается вызывающему.

- [ ] **Step 1: Написать падающий тест**

`tests/test_typer.py`:
```python
import pytest

import voiceflow.typer as typer


@pytest.fixture
def fake_env(monkeypatch):
    """Подменяет работу с реальным буфером и клавиатурой; пишет журнал вызовов."""
    calls = []
    clipboard = {"text": "старое содержимое"}

    monkeypatch.setattr(typer, "_get_clipboard_text", lambda: clipboard["text"])
    monkeypatch.setattr(
        typer, "_set_clipboard_text",
        lambda t: (clipboard.__setitem__("text", t), calls.append(("set", t))),
    )
    monkeypatch.setattr(typer, "_press_ctrl_v", lambda: calls.append(("ctrl_v",)))
    monkeypatch.setattr(typer.time, "sleep", lambda s: calls.append(("sleep", s)))
    return calls, clipboard


def test_paste_sets_pastes_then_restores(fake_env):
    calls, clipboard = fake_env
    typer.paste_text("новый текст", restore_delay=0.3)
    assert calls == [
        ("set", "новый текст"),
        ("ctrl_v",),
        ("sleep", 0.3),
        ("set", "старое содержимое"),
    ]
    assert clipboard["text"] == "старое содержимое"


def test_paste_without_prior_text_skips_restore(fake_env, monkeypatch):
    calls, clipboard = fake_env
    monkeypatch.setattr(typer, "_get_clipboard_text", lambda: None)  # в буфере картинка
    typer.paste_text("текст", restore_delay=0.1)
    assert ("set", "текст") in calls
    assert calls[-1] != ("set", None)
    assert clipboard["text"] == "текст"


def test_paste_failure_keeps_text_in_clipboard(fake_env, monkeypatch):
    calls, clipboard = fake_env
    monkeypatch.setattr(
        typer, "_press_ctrl_v",
        lambda: (_ for _ in ()).throw(OSError("SendInput failed")),
    )
    with pytest.raises(OSError):
        typer.paste_text("важный текст")
    assert clipboard["text"] == "важный текст"  # буфер НЕ восстановлен — текст не потерян


def test_insert_text_dispatch(fake_env, monkeypatch):
    called = {}
    monkeypatch.setattr(typer, "paste_text", lambda t: called.setdefault("paste", t))
    monkeypatch.setattr(typer, "type_text_direct", lambda t: called.setdefault("type", t))
    typer.insert_text("a", "clipboard")
    typer.insert_text("b", "type")
    assert called == {"paste": "a", "type": "b"}
```

- [ ] **Step 2: Убедиться, что тест падает**

Run: `.venv/Scripts/python -m pytest tests/test_typer.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'voiceflow.typer'`

- [ ] **Step 3: Реализация**

`voiceflow/typer.py`:
```python
import ctypes
import time

import win32clipboard
import win32con

_user32 = ctypes.windll.user32

VK_CONTROL = 0x11
VK_V = 0x56
VK_RETURN = 0x0D
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004


def _open_clipboard(retries=10, delay=0.05):
    """Буфер может быть занят другим процессом — пробуем несколько раз."""
    for _ in range(retries):
        try:
            win32clipboard.OpenClipboard()
            return
        except Exception:
            time.sleep(delay)
    win32clipboard.OpenClipboard()  # последняя попытка — пусть исключение всплывёт


def _get_clipboard_text():
    _open_clipboard()
    try:
        if win32clipboard.IsClipboardFormatAvailable(win32con.CF_UNICODETEXT):
            return win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT)
        return None  # не текст (картинка/файлы) — восстановить не сможем
    finally:
        win32clipboard.CloseClipboard()


def _set_clipboard_text(text):
    _open_clipboard()
    try:
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32con.CF_UNICODETEXT, text)
    finally:
        win32clipboard.CloseClipboard()


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.c_ushort),
        ("wScan", ctypes.c_ushort),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", ctypes.c_ulong),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class _HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", ctypes.c_ulong),
        ("wParamL", ctypes.c_ushort),
        ("wParamH", ctypes.c_ushort),
    ]


class _INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("ki", _KEYBDINPUT), ("mi", _MOUSEINPUT), ("hi", _HARDWAREINPUT)]
    _anonymous_ = ("u",)
    _fields_ = [("type", ctypes.c_ulong), ("u", _U)]


def _send_key(vk=0, scan=0, flags=0):
    inp = _INPUT(type=1)  # INPUT_KEYBOARD
    inp.ki = _KEYBDINPUT(vk, scan, flags, 0, None)
    if _user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(_INPUT)) != 1:
        raise OSError("SendInput failed")


def _press_ctrl_v():
    _send_key(vk=VK_CONTROL)
    _send_key(vk=VK_V)
    _send_key(vk=VK_V, flags=KEYEVENTF_KEYUP)
    _send_key(vk=VK_CONTROL, flags=KEYEVENTF_KEYUP)


def paste_text(text, restore_delay=0.3):
    old = _get_clipboard_text()
    _set_clipboard_text(text)
    _press_ctrl_v()
    # Пауза, чтобы целевое приложение успело прочитать буфер до восстановления.
    time.sleep(restore_delay)
    if old is not None:
        _set_clipboard_text(old)


def type_text_direct(text):
    for ch in text:
        if ch == "\n":
            _send_key(vk=VK_RETURN)
            _send_key(vk=VK_RETURN, flags=KEYEVENTF_KEYUP)
            continue
        code = ord(ch)
        _send_key(scan=code, flags=KEYEVENTF_UNICODE)
        _send_key(scan=code, flags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP)
        time.sleep(0.005)


def insert_text(text, mode):
    if mode == "type":
        type_text_direct(text)
    else:
        paste_text(text)
```

- [ ] **Step 4: Тесты зелёные**

Run: `.venv/Scripts/python -m pytest tests/test_typer.py -v`
Expected: 4 passed

- [ ] **Step 5: Ручная проверка вставки**

Run (курсор поставить в Блокнот в течение 3 секунд):
```bash
.venv/Scripts/python -c "import time; time.sleep(3); from voiceflow.typer import paste_text; paste_text('Проверка вставки: русский + English 123')"
```
Expected: текст появился в Блокноте, прежнее содержимое буфера обмена восстановлено.

- [ ] **Step 6: Commit**

```bash
git add voiceflow/typer.py tests/test_typer.py
git commit -m "feat: text insertion via clipboard paste and SendInput fallback"
```

---

### Task 5: controller.py — состояние и конвейер обработки

**Files:**
- Create: `voiceflow/controller.py`
- Test: `tests/test_controller.py`

**Interfaces:**
- Consumes: `Recorder.start()/stop() -> np.ndarray` (Task 2), `Transcriber.transcribe(np.ndarray) -> str` (Task 3), `insert_text(text, mode)` (Task 4).
- Produces: `class Controller(recorder, transcriber, insert_fn, ui, *, min_duration_sec=0.3, samplerate=16000, paste_mode="clipboard", notify=None)`.
  Методы: `on_press() -> None`, `on_release() -> None` (вызываются из потока хука), `start() -> None` / `shutdown() -> None` (рабочий поток), `toggle_pause() -> bool` (возвращает новое состояние paused).
  `ui` — любой объект с методами `show_recording()`, `show_transcribing()`, `hide()`.
  `notify` — `Callable[[str], None]` для уведомлений об ошибках (может быть None).

- [ ] **Step 1: Написать падающий тест**

`tests/test_controller.py`:
```python
import time

import numpy as np
import pytest

from voiceflow.controller import Controller


class FakeRecorder:
    def __init__(self, audio):
        self.audio = audio
        self.started = 0
    def start(self):
        self.started += 1
    def stop(self):
        return self.audio


class FakeTranscriber:
    def __init__(self, text="привет мир", error=None):
        self.text = text
        self.error = error
        self.calls = []
    def transcribe(self, audio):
        self.calls.append(audio)
        if self.error:
            raise self.error
        return self.text


class FakeUI:
    def __init__(self):
        self.events = []
    def show_recording(self):
        self.events.append("recording")
    def show_transcribing(self):
        self.events.append("transcribing")
    def hide(self):
        self.events.append("hide")


def _wait_until(cond, timeout=2.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if cond():
            return True
        time.sleep(0.01)
    return False


def _make(audio_sec=1.0, text="привет мир", error=None):
    audio = np.zeros(int(16000 * audio_sec), dtype=np.float32)
    rec, tr, ui = FakeRecorder(audio), FakeTranscriber(text, error), FakeUI()
    inserted = []
    notes = []
    ctl = Controller(
        rec, tr, lambda t, m: inserted.append((t, m)), ui,
        min_duration_sec=0.3, samplerate=16000, paste_mode="clipboard",
        notify=notes.append,
    )
    ctl.start()
    return ctl, rec, tr, ui, inserted, notes


def test_full_cycle_inserts_text():
    ctl, rec, tr, ui, inserted, _ = _make()
    ctl.on_press()
    ctl.on_release()
    assert _wait_until(lambda: inserted)
    ctl.shutdown()
    assert inserted == [("привет мир", "clipboard")]
    assert ui.events == ["recording", "transcribing", "hide"]


def test_short_recording_ignored():
    ctl, rec, tr, ui, inserted, _ = _make(audio_sec=0.1)
    ctl.on_press()
    ctl.on_release()
    assert _wait_until(lambda: "hide" in ui.events)
    ctl.shutdown()
    assert inserted == []
    assert tr.calls == []


def test_empty_transcription_not_inserted():
    ctl, rec, tr, ui, inserted, _ = _make(text="")
    ctl.on_press()
    ctl.on_release()
    assert _wait_until(lambda: ui.events.count("hide") >= 1)
    ctl.shutdown()
    assert inserted == []


def test_paused_ignores_hotkey():
    ctl, rec, tr, ui, inserted, _ = _make()
    assert ctl.toggle_pause() is True
    ctl.on_press()
    ctl.on_release()
    time.sleep(0.1)
    ctl.shutdown()
    assert rec.started == 0
    assert inserted == []
    assert ctl.toggle_pause() is False


def test_transcribe_error_notifies_and_hides():
    ctl, rec, tr, ui, inserted, notes = _make(error=RuntimeError("boom"))
    ctl.on_press()
    ctl.on_release()
    assert _wait_until(lambda: notes)
    ctl.shutdown()
    assert inserted == []
    assert "hide" in ui.events


def test_release_without_press_is_noop():
    ctl, rec, tr, ui, inserted, _ = _make()
    ctl.on_release()
    time.sleep(0.05)
    ctl.shutdown()
    assert tr.calls == []
```

- [ ] **Step 2: Убедиться, что тест падает**

Run: `.venv/Scripts/python -m pytest tests/test_controller.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'voiceflow.controller'`

- [ ] **Step 3: Реализация**

`voiceflow/controller.py`:
```python
import logging
import queue
import threading

log = logging.getLogger(__name__)


class Controller:
    """Связывает hotkey → запись → распознавание → вставку.

    on_press/on_release зовутся из потока хука клавиатуры и не блокируются:
    тяжёлая работа уходит в рабочий поток через очередь.
    """

    def __init__(self, recorder, transcriber, insert_fn, ui, *,
                 min_duration_sec=0.3, samplerate=16000,
                 paste_mode="clipboard", notify=None):
        self._recorder = recorder
        self._transcriber = transcriber
        self._insert_fn = insert_fn
        self._ui = ui
        self._min_samples = int(min_duration_sec * samplerate)
        self._paste_mode = paste_mode
        self._notify = notify or (lambda msg: None)
        self._jobs = queue.Queue()
        self._worker = None
        self._recording = False
        self._paused = False
        self._lock = threading.Lock()

    def start(self):
        self._worker = threading.Thread(target=self._run, daemon=True)
        self._worker.start()

    def shutdown(self):
        self._jobs.put(None)
        if self._worker is not None:
            self._worker.join(timeout=5)

    def toggle_pause(self):
        with self._lock:
            self._paused = not self._paused
            return self._paused

    def on_press(self):
        with self._lock:
            if self._paused or self._recording:
                return
            self._recording = True
        try:
            self._recorder.start()
            self._ui.show_recording()
        except Exception as exc:
            with self._lock:
                self._recording = False
            log.exception("Не удалось начать запись")
            self._notify(f"Микрофон недоступен: {exc}")
            self._ui.hide()

    def on_release(self):
        with self._lock:
            if not self._recording:
                return
            self._recording = False
        audio = self._recorder.stop()
        if len(audio) < self._min_samples:
            self._ui.hide()
            return
        self._ui.show_transcribing()
        self._jobs.put(audio)

    def _run(self):
        while True:
            audio = self._jobs.get()
            if audio is None:
                return
            try:
                text = self._transcriber.transcribe(audio)
                if text:
                    self._insert_fn(text, self._paste_mode)
            except Exception as exc:
                log.exception("Ошибка обработки диктовки")
                self._notify(f"Ошибка: {exc}. Если текст распознан — он в буфере обмена (Ctrl+V).")
            finally:
                self._ui.hide()
```

- [ ] **Step 4: Тесты зелёные**

Run: `.venv/Scripts/python -m pytest tests/test_controller.py -v`
Expected: 6 passed

- [ ] **Step 5: Полный прогон тестов**

Run: `.venv/Scripts/python -m pytest -v`
Expected: все тесты проекта passed

- [ ] **Step 6: Commit**

```bash
git add voiceflow/controller.py tests/test_controller.py
git commit -m "feat: dictation controller with worker queue"
```

---

### Task 6: hotkey.py — хук правого Ctrl

**Files:**
- Create: `voiceflow/hotkey.py`, `scripts/try_hotkey.py`
- Test: `tests/test_hotkey.py`

**Interfaces:**
- Consumes: `Controller.on_press` / `Controller.on_release` (Task 5) как колбэки.
- Produces: `class HotkeyListener(on_press: Callable, on_release: Callable, vk: int = 0xA3)` — метод `run() -> None` (блокирующий: ставит WH_KEYBOARD_LL и крутит цикл сообщений; запускать в отдельном потоке), `stop() -> None` (снимает хук, выходит из run). Внутренний метод `_handle(msg: int, vk: int) -> None` — чистая логика (подавление автоповтора), тестируется без WinAPI.

- [ ] **Step 1: Написать падающий тест**

`tests/test_hotkey.py`:
```python
from voiceflow.hotkey import WM_KEYDOWN, WM_KEYUP, VK_RCONTROL, HotkeyListener


def _make():
    events = []
    hl = HotkeyListener(
        on_press=lambda: events.append("press"),
        on_release=lambda: events.append("release"),
    )
    return hl, events


def test_press_release_cycle():
    hl, events = _make()
    hl._handle(WM_KEYDOWN, VK_RCONTROL)
    hl._handle(WM_KEYUP, VK_RCONTROL)
    assert events == ["press", "release"]


def test_autorepeat_suppressed():
    hl, events = _make()
    for _ in range(5):
        hl._handle(WM_KEYDOWN, VK_RCONTROL)  # Windows шлёт KEYDOWN каждые ~30 мс
    hl._handle(WM_KEYUP, VK_RCONTROL)
    assert events == ["press", "release"]


def test_other_keys_ignored():
    hl, events = _make()
    hl._handle(WM_KEYDOWN, 0x41)  # 'A'
    hl._handle(WM_KEYUP, 0x41)
    assert events == []


def test_release_without_press_ignored():
    hl, events = _make()
    hl._handle(WM_KEYUP, VK_RCONTROL)
    assert events == []
```

- [ ] **Step 2: Убедиться, что тест падает**

Run: `.venv/Scripts/python -m pytest tests/test_hotkey.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'voiceflow.hotkey'`

- [ ] **Step 3: Реализация**

`voiceflow/hotkey.py`:
```python
import ctypes
import ctypes.wintypes as wintypes
import logging

log = logging.getLogger(__name__)

_user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32

WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105
WM_QUIT = 0x0012
VK_RCONTROL = 0xA3

_HOOKPROC = ctypes.CFUNCTYPE(
    ctypes.c_longlong, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM
)


class _KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG)),
    ]


class HotkeyListener:
    def __init__(self, on_press, on_release, vk=VK_RCONTROL):
        self._on_press = on_press
        self._on_release = on_release
        self._vk = vk
        self._is_down = False
        self._hook = None
        self._thread_id = None
        self._proc = _HOOKPROC(self._low_level_proc)  # держим ссылку от GC

    def _handle(self, msg, vk):
        if vk != self._vk:
            return
        if msg in (WM_KEYDOWN, WM_SYSKEYDOWN):
            if not self._is_down:  # подавляем автоповтор Windows
                self._is_down = True
                self._on_press()
        elif msg in (WM_KEYUP, WM_SYSKEYUP):
            if self._is_down:
                self._is_down = False
                self._on_release()

    def _low_level_proc(self, n_code, w_param, l_param):
        if n_code >= 0:
            kb = ctypes.cast(l_param, ctypes.POINTER(_KBDLLHOOKSTRUCT)).contents
            try:
                self._handle(w_param, kb.vkCode)
            except Exception:
                log.exception("Ошибка в обработчике hotkey")
        return _user32.CallNextHookEx(None, n_code, w_param, l_param)

    def run(self):
        """Блокирующий цикл; запускать в отдельном потоке."""
        self._thread_id = _kernel32.GetCurrentThreadId()
        self._hook = _user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._proc, None, 0)
        if not self._hook:
            raise OSError("SetWindowsHookExW failed")
        msg = wintypes.MSG()
        while _user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            _user32.TranslateMessage(ctypes.byref(msg))
            _user32.DispatchMessageW(ctypes.byref(msg))
        _user32.UnhookWindowsHookEx(self._hook)
        self._hook = None

    def stop(self):
        if self._thread_id:
            _user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
```

- [ ] **Step 4: Тесты зелёные**

Run: `.venv/Scripts/python -m pytest tests/test_hotkey.py -v`
Expected: 4 passed

- [ ] **Step 5: Скрипт ручной проверки**

`scripts/try_hotkey.py`:
```python
"""Ручная проверка хука: зажмите/отпустите правый Ctrl, Ctrl+C для выхода."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from voiceflow.hotkey import HotkeyListener

hl = HotkeyListener(
    on_press=lambda: print("PRESS  (запись бы началась)"),
    on_release=lambda: print("RELEASE (распознавание бы началось)"),
)
print("Слушаю правый Ctrl... Ctrl+C — выход.")
try:
    hl.run()
except KeyboardInterrupt:
    pass
```

Run: `.venv/Scripts/python scripts/try_hotkey.py` — зажать правый Ctrl на секунду, отпустить.
Expected: ровно одна пара `PRESS`/`RELEASE` на одно удержание (без дублей от автоповтора). Левый Ctrl не срабатывает.

- [ ] **Step 6: Commit**

```bash
git add voiceflow/hotkey.py tests/test_hotkey.py scripts/try_hotkey.py
git commit -m "feat: low-level keyboard hook for right Ctrl push-to-talk"
```

---

### Task 7: overlay.py + tray.py — индикатор и трей

**Files:**
- Create: `voiceflow/overlay.py`, `voiceflow/tray.py`, `scripts/try_overlay.py`

**Interfaces:**
- Consumes: используется контроллером как `ui` (Task 5: `show_recording()`, `show_transcribing()`, `hide()`).
- Produces:
  - `class Overlay()` — создаёт `tk.Tk` (скрытый). Методы `show_recording()`, `show_transcribing()`, `hide()` потокобезопасны (кладут состояние в `queue.Queue`, главный поток забирает через `root.after`). `run() -> None` — блокирующий `mainloop()`, вызывать из главного потока. `schedule_quit() -> None` — потокобезопасное завершение mainloop.
  - `class Tray(on_toggle_pause: Callable[[], bool], on_exit: Callable[[], None])` — `start() -> None` (detached-поток pystray), `notify(msg: str) -> None`, `stop() -> None`.

GUI-модули без юнит-тестов (по спеке) — проверяются ручным скриптом.

- [ ] **Step 1: Реализовать overlay.py**

`voiceflow/overlay.py`:
```python
import ctypes
import queue
import tkinter as tk

GWL_EXSTYLE = -20
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080

_STATES = {
    "recording": ("●  Запись…", "#c0392b"),
    "transcribing": ("⏳  Распознаю…", "#2c3e50"),
}


class Overlay:
    """Мини-окно поверх всех окон. Не забирает фокус (WS_EX_NOACTIVATE) —
    иначе вставка ушла бы в оверлей, а не в активное приложение."""

    def __init__(self):
        self._queue = queue.Queue()
        self._root = tk.Tk()
        self._root.withdraw()
        self._root.overrideredirect(True)
        self._root.attributes("-topmost", True)
        self._root.attributes("-alpha", 0.92)
        self._label = tk.Label(
            self._root, text="", font=("Segoe UI", 12, "bold"),
            fg="white", bg="#c0392b", padx=18, pady=8,
        )
        self._label.pack()
        w, h = 190, 44
        sw = self._root.winfo_screenwidth()
        sh = self._root.winfo_screenheight()
        self._root.geometry(f"{w}x{h}+{(sw - w) // 2}+{sh - 140}")
        self._no_activate_applied = False
        self._root.after(50, self._poll)

    def _apply_no_activate(self):
        hwnd = ctypes.windll.user32.GetParent(self._root.winfo_id()) or self._root.winfo_id()
        style = ctypes.windll.user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
        ctypes.windll.user32.SetWindowLongPtrW(
            hwnd, GWL_EXSTYLE, style | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW
        )
        self._no_activate_applied = True

    def _poll(self):
        try:
            while True:
                state = self._queue.get_nowait()
                if state == "quit":
                    self._root.destroy()
                    return
                if state == "hide":
                    self._root.withdraw()
                else:
                    text, bg = _STATES[state]
                    self._label.config(text=text, bg=bg)
                    self._root.deiconify()
                    if not self._no_activate_applied:
                        self._apply_no_activate()
        except queue.Empty:
            pass
        self._root.after(50, self._poll)

    # --- потокобезопасный интерфейс для Controller ---
    def show_recording(self):
        self._queue.put("recording")

    def show_transcribing(self):
        self._queue.put("transcribing")

    def hide(self):
        self._queue.put("hide")

    def schedule_quit(self):
        self._queue.put("quit")

    def run(self):
        self._root.mainloop()
```

- [ ] **Step 2: Реализовать tray.py**

`voiceflow/tray.py`:
```python
import threading

import pystray
from PIL import Image, ImageDraw


def _make_icon_image(color="#27ae60"):
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((8, 8, 56, 56), fill=color)
    d.ellipse((26, 18, 38, 40), fill="white")   # стилизованный микрофон
    d.rectangle((30, 40, 34, 50), fill="white")
    return img


class Tray:
    def __init__(self, on_toggle_pause, on_exit):
        self._on_toggle_pause = on_toggle_pause
        self._on_exit = on_exit
        self._paused = False
        self._icon = pystray.Icon(
            "VoiceFlow", _make_icon_image(), "VoiceFlow",
            menu=pystray.Menu(
                pystray.MenuItem(
                    lambda item: "Возобновить" if self._paused else "Пауза",
                    self._toggle,
                ),
                pystray.MenuItem("Выход", self._exit),
            ),
        )

    def _toggle(self, icon, item):
        self._paused = self._on_toggle_pause()
        color = "#e67e22" if self._paused else "#27ae60"
        self._icon.icon = _make_icon_image(color)

    def _exit(self, icon, item):
        threading.Thread(target=self._on_exit, daemon=True).start()

    def start(self):
        self._icon.run_detached()

    def notify(self, msg):
        try:
            self._icon.notify(msg, "VoiceFlow")
        except Exception:
            pass  # уведомление — best effort, не роняем обработку

    def stop(self):
        self._icon.stop()
```

- [ ] **Step 3: Скрипт ручной проверки оверлея**

`scripts/try_overlay.py`:
```python
"""Ручная проверка: оверлей показывает запись → распознавание → скрывается.
Проверить, что фокус НЕ уходит из активного окна (курсор в Блокноте должен мигать)."""
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from voiceflow.overlay import Overlay

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
```

Run: `.venv/Scripts/python scripts/try_overlay.py` (поставив курсор в Блокнот).
Expected: внизу по центру появляется «● Запись…» (красный), затем «⏳ Распознаю…» (тёмный), затем исчезает; курсор в Блокноте продолжает мигать (фокус не украден); скрипт завершается с «OK».

- [ ] **Step 4: Быстрая проверка трея**

Run:
```bash
.venv/Scripts/python -c "
import sys, time
sys.path.insert(0, '.')
from voiceflow.tray import Tray
t = Tray(on_toggle_pause=lambda: True, on_exit=lambda: None)
t.start(); t.notify('VoiceFlow запущен'); time.sleep(5); t.stop()
"
```
Expected: на 5 секунд в трее появляется зелёная иконка с микрофоном и всплывает уведомление.

- [ ] **Step 5: Прогон всех тестов (регрессия)**

Run: `.venv/Scripts/python -m pytest -v`
Expected: все тесты passed

- [ ] **Step 6: Commit**

```bash
git add voiceflow/overlay.py voiceflow/tray.py scripts/try_overlay.py
git commit -m "feat: recording overlay and tray icon"
```

---

### Task 8: app.py — сборка, автозагрузка, README

**Files:**
- Create: `voiceflow/app.py`, `voiceflow.bat`, `README.md`

**Interfaces:**
- Consumes: все модули Task 1–7 с сигнатурами из их блоков «Produces».
- Produces: `python -m voiceflow.app` — запуск приложения; `voiceflow.bat` — запуск без консоли.

- [ ] **Step 1: Реализовать app.py**

`voiceflow/app.py`:
```python
import logging
import logging.handlers
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _setup_logging():
    handler = logging.handlers.RotatingFileHandler(
        ROOT / "voiceflow.log", maxBytes=1_000_000, backupCount=1, encoding="utf-8"
    )
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[handler],
    )


def main():
    _setup_logging()
    log = logging.getLogger("voiceflow")
    log.info("Запуск VoiceFlow")

    from voiceflow.config import load_config
    cfg = load_config(ROOT / "config.json")

    # Тяжёлые импорты — после логирования, чтобы ошибки попали в лог.
    from voiceflow.controller import Controller
    from voiceflow.hotkey import HotkeyListener
    from voiceflow.overlay import Overlay
    from voiceflow.recorder import Recorder
    from voiceflow.transcriber import Transcriber
    from voiceflow.tray import Tray
    from voiceflow.typer import insert_text

    overlay = Overlay()

    tray = Tray(on_toggle_pause=lambda: controller.toggle_pause(), on_exit=lambda: shutdown())
    tray.start()
    tray.notify("Загружаю модель распознавания…")

    log.info("Загрузка модели %s (%s)", cfg["model"], cfg["device"])
    transcriber = Transcriber(cfg["model"], cfg["device"], cfg["compute_type"], cfg["language"])
    log.info("Модель загружена, устройство: %s", transcriber.device)

    recorder = Recorder(samplerate=cfg["samplerate"], device=cfg["input_device"])
    controller = Controller(
        recorder, transcriber, insert_text, overlay,
        min_duration_sec=cfg["min_duration_sec"],
        samplerate=cfg["samplerate"],
        paste_mode=cfg["paste_mode"],
        notify=tray.notify,
    )
    controller.start()

    listener = HotkeyListener(on_press=controller.on_press, on_release=controller.on_release)
    hotkey_thread = threading.Thread(target=listener.run, daemon=True)
    hotkey_thread.start()

    def shutdown():
        log.info("Завершение")
        listener.stop()
        controller.shutdown()
        tray.stop()
        overlay.schedule_quit()

    suffix = "" if transcriber.device == "cuda" else " (CPU — медленный режим!)"
    tray.notify(f"Готов. Зажмите правый Ctrl и говорите{suffix}")
    overlay.run()  # блокирует главный поток до schedule_quit()
    log.info("Остановлен")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Создать voiceflow.bat**

`voiceflow.bat`:
```bat
@echo off
start "" "%~dp0.venv\Scripts\pythonw.exe" -m voiceflow.app
```
(Запуск через `pythonw.exe` — без окна консоли; `start ""` — bat сразу завершается.)

- [ ] **Step 3: Написать README.md**

`README.md`:
```markdown
# VoiceFlow

Локальный аналог Wispr Flow для Windows: зажмите **правый Ctrl**, говорите,
отпустите — текст напечатается в активном окне. Распознавание — Whisper large-v3
локально на GPU (faster-whisper/CUDA), без облака и подписок.

## Установка

```
py -3.13 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

Первый запуск скачает модель (~3 ГБ).

## Запуск

Двойной клик по `voiceflow.bat` (или `.venv\Scripts\python -m voiceflow.app` для
запуска с консолью и видимыми ошибками). Иконка появится в трее; после
уведомления «Готов» можно диктовать.

## Автозагрузка

Win+R → `shell:startup` → создать там ярлык на `voiceflow.bat`.

## Настройка — config.json

| Ключ | По умолчанию | Значения |
|---|---|---|
| model | large-v3 | любая модель faster-whisper |
| device | auto | auto / cuda / cpu |
| compute_type | int8_float16 | float16, int8, … |
| language | auto | auto / ru / en |
| min_duration_sec | 0.3 | минимальная длительность записи |
| paste_mode | clipboard | clipboard (Ctrl+V) / type (посимвольно) |
| input_device | null | имя или индекс микрофона (см. `python -m sounddevice`) |
| samplerate | 16000 | не менять без необходимости |

## Диагностика

Ошибки пишутся в `voiceflow.log`. Если распознавание медленное — проверьте в логе,
что устройство `cuda`, а не `cpu`.
```

- [ ] **Step 4: Полный прогон тестов**

Run: `.venv/Scripts/python -m pytest -v`
Expected: все тесты passed

- [ ] **Step 5: Ручная e2e-проверка (чек-лист)**

Run: `.venv/Scripts/python -m voiceflow.app` (с консолью, чтобы видеть ошибки), дождаться уведомления «Готов». Затем проверить:

1. Блокнот: зажать правый Ctrl → «● Запись…» → сказать «Привет, это тест» → отпустить → текст появился, буфер обмена восстановлен (скопировать слово до теста и после вставки нажать Ctrl+V — вставится старое слово).
2. Терминал с Claude Code: продиктовать смешанную фразу («Сделай commit и push в main») → текст появился в строке ввода.
3. Короткое случайное нажатие правого Ctrl (<0.3 c) → ничего не вставлено, оверлей исчез.
4. Трей → «Пауза» → правый Ctrl не реагирует → «Возобновить» → снова работает.
5. Трей → «Выход» → процесс завершился (проверить в диспетчере задач).
6. `voiceflow.bat` → приложение запускается без окна консоли.

Expected: все 6 пунктов проходят. (Пункты требуют голоса/микрофона — исполнитель без ручного доступа просит пользователя пройти чек-лист.)

- [ ] **Step 6: Commit**

```bash
git add voiceflow/app.py voiceflow.bat README.md
git commit -m "feat: application entry point, autostart script and README"
```
