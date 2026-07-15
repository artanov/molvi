"""Мастер первого запуска: железо → докачка → микрофон → клавиша.

Любая ошибка шага не роняет мастер: шаг можно пропустить, действуют дефолты.
Окно закрыто крестиком — возвращаются накопленные к этому моменту значения.
"""
import logging
import sys
import tempfile
import threading
import tkinter as tk
from tkinter import messagebox, ttk

import numpy as np
import sounddevice as sd

from molvi import fetch, gpu, i18n, paths
from molvi.i18n import tr
from molvi.platform import hotkey as hk
from molvi.config import DEFAULTS
from molvi.settings import dedupe_input_devices, quality_index_for_model, quality_presets

log = logging.getLogger(__name__)


def resolve_device(model, recommended_device):
    """device для выбранной модели: large-v3 всегда пробует GPU (auto),
    остальные — что рекомендовано для железа. Не зависит от порядка кликов."""
    return "auto" if model == "large-v3" else recommended_device


def vram_label(vram_mb):
    """Человекочитаемый объём видеопамяти («8 ГБ», «512 МБ» — не «0 ГБ»)."""
    if vram_mb >= 1024:
        return f"{vram_mb // 1024} {tr('unit.gb')}"
    return f"{vram_mb} {tr('unit.mb')}"


class Wizard:
    def __init__(self):
        self._cfg = dict(DEFAULTS)
        self._gpu = gpu.detect_nvidia()
        model, device = gpu.recommend(self._gpu)
        self._cfg["model"], self._cfg["device"] = model, device
        self._rec_device = device      # рекомендация для железа — база resolve_device
        self._need_cuda = device == "auto" and sys.platform == "win32"

        self._root = tk.Tk()
        self._root.title(tr("wizard.title"))
        self._root.resizable(False, False)
        self._root.attributes("-topmost", True)
        self._body = ttk.Frame(self._root, padding=20, width=560, height=330)
        self._body.pack(fill="both", expand=True)
        self._body.pack_propagate(False)
        nav = ttk.Frame(self._root, padding=(20, 0, 20, 16))
        nav.pack(fill="x")
        # Текст кнопок ставит _show_step на каждой отрисовке — он же
        # актуален после смены языка на первом шаге.
        self._back_btn = ttk.Button(nav, command=self._go_back)
        self._back_btn.pack(side="left")
        self._next_btn = ttk.Button(nav, command=self._go_next)
        self._next_btn.pack(side="right")

        self._steps = [self._step_language, self._step_welcome, self._step_hardware,
                       self._step_download, self._step_mic]
        if sys.platform == "darwin":
            # TCC: без Input Monitoring не работает клавиша, без
            # Accessibility — вставка. Спрашиваем до шага с хоткеем.
            self._steps.append(self._step_permissions)
        self._steps += [self._step_hotkey, self._step_done]
        self._idx = 0
        self._download_thread = None
        self._download_error = None
        self._cancel_download = False
        self._progress = {"text": "", "percent": 0.0, "done": False}
        self._mic_stream = None
        self._mic_level = 0.0
        self._listener = None
        self._listener_thread = None
        self._capture_state = "idle"
        self._perm_probe = None
        self._perm_rows = []
        self._perm_warned = False

        self._root.protocol("WM_DELETE_WINDOW", self._finish)
        self._show_step()

    # --- каркас ---
    def run(self):
        self._root.mainloop()
        return self._cfg

    def _clear(self):
        self._close_mic()
        for child in self._body.winfo_children():
            child.destroy()

    def _show_step(self):
        self._clear()
        self._back_btn.config(text=tr("wizard.back"),
                              state="normal" if self._idx > 0 else "disabled")
        self._next_btn.config(
            text=tr("wizard.finish") if self._idx == len(self._steps) - 1 else tr("wizard.next"),
            state="normal")
        try:
            self._steps[self._idx]()
        except Exception:
            log.exception("Шаг мастера %d упал — пропускаю", self._idx)
            ttk.Label(self._body, text=tr("wizard.step_failed")).pack()

    def _go_next(self):
        if self._idx == len(self._steps) - 1:
            self._finish()
            return
        self._idx += 1
        self._show_step()

    def _go_back(self):
        if self._idx > 0:
            self._idx -= 1
            self._show_step()

    def _finish(self):
        if self._download_thread is not None and self._download_thread.is_alive():
            if not messagebox.askyesno("Molvi", tr("wizard.confirm_quit")):
                return
            self._cancel_download = True
        self._close_mic()
        if self._listener is not None:
            self._listener.stop()
        self._root.destroy()

    def _title(self, text):
        ttk.Label(self._body, text=text, font=("Segoe UI", 13, "bold")).pack(
            anchor="w", pady=(0, 12))

    # --- шаги ---
    def _step_language(self):
        self._title(tr("wizard.language.title"))
        self._lang_var = tk.StringVar(value=i18n.current_language())
        for label, code in (("Русский", "ru"), ("English", "en")):
            ttk.Radiobutton(self._body, text=label, variable=self._lang_var,
                            value=code, command=self._on_language).pack(anchor="w", pady=2)

    def _on_language(self):
        code = self._lang_var.get()
        self._cfg["ui_language"] = code
        i18n.set_language(code)
        self._root.title(tr("wizard.title"))
        self._show_step()  # перерисовать шаг и кнопки уже на новом языке

    def _step_welcome(self):
        self._title(tr("wizard.welcome.title"))
        ttk.Label(self._body, wraplength=500, justify="left",
                  text=tr("wizard.welcome.body")).pack(anchor="w")

    def _step_hardware(self):
        self._title(tr("wizard.hw.title"))
        if sys.platform == "darwin":
            found = tr("wizard.hw.mac")
        elif self._gpu:
            found = tr("wizard.hw.gpu", name=self._gpu["name"],
                       vram=vram_label(self._gpu["vram_mb"]))
        else:
            found = tr("wizard.hw.nogpu")
        ttk.Label(self._body, text=found, wraplength=500, justify="left").pack(
            anchor="w", pady=(0, 10))
        self._quality_var = tk.IntVar(value=quality_index_for_model(self._cfg["model"]))
        for i, (label, _model) in enumerate(quality_presets()):
            ttk.Radiobutton(self._body, text=label, variable=self._quality_var,
                            value=i, command=self._on_quality).pack(anchor="w", pady=2)

    def _on_quality(self):
        model = quality_presets()[self._quality_var.get()][1]
        self._cfg["model"] = model
        self._cfg["device"] = resolve_device(model, self._rec_device)
        self._need_cuda = self._cfg["device"] == "auto" and sys.platform == "win32"

    def _step_download(self):
        self._title(tr("wizard.dl.title"))
        need_dlls = self._need_cuda and not any(paths.cuda_dir().glob("*.dll"))
        size_note = fetch.MODEL_SIZES[self._cfg["model"]] / 1e9
        parts = [tr("wizard.dl.part_model", size=f"{size_note:.1f}")]
        if need_dlls:
            parts.insert(0, tr("wizard.dl.part_cuda"))
        ttk.Label(self._body, wraplength=500, justify="left",
                  text=tr("wizard.dl.will_download", parts=", ".join(parts))).pack(anchor="w")
        self._bar = ttk.Progressbar(self._body, maximum=100)
        self._bar.pack(fill="x", pady=12)
        self._status_var = tk.StringVar(value="")
        ttk.Label(self._body, textvariable=self._status_var).pack(anchor="w")
        self._dl_btn = ttk.Button(self._body, text=tr("wizard.dl.start"),
                                  command=self._start_download)
        self._dl_btn.pack(pady=8)
        ttk.Label(self._body, foreground="#666", wraplength=500, justify="left",
                  text=tr("wizard.dl.skip_note")).pack(anchor="w")
        if self._download_thread is not None and self._download_thread.is_alive():
            # Вернулись на шаг во время загрузки — показываем живой прогресс.
            self._dl_btn.config(state="disabled")
            self._next_btn.config(state="disabled")
            self._back_btn.config(state="disabled")
            self._poll_download()

    def _start_download(self):
        if self._download_thread is not None and self._download_thread.is_alive():
            return
        self._dl_btn.config(state="disabled")
        self._next_btn.config(state="disabled")
        self._back_btn.config(state="disabled")
        self._download_error = None
        self._progress = {"text": tr("wizard.dl.preparing"), "percent": 0.0, "done": False}

        def work():
            try:
                if self._cancel_download:
                    return
                # Пересчитываем на момент запуска, а не отрисовки шага:
                # после «Повторить» уже распакованные DLL не качаются заново.
                need_dlls = self._need_cuda and not any(paths.cuda_dir().glob("*.dll"))
                if need_dlls:
                    paths.cuda_dir().mkdir(parents=True, exist_ok=True)
                    n_pkgs = len(fetch.CUDA_PACKAGES)
                    with tempfile.TemporaryDirectory() as tmp:
                        fetch.fetch_cuda(
                            paths.cuda_dir(), tmp,
                            # Прогресс кумулятивный по пакетам: полоска идёт
                            # 0→40 % один раз, а не дважды.
                            lambda i, pkg, d, t: self._progress.update(
                                text=tr("wizard.dl.progress_cuda", pkg=pkg,
                                        done=d // 1048576, total=max(t, 1) // 1048576),
                                percent=(i + (d / t if t else 0.0)) / n_pkgs * 40),
                            cancelled=lambda: self._cancel_download)
                if self._cancel_download:
                    return
                base = fetch.hf_cache_size()
                total = fetch.MODEL_SIZES[self._cfg["model"]]
                watcher_stop = threading.Event()

                def watch():
                    while not watcher_stop.wait(0.5):
                        grown = fetch.hf_cache_size() - base
                        self._progress.update(
                            text=tr("wizard.dl.progress_model",
                                    done=grown // 1048576, total=total // 1048576),
                            percent=40 + min(60.0, grown / total * 60))

                threading.Thread(target=watch, daemon=True).start()
                try:
                    fetch.fetch_model(self._cfg["model"])
                finally:
                    watcher_stop.set()
                self._progress.update(text=tr("wizard.dl.done"), percent=100.0, done=True)
            except Exception as exc:
                log.exception("Ошибка загрузки в мастере")
                self._download_error = exc
                self._progress["done"] = True

        self._download_thread = threading.Thread(target=work, daemon=True)
        self._download_thread.start()
        self._poll_download()

    def _poll_download(self):
        if not self._bar.winfo_exists():
            return
        p = self._progress
        self._bar["value"] = p["percent"]
        self._status_var.set(p["text"])
        if not p["done"]:
            self._root.after(200, self._poll_download)
            return
        self._next_btn.config(state="normal")
        self._back_btn.config(state="normal")
        if self._download_error is not None:
            self._status_var.set(tr("wizard.dl.failed", exc=self._download_error))
            self._dl_btn.config(text=tr("wizard.dl.retry"), state="normal")

    def _step_mic(self):
        self._title(tr("wizard.mic.title"))
        devices = [tr("settings.default_device")] + dedupe_input_devices(sd.query_devices())
        self._mic_box = ttk.Combobox(self._body, values=devices, state="readonly", width=45)
        cur = self._cfg["input_device"]
        self._mic_box.current(devices.index(cur) if cur in devices else 0)
        self._mic_box.pack(anchor="w", pady=(0, 10))
        self._mic_box.bind("<<ComboboxSelected>>", lambda e: self._open_mic())
        ttk.Label(self._body, text=tr("wizard.mic.speak")).pack(anchor="w")
        self._level_bar = ttk.Progressbar(self._body, maximum=100)
        self._level_bar.pack(fill="x", pady=8)
        self._mic_status_var = tk.StringVar(value="")
        ttk.Label(self._body, textvariable=self._mic_status_var,
                  wraplength=500, justify="left").pack(anchor="w")
        self._open_mic()
        self._poll_mic()

    def _mic_device(self):
        val = self._mic_box.get()
        return None if val == tr("settings.default_device") else val

    def _open_mic(self):
        self._close_mic()
        device = self._mic_device()
        try:
            def cb(indata, frames, t, status):
                self._mic_level = float(np.sqrt((indata ** 2).mean()))
            self._mic_stream = sd.InputStream(
                samplerate=16000, channels=1, dtype="float32",
                device=device, callback=cb)
            self._mic_stream.start()
        except Exception as exc:
            log.exception("Не удалось открыть микрофон в мастере")
            self._mic_stream = None
            self._mic_level = 0.0
            # Нерабочий выбор в конфиг не пишем — иначе пользователь молча
            # унёс бы устройство, с которого запись не идёт.
            self._mic_status_var.set(tr("wizard.mic.failed", exc=exc))
            return
        self._cfg["input_device"] = device
        self._mic_status_var.set("")

    def _close_mic(self):
        if self._mic_stream is not None:
            try:
                self._mic_stream.stop()
                self._mic_stream.close()
            except Exception:
                pass
            self._mic_stream = None

    def _poll_mic(self):
        if not self._level_bar.winfo_exists():
            return
        self._level_bar["value"] = min(100.0, self._mic_level * 700)
        self._root.after(80, self._poll_mic)

    def _step_permissions(self):
        self._title(tr("wizard.perm.title"))
        ttk.Label(self._body, wraplength=500, justify="left",
                  text=tr("wizard.perm.body")).pack(anchor="w", pady=(0, 10))
        self._perm_rows = []
        self._perm_probe = None  # живой виджет шага: умер — опрос прекращаем
        for title, kind in ((tr("wizard.perm.listen"), "listen"),
                            (tr("wizard.perm.post"), "post")):
            row = ttk.Frame(self._body)
            row.pack(anchor="w", fill="x", pady=4)
            status = tk.StringVar()
            ttk.Label(row, textvariable=status, width=3).pack(side="left")
            ttk.Label(row, text=title).pack(side="left")
            ttk.Button(row, text=tr("wizard.perm.grant"),
                       command=lambda k=kind: self._request_permission(k)).pack(
                side="right")
            self._perm_rows.append((kind, status))
            self._perm_probe = row
        ttk.Label(self._body, foreground="#666", wraplength=500, justify="left",
                  text=tr("wizard.perm.restart_note")).pack(anchor="w", pady=(10, 0))
        self._poll_permissions()

    @staticmethod
    def _permission_granted(kind):
        import Quartz
        if kind == "listen":
            return bool(Quartz.CGPreflightListenEventAccess())
        return bool(Quartz.CGPreflightPostEventAccess())

    def _request_permission(self, kind):
        """Системный диалог (работает один раз) + панель System Settings."""
        import subprocess
        import Quartz
        try:
            if kind == "listen":
                Quartz.CGRequestListenEventAccess()
                pane = "Privacy_ListenEvent"
            else:
                Quartz.CGRequestPostEventAccess()
                pane = "Privacy_Accessibility"
            subprocess.Popen(
                ["open", "x-apple.systempreferences:"
                 f"com.apple.preference.security?{pane}"])
        except Exception:
            log.exception("Не удалось запросить разрешение %s", kind)

    def _poll_permissions(self):
        if self._perm_probe is None or not self._perm_probe.winfo_exists():
            return  # ушли с шага — виджеты разрушены _clear()
        try:
            for kind, status in self._perm_rows:
                status.set("✓" if self._permission_granted(kind) else "✗")
        except Exception:
            # Разовый сбой Quartz не должен замораживать индикаторы: тогда
            # выданное разрешение так и не отобразилось бы галочкой.
            if not self._perm_warned:
                self._perm_warned = True
                log.exception("Не удалось проверить разрешения TCC")
        self._root.after(1000, self._poll_permissions)

    def _step_hotkey(self):
        self._title(tr("wizard.hk.title"))
        self._hotkey_var = tk.StringVar(value=hk.human_label(self._cfg["hotkey"]))
        ttk.Label(self._body, textvariable=self._hotkey_var,
                  font=("Segoe UI", 11)).pack(anchor="w", pady=(0, 8))
        self._hk_btn = ttk.Button(self._body, text=tr("settings.change"), command=self._capture)
        self._hk_btn.pack(anchor="w")
        ttk.Label(self._body, foreground="#666", wraplength=500, justify="left",
                  text=tr("wizard.hk.hint")).pack(anchor="w", pady=(10, 0))

    def _ensure_listener(self):
        if self._listener is None:
            listener = hk.HotkeyListener(
                on_press=lambda: None, on_release=lambda: None,
                combo=hk.names_to_vks(self._cfg["hotkey"]))

            def run():
                try:
                    listener.run()
                except Exception:
                    listener.dead = True  # _poll_capture вернёт кнопки, а не зависнет
                    log.exception("Хук клавиатуры в мастере не запустился")

            self._listener = listener
            self._listener_thread = threading.Thread(target=run, daemon=True)
            self._listener_thread.start()

    def _capture(self):
        self._ensure_listener()
        self._hk_btn.config(state="disabled")
        self._next_btn.config(state="disabled")
        self._back_btn.config(state="disabled")
        self._hotkey_var.set(tr("settings.press_combo"))
        self._capture_state = "wait"
        self._listener.start_capture(
            lambda names: setattr(self, "_capture_state", names or "cancel"))
        self._poll_capture()

    def _poll_capture(self):
        if not self._hk_btn.winfo_exists():
            return
        state = self._capture_state
        if state == "wait":
            if self._listener is not None and self._listener.dead:
                # Хук не запустился (нет «Мониторинга ввода») — колбэк не
                # придёт никогда; без этого мастер зависал бы с выключенными
                # кнопками навсегда.
                self._listener.cancel_capture()
                self._capture_state = "idle"
                self._hotkey_var.set(tr("wizard.hk.unavailable"))
                self._hk_btn.config(state="normal")
                self._next_btn.config(state="normal")
                self._back_btn.config(state="normal")
                return
            self._root.after(100, self._poll_capture)
            return
        if isinstance(state, list):
            self._cfg["hotkey"] = state
        self._capture_state = "idle"
        self._hotkey_var.set(hk.human_label(self._cfg["hotkey"]))
        self._hk_btn.config(state="normal")
        self._next_btn.config(state="normal")
        self._back_btn.config(state="normal")

    def _step_done(self):
        self._title(tr("wizard.done.title"))
        if sys.platform == "darwin":
            where, how = tr("wizard.done.where_mac"), tr("wizard.done.how_mac")
        else:
            where, how = tr("wizard.done.where_win"), tr("wizard.done.how_win")
        ttk.Label(self._body, wraplength=500, justify="left",
                  text=tr("wizard.done.body", where=where,
                          hotkey=hk.human_label(self._cfg["hotkey"]), how=how)).pack(anchor="w")
