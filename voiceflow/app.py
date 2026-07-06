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

        from voiceflow.config import load_config, save_config
        cfg = load_config(ROOT / "config.json")

        # Тяжёлые импорты — после логирования, чтобы ошибки попали в лог.
        from voiceflow import autostart
        from voiceflow.controller import Controller
        from voiceflow.hotkey import (
            VK_LCONTROL, HotkeyListener, human_label, names_to_vks,
        )
        from voiceflow.overlay import Overlay
        from voiceflow.recorder import Recorder
        from voiceflow.settings import SettingsWindow
        from voiceflow.sounds import Sounds
        from voiceflow.transcriber import Transcriber
        from voiceflow.tray import Tray
        from voiceflow.typer import insert_text

        overlay = Overlay()
        sounds = Sounds(cfg["sounds"])

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
            on_settings=overlay.open_settings,
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
            sounds=sounds,
        )
        controller.start()

        def _combo_from_cfg():
            try:
                return names_to_vks(cfg["hotkey"])
            except ValueError:
                log.warning("Некорректный hotkey %r, использую ctrl_left", cfg["hotkey"])
                return [VK_LCONTROL]

        listener = HotkeyListener(
            on_press=controller.on_press,
            on_release=controller.on_release,
            combo=_combo_from_cfg(),
        )
        hotkey_thread = threading.Thread(target=listener.run, daemon=True)
        hotkey_thread.start()

        def _reload_model():
            try:
                new_tr = Transcriber(
                    cfg["model"], cfg["device"], cfg["compute_type"], cfg["language"]
                )
                controller.finish_model_reload(new_tr)
                log.info("Модель %s загружена, устройство: %s", cfg["model"], new_tr.device)
                tray.notify(f"Готов. Модель: {cfg['model']}")
            except Exception as exc:
                log.exception("Не удалось загрузить модель %s", cfg["model"])
                controller.finish_model_reload(None)
                tray.notify(f"Не удалось загрузить модель: {exc}. Работает прежняя.")

        def apply_settings(new_cfg, autostart_on):
            # вызывается в tk-потоке из SettingsWindow
            old_model = (cfg["model"], cfg["language"])
            cfg.update(new_cfg)
            save_config(ROOT / "config.json", cfg)
            listener.set_combo(_combo_from_cfg())
            sounds.set_enabled(cfg["sounds"])
            controller.set_device(cfg["input_device"])
            try:
                if autostart_on:
                    autostart.enable(str(ROOT / "voiceflow.bat"))
                else:
                    autostart.disable()
            except OSError as exc:
                log.exception("Автозапуск: ошибка реестра")
                tray.notify(f"Не удалось изменить автозапуск: {exc}")
            if (cfg["model"], cfg["language"]) != old_model:
                controller.begin_model_reload()
                tray.notify("Загружаю модель… Диктовка временно недоступна.")
                threading.Thread(target=_reload_model, daemon=True).start()
            log.info("Настройки применены: hotkey=%s", cfg["hotkey"])

        settings_ref = {"win": None}

        def open_settings_window():
            # вызывается в tk-потоке из Overlay._poll
            win = settings_ref["win"]
            if win is not None and win.alive():
                win.lift_window()
                return
            settings_ref["win"] = SettingsWindow(
                overlay.root, cfg, listener, apply_settings
            )

        overlay.set_settings_opener(open_settings_window)

        suffix = "" if transcriber.device == "cuda" else " (CPU — медленный режим!)"
        tray.notify(f"Готов. Зажмите {human_label(cfg['hotkey'])} и говорите{suffix}")
        overlay.run()  # блокирует главный поток до schedule_quit()
        log.info("Остановлен")
    except Exception:
        log.exception("Фатальная ошибка")
        raise


if __name__ == "__main__":
    main()
