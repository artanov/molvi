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
        import molvi.transcriber as t
        monkeypatch.setattr(t, "WhisperModel", _fake_model_factory(calls, **kw))
        return calls
    return _patch


def test_joins_segments_and_strips(patch_model):
    from molvi.transcriber import Transcriber
    calls = patch_model(segments=[FakeSegment(" Привет,"), FakeSegment(" мир! ")])
    tr = Transcriber("large-v3", "cpu", "int8", "auto")
    text = tr.transcribe(np.zeros(16000, dtype=np.float32))
    assert text == "Привет, мир!"


def test_empty_segments_give_empty_string(patch_model):
    from molvi.transcriber import Transcriber
    patch_model(segments=[])
    tr = Transcriber("large-v3", "cpu", "int8", "auto")
    assert tr.transcribe(np.zeros(16000, dtype=np.float32)) == ""


def test_auto_language_passed_as_none(patch_model):
    from molvi.transcriber import Transcriber
    calls = patch_model(segments=[])
    tr = Transcriber("large-v3", "cpu", "int8", "auto")
    tr.transcribe(np.zeros(16000, dtype=np.float32))
    kwargs = calls[-1]["transcribe_kwargs"]
    assert kwargs["language"] is None


def test_fixed_language_passed_through(patch_model):
    from molvi.transcriber import Transcriber
    calls = patch_model(segments=[])
    tr = Transcriber("large-v3", "cpu", "int8", "ru")
    tr.transcribe(np.zeros(16000, dtype=np.float32))
    assert calls[-1]["transcribe_kwargs"]["language"] == "ru"


def test_cuda_failure_falls_back_to_cpu(patch_model):
    from molvi.transcriber import Transcriber
    calls = patch_model(fail_on_cuda=True)
    tr = Transcriber("large-v3", "auto", "int8_float16", "auto")
    assert tr.device == "cpu"
    assert calls[0]["device"] == "cuda"
    assert calls[1] == {"device": "cpu", "compute_type": "int8"}
