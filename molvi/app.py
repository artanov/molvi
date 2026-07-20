import logging
import logging.handlers
import os
import sys
import threading

from molvi import paths


def _ensure_std_streams():
    """В windowed-сборке (PyInstaller console=False) sys.stdout/stderr == None;
    любая библиотека, пишущая в консоль (tqdm внутри huggingface_hub при докачке
    модели), падает с 'NoneType object has no attribute write'. Подменяем на
    devnull, чтобы такой вывод молча уходил в никуда."""
    devnull = None
    for name in ("stdout", "stderr"):
        if getattr(sys, name) is None:
            if devnull is None:
                devnull = open(os.devnull, "w", encoding="utf-8")
            setattr(sys, name, devnull)


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
    _ensure_std_streams()
    from molvi import migrate
    migrate.run()
    _setup_logging()
    log = logging.getLogger("molvi")
    try:
        log.info("Запуск Molvi")

        from molvi import i18n
        from molvi.i18n import tr
        from molvi.config import load_config, save_config
        cfg_file = paths.config_path()
        if not cfg_file.exists():
            i18n.set_language("auto")   # мастер стартует на языке системы
            log.info("config.json не найден — запускаю мастер первого запуска")
            try:
                from molvi.wizard import Wizard
                cfg = Wizard().run()
            except Exception:
                log.exception("Мастер первого запуска упал — значения по умолчанию")
                cfg = load_config(cfg_file)
            save_config(cfg_file, cfg)
        else:
            cfg = load_config(cfg_file)
        i18n.set_language(cfg.get("ui_language", "auto"))

        # Тяжёлые импорты — после логирования, чтобы ошибки попали в лог.
        # transcriber импортируется НИЖЕ — после докачки CUDA-DLL: его
        # _add_cuda_dll_dirs() добавляет каталог в поиск только если тот
        # уже существует и наполнен.
        from molvi.controller import Controller
        from molvi.overlay import Overlay
        from molvi.platform import autostart
        from molvi.platform import hotkey as hk
        from molvi.platform import typer
        from molvi.recorder import Recorder
        from molvi.settings import SettingsWindow
        from molvi.sounds import Sounds
        from molvi.tray import Tray

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

        def copy_last_to_clipboard():
            # Получаем последний распознанный текст; controller может быть ещё
            # None, если кликнули до конца загрузки модели — тот же случай,
            # что и «диктовок ещё не было»: пункт меню всегда активен (pystray
            # перечитывает enabled только при update_menu()), поэтому клик без
            # текста — штатная ветка с подсказкой, а не тихий no-op.
            text = controller.last_text() if controller is not None else None
            if text is None:
                tray.notify(tr("app.notify.nothing_to_copy"))
                return
            try:
                typer.copy_to_clipboard(text)
            except Exception as exc:
                log.exception("Не удалось скопировать текст в буфер")
                tray.notify(tr("app.notify.copy_failed", exc=exc))
                return
            tray.notify(tr("app.notify.copied"))

        tray = Tray(
            on_toggle_pause=lambda: controller.toggle_pause() if controller is not None else False,
            on_exit=shutdown,
            on_settings=overlay.open_settings,
            on_copy_last=copy_last_to_clipboard,
        )
        tray.start()

        # Если шаг загрузки в мастере пропустили, CUDA-DLL иначе не появятся
        # никогда: cuda-модель «успешно» создаётся без них, а первая диктовка
        # падает. Докачиваем при старте (только frozen: в dev DLL из venv).
        if (paths.is_frozen() and cfg["device"] in ("auto", "cuda")
                and not any(paths.cuda_dir().glob("*.dll"))):
            from molvi import fetch, gpu
            if gpu.detect_nvidia() is not None:
                tray.notify(tr("app.notify.cuda_download"))
                try:
                    import tempfile
                    paths.cuda_dir().mkdir(parents=True, exist_ok=True)
                    with tempfile.TemporaryDirectory() as tmp:
                        fetch.fetch_cuda(paths.cuda_dir(), tmp)
                    log.info("CUDA-библиотеки докачаны")
                except Exception:
                    log.exception("Не удалось скачать библиотеки NVIDIA")
                    tray.notify(tr("app.notify.cuda_failed"))

        tray.notify(tr("app.notify.loading_model"))
        if sys.platform == "darwin":
            from molvi.platform.darwin.transcriber import Transcriber
        else:
            from molvi.transcriber import Transcriber

        log.info("Загрузка модели %s (%s)", cfg["model"], cfg["device"])
        transcriber = Transcriber(cfg["model"], cfg["device"], cfg["compute_type"], cfg["language"])
        log.info("Модель загружена, устройство: %s", transcriber.device)
        last_good = {"model": cfg["model"], "language": cfg["language"]}

        recorder = Recorder(samplerate=cfg["samplerate"], device=cfg["input_device"])
        overlay.set_level_source(lambda: recorder.level)  # эквалайзер дышит голосом
        controller = Controller(
            recorder, transcriber, typer.insert_text, overlay,
            min_duration_sec=cfg["min_duration_sec"],
            samplerate=cfg["samplerate"],
            paste_mode=cfg["paste_mode"],
            notify=tray.notify,
            sounds=sounds,
            paste_hint=typer.PASTE_HINT,
            target_fns=(typer.get_target, typer.target_is_foreground,
                        typer.activate_target),
        )
        controller.start()

        def _combo_from_cfg():
            try:
                return hk.names_to_vks(cfg["hotkey"])
            except ValueError:
                log.warning("Некорректный hotkey %r, использую %s",
                            cfg["hotkey"], hk.DEFAULT_HOTKEY)
                return hk.names_to_vks(hk.DEFAULT_HOTKEY)

        listener = hk.HotkeyListener(
            on_press=controller.on_press,
            on_release=controller.on_release,
            combo=_combo_from_cfg(),
            on_esc=controller.cancel_pending,
        )

        def _run_listener():
            # Поток — daemon, его traceback в windowed-сборке ушёл бы в devnull:
            # без уведомления пользователь видел бы «Готов», а диктовка молчала.
            try:
                listener.run()
            except Exception as exc:
                listener.dead = True  # капчер в настройках не будет ждать вечно
                log.exception("Хук клавиатуры не запустился")
                tray.notify(tr("app.notify.hotkey_broken", exc=exc))

        hotkey_thread = threading.Thread(target=_run_listener, daemon=True)
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
                    tray.notify(tr("app.notify.model_ready", model=snapshot["model"]))
            except Exception as exc:
                log.exception("Не удалось загрузить модель %s", snapshot["model"])
                applied = controller.finish_model_reload(None, token)
                if applied:
                    with cfg_lock:
                        cfg["model"], cfg["language"] = last_good["model"], last_good["language"]
                        save_config(paths.config_path(), cfg)
                    tray.notify(tr("app.notify.model_failed", exc=exc))

        def apply_settings(new_cfg, autostart_on):
            # вызывается в tk-потоке из SettingsWindow
            try:
                # Смена модели/языка детектируется и begin_model_reload()
                # вызывается в той же критической секции, что и cfg.update(),
                # иначе restore упавшей перезагрузки может проскочить между
                # release cfg_lock и begin_model_reload и затереть свежий выбор.
                reload_args = None
                with cfg_lock:
                    old_model = cfg["model"]
                    old_language = cfg["language"]
                    old_ui_language = cfg["ui_language"]
                    cfg.update(new_cfg)
                    save_config(paths.config_path(), cfg)
                    if cfg["ui_language"] != old_ui_language:
                        # Меню трея перечитает подписи; открытые окна
                        # перерисуются при следующем открытии.
                        i18n.set_language(cfg["ui_language"])
                        tray.refresh()
                    if cfg["model"] != old_model:
                        token = controller.begin_model_reload()
                        snapshot = {
                            "model": cfg["model"],
                            "device": cfg["device"],
                            "compute_type": cfg["compute_type"],
                            "language": cfg["language"],
                        }
                        reload_args = (snapshot, token)
                    elif cfg["language"] != old_language:
                        # Язык — параметр transcribe(), полная перезагрузка не
                        # нужна (она держала бы 2 модели в VRAM и блокировала
                        # диктовку на минуты).
                        controller.set_language(cfg["language"])
                        last_good["language"] = cfg["language"]
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
                    tray.notify(tr("app.notify.autostart_failed", exc=exc))
                if reload_args is not None:
                    tray.notify(tr("app.notify.model_reloading"))
                    threading.Thread(
                        target=_reload_model, args=reload_args, daemon=True
                    ).start()
                log.info("Настройки применены: hotkey=%s", cfg["hotkey"])
            except Exception as exc:
                log.exception("Не удалось применить настройки")
                tray.notify(tr("app.notify.settings_failed", exc=exc))

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

        suffix = ("" if transcriber.device in ("cuda", "mlx")
                  else tr("app.notify.cpu_suffix"))
        tray.notify(tr("app.notify.ready",
                       hotkey=hk.human_label(cfg["hotkey"]), suffix=suffix))
        overlay.run()  # блокирует главный поток до schedule_quit()
        log.info("Остановлен")
    except Exception as exc:
        log.exception("Фатальная ошибка")
        _show_fatal_error(exc)
        raise


def _show_fatal_error(exc):
    """Best-effort окно с ошибкой: в windowed-сборке молчаливая смерть выглядит
    как «приложение просто не запускается» — особенно в автозапуске."""
    if os.environ.get("MOLVI_NO_ERROR_DIALOG"):
        return  # smoke-тест в CI: модальное окно повесило бы процесс «живым»
    try:
        import tkinter as tk
        from tkinter import messagebox

        from molvi.i18n import tr

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "Molvi",
            tr("app.fatal", exc=exc, log_path=paths.log_path()),
        )
        root.destroy()
    except Exception:
        pass  # нет дисплея/tk — хотя бы лог остался


if __name__ == "__main__":
    main()
