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
