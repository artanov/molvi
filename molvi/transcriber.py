import ctypes
import logging
import os
import sys
from pathlib import Path

log = logging.getLogger(__name__)


def _add_cuda_dll_dirs():
    """cuBLAS/cuDNN/NVRTC ставятся pip-пакетами nvidia-*; их DLL надо добавить в поиск.

    os.add_dll_directory недостаточно: ctranslate2 подгружает cublas64_12.dll
    лениво во время encode() через LoadLibrary, который ищет DLL по PATH,
    поэтому каталоги надо добавить и туда.
    """
    for sub in ("nvidia/cublas/bin", "nvidia/cudnn/bin", "nvidia/cuda_nvrtc/bin"):
        p = Path(sys.prefix) / "Lib" / "site-packages" / Path(sub)
        if p.is_dir():
            os.add_dll_directory(str(p))
            os.environ["PATH"] = str(p) + os.pathsep + os.environ["PATH"]
    from molvi import paths
    app_cuda = paths.cuda_dir()
    if app_cuda.is_dir():
        os.add_dll_directory(str(app_cuda))
        os.environ["PATH"] = str(app_cuda) + os.pathsep + os.environ["PATH"]


if sys.platform == "win32":
    _add_cuda_dll_dirs()

from faster_whisper import WhisperModel  # noqa: E402

from molvi.i18n import tr


def _cuda_libs_loadable():
    """cuBLAS/cuDNN грузятся ctranslate2 лениво при первом encode(): без них
    cuda-модель «успешно» создаётся, а первая диктовка падает — и повторный
    encode после сбоя зависает внутри ctranslate2. Проверяем заранее."""
    if sys.platform != "win32":
        return False  # CUDA бывает только на Windows-машинах с NVIDIA
    try:
        ctypes.WinDLL("cublas64_12.dll")
        ctypes.WinDLL("cudnn64_9.dll")
        return True
    except OSError:
        return False


class Transcriber:
    def __init__(self, model_name, device, compute_type, language):
        self._language = None if language == "auto" else language
        if device in ("auto", "cuda") and not _cuda_libs_loadable():
            if device == "cuda":
                raise RuntimeError(tr("transcriber.cuda_missing"))
            log.warning("Библиотеки NVIDIA не найдены — распознавание на CPU")
            device = "cpu"
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

    def set_language(self, language):
        """Язык — параметр transcribe(), а не модели: смена не требует перезагрузки."""
        self._language = None if language == "auto" else language

    def transcribe(self, audio):
        segments, _info = self._model.transcribe(
            audio,
            language=self._language,
            beam_size=5,
            vad_filter=True,
        )
        return " ".join(s.text.strip() for s in segments).strip()
