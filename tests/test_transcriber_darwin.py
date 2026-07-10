"""mlx-обёртка ASR для macOS. mlx_whisper подменяется фейком в sys.modules —
тесты гоняются на любой ОС (сам mlx ставится только на Apple Silicon)."""
import sys
import types

import numpy as np
import pytest


@pytest.fixture
def fake_mlx(monkeypatch):
    calls = []
    fake = types.ModuleType("mlx_whisper")

    def transcribe(audio, *, path_or_hf_repo, language=None, **kw):
        calls.append({"n": len(audio), "repo": path_or_hf_repo, "language": language})
        return {"text": "  Привет, мир!  "}

    fake.transcribe = transcribe
    monkeypatch.setitem(sys.modules, "mlx_whisper", fake)
    # Модуль обёртки мог быть импортирован раньше с другим фейком.
    monkeypatch.delitem(sys.modules, "molvi.platform.darwin.transcriber", raising=False)
    return calls


def _make(fake_calls, model="large-v3-turbo", language="auto"):
    from molvi.platform.darwin.transcriber import Transcriber
    return Transcriber(model, "auto", "int8_float16", language)


def test_init_warms_up_known_model(fake_mlx):
    tr = _make(fake_mlx)
    assert tr.device == "mlx"
    # Прогрев в конструкторе: веса качаются/грузятся до первой диктовки.
    assert len(fake_mlx) == 1
    assert fake_mlx[0]["repo"] == "mlx-community/whisper-large-v3-turbo"


def test_transcribe_strips_text(fake_mlx):
    tr = _make(fake_mlx)
    text = tr.transcribe(np.zeros(16000, dtype=np.float32))
    assert text == "Привет, мир!"


def test_auto_language_passed_as_none(fake_mlx):
    tr = _make(fake_mlx)
    tr.transcribe(np.zeros(16000, dtype=np.float32))
    assert fake_mlx[-1]["language"] is None


def test_fixed_language_passed_through(fake_mlx):
    tr = _make(fake_mlx, language="ru")
    tr.transcribe(np.zeros(16000, dtype=np.float32))
    assert fake_mlx[-1]["language"] == "ru"


def test_set_language_changes_param(fake_mlx):
    tr = _make(fake_mlx)
    tr.set_language("ru")
    tr.transcribe(np.zeros(16000, dtype=np.float32))
    assert fake_mlx[-1]["language"] == "ru"
    tr.set_language("auto")
    tr.transcribe(np.zeros(16000, dtype=np.float32))
    assert fake_mlx[-1]["language"] is None


def test_win_model_names_map_to_mlx_repos(fake_mlx):
    # Конфиг переносим между ОС: виндовые имена моделей не должны ломать мак.
    tr = _make(fake_mlx, model="large-v3")
    assert fake_mlx[0]["repo"] == "mlx-community/whisper-large-v3-mlx"


def test_unknown_model_passed_as_repo_path(fake_mlx):
    # Правленный руками конфиг с прямым HF-репо или локальным путём — пропускаем как есть.
    _make(fake_mlx, model="acme/custom-whisper")
    assert fake_mlx[0]["repo"] == "acme/custom-whisper"
