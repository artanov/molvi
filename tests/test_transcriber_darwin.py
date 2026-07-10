"""mlx-обёртка ASR для macOS. mlx_whisper подменяется фейком в sys.modules —
тесты гоняются на любой ОС (сам mlx ставится только на Apple Silicon)."""
import sys
import types

import numpy as np
import pytest

AUDIO = np.full(16000, 0.05, dtype=np.float32)  # «речь»: заметно громче тишины


def _seg(text, no_speech=0.0, logprob=-0.2):
    return {"text": text, "no_speech_prob": no_speech, "avg_logprob": logprob}


class _CallLog(list):
    fake = None  # модуль-фейк, чтобы тесты меняли его сегменты


@pytest.fixture
def fake_mlx(monkeypatch):
    calls = _CallLog()
    fake = types.ModuleType("mlx_whisper")
    fake.segments = [_seg(" Привет,"), _seg(" мир! ")]

    def transcribe(audio, *, path_or_hf_repo, language=None, **kw):
        calls.append({"n": len(audio), "repo": path_or_hf_repo, "language": language})
        return {"text": "", "segments": fake.segments}

    fake.transcribe = transcribe
    monkeypatch.setitem(sys.modules, "mlx_whisper", fake)
    # Модуль обёртки мог быть импортирован раньше с другим фейком.
    monkeypatch.delitem(sys.modules, "molvi.platform.darwin.transcriber", raising=False)
    calls.fake = fake
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


def test_transcribe_joins_segments_and_strips(fake_mlx):
    tr = _make(fake_mlx)
    assert tr.transcribe(AUDIO) == "Привет, мир!"


def test_silence_short_circuits_without_model(fake_mlx):
    tr = _make(fake_mlx)
    n_warmup = len(fake_mlx)
    assert tr.transcribe(np.zeros(16000, dtype=np.float32)) == ""
    assert len(fake_mlx) == n_warmup  # модель не будили


def test_no_speech_segments_filtered(fake_mlx):
    # Аналог vad_filter из faster-whisper: галлюцинации на тишине не печатаем.
    fake_mlx.fake.segments = [
        _seg("Продолжение следует...", no_speech=0.95, logprob=-1.5),
        _seg("реальная речь"),
    ]
    tr = _make(fake_mlx)
    assert tr.transcribe(AUDIO) == "реальная речь"


def test_confident_segment_kept_despite_no_speech(fake_mlx):
    # Порог двойной, как у самого Whisper: высокий no_speech при уверенном
    # логпробе — сегмент оставляем.
    fake_mlx.fake.segments = [_seg("уверенный текст", no_speech=0.9, logprob=-0.3)]
    tr = _make(fake_mlx)
    assert tr.transcribe(AUDIO) == "уверенный текст"


def test_auto_language_passed_as_none(fake_mlx):
    tr = _make(fake_mlx)
    tr.transcribe(AUDIO)
    assert fake_mlx[-1]["language"] is None


def test_fixed_language_passed_through(fake_mlx):
    tr = _make(fake_mlx, language="ru")
    tr.transcribe(AUDIO)
    assert fake_mlx[-1]["language"] == "ru"


def test_set_language_changes_param(fake_mlx):
    tr = _make(fake_mlx)
    tr.set_language("ru")
    tr.transcribe(AUDIO)
    assert fake_mlx[-1]["language"] == "ru"
    tr.set_language("auto")
    tr.transcribe(AUDIO)
    assert fake_mlx[-1]["language"] is None


def test_win_model_names_map_to_mlx_repos(fake_mlx):
    # Конфиг переносим между ОС: виндовые имена моделей не должны ломать мак.
    _make(fake_mlx, model="large-v3")
    assert fake_mlx[0]["repo"] == "mlx-community/whisper-large-v3-mlx"


def test_unknown_model_passed_as_repo_path(fake_mlx):
    # Правленный руками конфиг с прямым HF-репо или локальным путём — пропускаем как есть.
    _make(fake_mlx, model="acme/custom-whisper")
    assert fake_mlx[0]["repo"] == "acme/custom-whisper"


def test_catalog_covers_fetch_and_presets():
    """Каталог models.py — общий источник: всё, что предлагают пресеты и умеет
    качать fetch, транскрайбер должен уметь открыть (и наоборот)."""
    import sys as _sys
    from molvi.platform.darwin.models import REPOS, SIZES
    assert set(REPOS) == set(SIZES)
    if _sys.platform == "darwin":
        import molvi.fetch as fetch
        assert fetch.MODEL_REPOS is REPOS
