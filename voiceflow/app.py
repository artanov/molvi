import logging
import logging.handlers
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _setup_logging():
    handler = logging.handlers.RotatingFileHandler(
        ROOT / "voiceflow.log", maxBytes=1_000_000, backupCount=1, encoding="utf-8"
    )
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[handler],
    )


def main():
    _setup_logging()
    log = logging.getLogger("voiceflow")
    try:
        log.info("Запуск VoiceFlow")

        from voiceflow.config import load_config
        cfg = load_config(ROOT / "config.json")

        # Тяжёлые импорты — после логирования, чтобы ошибки попали в лог.
        from voiceflow.controller import Controller
        from voiceflow.hotkey import HotkeyListener
        from voiceflow.overlay import Overlay
        from voiceflow.recorder import Recorder
        from voiceflow.transcriber import Transcriber
        from voiceflow.tray import Tray
        from voiceflow.typer import insert_text

        overlay = Overlay()

        # Коллбэки трея могут сработать до конца загрузки модели —
        # до присваивания controller/listener они должны быть безопасны.
        controller = None
        listener = None

        def shutdown():
            log.info("Завершение")
            if listener is not None:
                listener.stop()
            if controller is not None:
                controller.shutdown()
            tray.stop()
            overlay.schedule_quit()

        tray = Tray(
            on_toggle_pause=lambda: controller.toggle_pause() if controller is not None else False,
            on_exit=shutdown,
        )
        tray.start()
        tray.notify("Загружаю модель распознавания…")

        log.info("Загрузка модели %s (%s)", cfg["model"], cfg["device"])
        transcriber = Transcriber(cfg["model"], cfg["device"], cfg["compute_type"], cfg["language"])
        log.info("Модель загружена, устройство: %s", transcriber.device)

        recorder = Recorder(samplerate=cfg["samplerate"], device=cfg["input_device"])
        controller = Controller(
            recorder, transcriber, insert_text, overlay,
            min_duration_sec=cfg["min_duration_sec"],
            samplerate=cfg["samplerate"],
            paste_mode=cfg["paste_mode"],
            notify=tray.notify,
        )
        controller.start()

        from voiceflow.hotkey import VK_LCONTROL, names_to_vks
        try:
            combo = names_to_vks(cfg["hotkey"])
        except ValueError:
            log.warning("Некорректный hotkey %r, использую ctrl_left", cfg["hotkey"])
            combo = [VK_LCONTROL]
        listener = HotkeyListener(
            on_press=controller.on_press,
            on_release=controller.on_release,
            combo=combo,
        )
        hotkey_thread = threading.Thread(target=listener.run, daemon=True)
        hotkey_thread.start()

        from voiceflow.hotkey import human_label
        key_name = human_label(cfg["hotkey"])
        suffix = "" if transcriber.device == "cuda" else " (CPU — медленный режим!)"
        tray.notify(f"Готов. Зажмите {key_name} и говорите{suffix}")
        overlay.run()  # блокирует главный поток до schedule_quit()
        log.info("Остановлен")
    except Exception:
        log.exception("Фатальная ошибка")
        raise


if __name__ == "__main__":
    main()
