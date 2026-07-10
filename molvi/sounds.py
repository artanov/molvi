import logging
from pathlib import Path

from molvi.platform import sounds as _backend

log = logging.getLogger(__name__)

ASSETS = Path(__file__).parent / "assets"

# Точка подмены в тестах; сам бэкенд платформенный (winsound / afplay).
_play_wav = _backend.play_wav


class Sounds:
    """Короткие сигналы начала/конца записи. Никогда не бросает исключений."""

    def __init__(self, enabled=True):
        self._enabled = enabled
        self._warned = set()

    def set_enabled(self, enabled):
        self._enabled = enabled

    def play_start(self):
        self._play("start.wav")

    def play_stop(self):
        self._play("stop.wav")

    def _play(self, name):
        if not self._enabled:
            return
        path = ASSETS / name
        if not path.is_file():
            if name not in self._warned:
                self._warned.add(name)
                log.warning("Звук %s не найден, сигнал пропущен", name)
            return
        try:
            _play_wav(str(path))
        except Exception:
            log.warning("Не удалось воспроизвести %s", name, exc_info=True)
