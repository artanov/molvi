import numpy as np
import pytest

from molvi.recorder import Recorder


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

    import molvi.recorder as r
    monkeypatch.setattr(r.sd, "InputStream", FakeStream)
    rec = Recorder(samplerate=16000, device=None)
    rec._chunks = [np.zeros((10, 1), dtype=np.float32)]  # мусор от прошлой записи
    rec.start()
    assert created["samplerate"] == 16000
    assert created["channels"] == 1
    assert created["started"] is True
    assert rec._chunks == []


def test_failed_stream_start_closes_stream(monkeypatch):
    """stream.start() бросил (устройство занято) → стрим закрыт, хэндл не течёт."""
    events = []

    class FakeStream:
        def __init__(self, **kwargs):
            pass
        def start(self):
            events.append("start")
            raise OSError("device busy")
        def stop(self):
            events.append("stop")
        def close(self):
            events.append("close")

    import molvi.recorder as r
    monkeypatch.setattr(r.sd, "InputStream", FakeStream)
    rec = Recorder()
    with pytest.raises(OSError):
        rec.start()
    assert events == ["start", "close"]
    assert rec._stream is None
