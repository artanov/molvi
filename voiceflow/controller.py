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
