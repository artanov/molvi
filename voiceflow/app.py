import logging
import logging.handlers
import threading

from voiceflow import paths


def _setup_logging():
    handler = logging.handlers.RotatingFileHandler(
        paths.log_path(), maxBytes=1_000_000, backupCount=1, encoding="utf-8"
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
        cfg = load_config(paths.config_path())

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

        overlay = Overlay(scale=cfg["overlay_scale"])
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
        last_good = {"model": cfg["model"], "language": cfg["language"]}

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

        cfg_lock = threading.Lock()

        def _reload_model(snapshot, token):
            try:
                new_tr = Transcriber(
                    snapshot["model"], snapshot["device"],
                    snapshot["compute_type"], snapshot["language"],
                )
                applied = controller.finish_model_reload(new_tr, token)
                log.info("Модель %s загружена, устройство: %s", snapshot["model"], new_tr.device)
                if applied:
                    last_good["model"] = snapshot["model"]
                    last_good["language"] = snapshot["language"]
                    tray.notify(f"Готов. Модель: {snapshot['model']}")
            except Exception as exc:
                log.exception("Не удалось загрузить модель %s", snapshot["model"])
                applied = controller.finish_model_reload(None, token)
                if applied:
                    with cfg_lock:
                        cfg["model"], cfg["language"] = last_good["model"], last_good["language"]
                        save_config(paths.config_path(), cfg)
                    tray.notify(
                        f"Не удалось загрузить модель: {exc}. Возвращены прежние настройки."
                    )

        def apply_settings(new_cfg, autostart_on):
            # вызывается в tk-потоке из SettingsWindow
            try:
                # Смена модели/языка детектируется и begin_model_reload()
                # вызывается в той же критической секции, что и cfg.update(),
                # иначе restore упавшей перезагрузки может проскочить между
                # release cfg_lock и begin_model_reload и затереть свежий выбор.
                reload_args = None
                with cfg_lock:
                    old_model_lang = (cfg["model"], cfg["language"])
                    cfg.update(new_cfg)
                    save_config(paths.config_path(), cfg)
                    if (cfg["model"], cfg["language"]) != old_model_lang:
                        token = controller.begin_model_reload()
                        snapshot = {
                            "model": cfg["model"],
                            "device": cfg["device"],
                            "compute_type": cfg["compute_type"],
                            "language": cfg["language"],
                        }
                        reload_args = (snapshot, token)
                listener.set_combo(_combo_from_cfg())
                sounds.set_enabled(cfg["sounds"])
                controller.set_device(cfg["input_device"])
                try:
                    if autostart_on:
                        autostart.enable(paths.autostart_command())
                    else:
                        autostart.disable()
                except OSError as exc:
                    log.exception("Автозапуск: ошибка реестра")
                    tray.notify(f"Не удалось изменить автозапуск: {exc}")
                if reload_args is not None:
                    tray.notify("Загружаю модель… Диктовка временно недоступна.")
                    threading.Thread(
                        target=_reload_model, args=reload_args, daemon=True
                    ).start()
                log.info("Настройки применены: hotkey=%s", cfg["hotkey"])
            except Exception as exc:
                log.exception("Не удалось применить настройки")
                tray.notify(f"Не удалось применить настройки: {exc}")

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
