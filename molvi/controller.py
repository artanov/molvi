import logging
import queue
import threading

from molvi.i18n import tr

log = logging.getLogger(__name__)


class Controller:
    """Связывает hotkey → запись → распознавание → вставку.

    on_press/on_release зовутся из потока хука клавиатуры и не блокируются:
    тяжёлая работа уходит в рабочий поток через очередь.
    """

    def __init__(self, recorder, transcriber, insert_fn, ui, *,
                 min_duration_sec=0.3, samplerate=16000,
                 paste_mode="clipboard", notify=None, sounds=None,
                 paste_hint="Ctrl+V", target_fns=None):
        self._recorder = recorder
        self._transcriber = transcriber
        self._insert_fn = insert_fn
        self._ui = ui
        self._min_samples = int(min_duration_sec * samplerate)
        self._samplerate = samplerate
        self._paste_mode = paste_mode
        self._notify = notify or (lambda msg: None)
        self._sounds = sounds
        self._paste_hint = paste_hint  # подпись «вставить» на этой ОС (Ctrl+V/Cmd+V)
        self._jobs = queue.Queue()
        self._worker = None
        self._recording = False
        self._paused = False
        self._reloading = False
        self._reload_token = 0
        self._last_text = None  # последняя расшифровка — для «Скопировать последний текст»
        self._lock = threading.Lock()
        # Функции цели вставки (get, is_foreground, activate) — платформенные,
        # передаются снаружи: контроллер не импортирует platform-модули.
        if target_fns is not None:
            self._get_target, self._target_is_foreground, self._activate_target = target_fns
        else:
            self._get_target = self._target_is_foreground = self._activate_target = None

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

    def set_device(self, device):
        self._recorder.device = device

    def set_language(self, language):
        """Сменить язык распознавания на лету — без перезагрузки модели."""
        with self._lock:
            self._transcriber.set_language(language)

    def last_text(self):
        """Последняя успешная расшифровка (для пункта трея); None — диктовок не было."""
        with self._lock:
            return self._last_text

    def _insert_allowed(self, target):
        """Фокус там же — вставляем; ушёл — возвращаем; не вышло — не
        вставляем вслепую в чужое окно (текст уже спасён в _last_text)."""
        if target is None or self._target_is_foreground is None:
            return True
        try:
            if self._target_is_foreground(target):
                return True
            return bool(self._activate_target(target))
        except Exception:
            log.exception("Не удалось вернуть фокус целевому окну")
            return False

    def begin_model_reload(self):
        with self._lock:
            self._reloading = True
            self._reload_token += 1
            return self._reload_token

    def finish_model_reload(self, transcriber=None, token=None):
        """Возвращает True, если применено; False — если поток устарел (проигнорирован)."""
        with self._lock:
            if token is not None and token != self._reload_token:
                return False  # устаревший поток перезагрузки — игнорируем
            if transcriber is not None:
                self._transcriber = transcriber
            self._reloading = False
            return True

    def on_press(self):
        # recorder.start() — внутри лока: иначе параллельный on_release
        # (например, из set_combo при смене хоткея) мог бы проскочить между
        # выставлением флага и стартом стрима — стрим остался бы открытым
        # навсегда без записи.
        with self._lock:
            if self._paused or self._recording or self._reloading:
                return
            try:
                self._recorder.start()
            except Exception as exc:
                log.exception("Не удалось начать запись")
                self._notify(tr("controller.mic_unavailable", exc=exc))
                self._ui.hide()
                return
            self._recording = True
        self._ui.show_recording()
        if self._sounds is not None:
            self._sounds.play_start()

    def on_release(self):
        with self._lock:
            if not self._recording:
                return
            self._recording = False
            try:
                audio = self._recorder.stop()
            except Exception as exc:
                log.exception("Не удалось остановить запись")
                self._notify(tr("controller.record_error", exc=exc))
                self._ui.hide()
                return
        if len(audio) < self._min_samples:
            self._ui.hide()
            return
        log.info("Запись %.1f c", len(audio) / self._samplerate)
        self._ui.show_transcribing()
        target = None
        if self._get_target is not None:
            try:
                target = self._get_target()
            except Exception:
                # Нет цели — работаем по-старому: вставка в текущее окно.
                log.exception("Не удалось определить целевое окно")
        self._jobs.put((audio, target))
        if self._sounds is not None:
            self._sounds.play_stop()

    def _run(self):
        while True:
            job = self._jobs.get()
            if job is None:
                return
            audio, target = job
            try:
                text = self._transcriber.transcribe(audio)
            except Exception as exc:
                log.exception("Ошибка распознавания")
                self._notify(tr("controller.transcribe_error", exc=exc))
                text = None
            if text is not None:
                log.info("Распознано %d символов", len(text))
            if text:
                # Сохраняем до вставки: если вставка упадёт или уйдёт не в то
                # окно, текст можно забрать через трей.
                with self._lock:
                    self._last_text = text
                if self._insert_allowed(target):
                    try:
                        self._insert_fn(text, self._paste_mode)
                    except Exception as exc:
                        log.exception("Ошибка вставки текста")
                        self._notify(tr("controller.paste_error",
                                        exc=exc, paste_hint=self._paste_hint))
                else:
                    self._notify(tr("controller.target_lost"))
            with self._lock:
                still_recording = self._recording
            if not still_recording:
                self._ui.hide()
