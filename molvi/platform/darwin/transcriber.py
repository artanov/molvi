"""ASR на Apple Silicon: mlx-whisper (Metal + unified memory).

Бенчмарк на M1 8 ГБ (фаза 1 порта, см. docs/macos-port.md): large-v3-turbo
расшифровывает 10.9-сек русскую фразу за ~1.9 с (RTF 0.18) при пике памяти
0.7 ГБ — ctranslate2 на маке CPU-only и в разы медленнее.

Интерфейс повторяет molvi.transcriber.Transcriber; device/compute_type —
виндовые ручки (cuda/int8), здесь принимаются и игнорируются: движок один.
"""
import logging

import numpy as np

import mlx_whisper

log = logging.getLogger(__name__)

# Имена моделей из конфига (общие с Windows-версией) → репозитории mlx-community.
# Незнакомое имя пропускаем как есть: это прямой HF-репозиторий или локальный путь.
REPOS = {
    "large-v3-turbo": "mlx-community/whisper-large-v3-turbo",
    "large-v3": "mlx-community/whisper-large-v3-mlx",
    "medium": "mlx-community/whisper-medium-mlx",
    "small": "mlx-community/whisper-small-mlx",
    "base": "mlx-community/whisper-base-mlx",
}


class Transcriber:
    def __init__(self, model_name, device, compute_type, language):
        self._language = None if language == "auto" else language
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
        result = mlx_whisper.transcribe(
            audio, path_or_hf_repo=self._repo, language=self._language
        )
        return result["text"].strip()
