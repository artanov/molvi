"""ASR на Apple Silicon: mlx-whisper (Metal + unified memory).

Бенчмарк на M1 8 ГБ (фаза 1 порта, см. docs/macos-port.md): large-v3-turbo
расшифровывает 10.9-сек русскую фразу за ~1.9 с (RTF 0.18) при пике памяти
0.7 ГБ — ctranslate2 на маке CPU-only и в разы медленнее.

Интерфейс повторяет molvi.transcriber.Transcriber; device/compute_type —
виндовые ручки (cuda/int8), здесь принимаются и игнорируются: движок один.
"""
import logging

import numpy as np

try:
    import mlx_whisper
except ImportError as exc:  # Intel-мак: pip пропустил mlx-whisper по маркеру arm64
    raise ImportError(
        "Molvi для Mac работает только на Apple Silicon (M1 и новее): "
        "движок mlx-whisper недоступен на этом компьютере."
    ) from exc

from molvi.platform.darwin.models import REPOS

log = logging.getLogger(__name__)

# У mlx-whisper нет VAD-фильтра faster-whisper — сегменты «тишины» отсекаем
# порогами самого Whisper (как в его подавлении no_speech): иначе пауза с
# зажатым хоткеем печатала бы галлюцинации вроде «Продолжение следует…».
_NO_SPEECH_PROB = 0.6
_LOGPROB_FLOOR = -1.0
_SILENCE_RMS = 1e-4  # почти цифровая тишина — не будим модель вовсе


class Transcriber:
    def __init__(self, model_name, device, compute_type, language):
        self._language = None if language == "auto" else language
        # Незнакомое имя пропускаем как есть: прямой HF-репозиторий или путь.
        self._repo = REPOS.get(model_name, model_name)
        self.device = "mlx"
        # Прогрев: первый вызов качает веса с HF и грузит их в память
        # (mlx_whisper кэширует модель внутри) — первая диктовка не ждёт.
        mlx_whisper.transcribe(
            np.zeros(1600, dtype=np.float32), path_or_hf_repo=self._repo
        )
        log.info("mlx-whisper готов: %s", self._repo)

    def set_language(self, language):
        """Язык — параметр transcribe(), а не модели: смена не требует перезагрузки."""
        self._language = None if language == "auto" else language

    def transcribe(self, audio):
        if float(np.sqrt((audio ** 2).mean() or 0.0)) < _SILENCE_RMS:
            return ""
        result = mlx_whisper.transcribe(
            audio, path_or_hf_repo=self._repo, language=self._language
        )
        parts = []
        for seg in result.get("segments", []):
            if (seg.get("no_speech_prob", 0.0) > _NO_SPEECH_PROB
                    and seg.get("avg_logprob", 0.0) < _LOGPROB_FLOOR):
                continue  # модель сама считает сегмент тишиной
            parts.append(seg.get("text", "").strip())
        return " ".join(p for p in parts if p).strip()
