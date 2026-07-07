"""Мастер первого запуска: железо → докачка → микрофон → клавиша.

Любая ошибка шага не роняет мастер: шаг можно пропустить, действуют дефолты.
Окно закрыто крестиком — возвращаются накопленные к этому моменту значения.
"""
import logging
import tempfile
import threading
import tkinter as tk
from tkinter import messagebox, ttk

import numpy as np
import sounddevice as sd

from voiceflow import fetch, gpu, paths
from voiceflow import hotkey as hk
from voiceflow.config import DEFAULTS
from voiceflow.settings import QUALITY_PRESETS, dedupe_input_devices, quality_index_for_model

log = logging.getLogger(__name__)


class Wizard:
    def __init__(self):
        self._cfg = dict(DEFAULTS)
        self._gpu = gpu.detect_nvidia()
        model, device = gpu.recommend(self._gpu)
        self._cfg["model"], self._cfg["device"] = model, device
        self._need_cuda = device == "auto"

        self._root = tk.Tk()
        self._root.title("VoiceFlow — первый запуск")
        self._root.resizable(False, False)
        self._root.attributes("-topmost", True)
        self._body = ttk.Frame(self._root, padding=20, width=560, height=330)
        self._body.pack(fill="both", expand=True)
        self._body.pack_propagate(False)
        nav = ttk.Frame(self._root, padding=(20, 0, 20, 16))
        nav.pack(fill="x")
        self._back_btn = ttk.Button(nav, text="Назад", command=self._go_back)
        self._back_btn.pack(side="left")
        self._next_btn = ttk.Button(nav, text="Далее", command=self._go_next)
        self._next_btn.pack(side="right")

        self._steps = [self._step_welcome, self._step_hardware,
                       self._step_download, self._step_mic,
                       self._step_hotkey, self._step_done]
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
        self._back_btn.config(state="normal" if self._idx > 0 else "disabled")
        self._next_btn.config(text="Готово" if self._idx == len(self._steps) - 1 else "Далее",
                              state="normal")
        try:
            self._steps[self._idx]()
        except Exception:
            log.exception("Шаг мастера %d упал — пропускаю", self._idx)
            ttk.Label(self._body, text="Этот шаг не удался — нажмите «Далее», "
                      "настройку можно закончить позже в Настройках.").pack()

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
            if not messagebox.askyesno("VoiceFlow", "Идёт загрузка. Прервать и выйти?"):
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
    def _step_welcome(self):
        self._title("Добро пожаловать в VoiceFlow")
        ttk.Label(self._body, wraplength=500, justify="left", text=(
            "VoiceFlow печатает вашим голосом: зажмите клавишу, говорите, "
            "отпустите — текст появится там, где стоит курсор. Распознавание "
            "работает полностью на вашем компьютере, без интернета и подписок.\n\n"
            "Сейчас мы за пару минут всё настроим.")).pack(anchor="w")

    def _step_hardware(self):
        self._title("Оборудование")
        if self._gpu:
            found = (f"Найдена видеокарта {self._gpu['name']} "
                     f"({self._gpu['vram_mb'] // 1024} ГБ) — рекомендуем "
                     "максимальное качество.")
        else:
            found = ("Видеокарта NVIDIA не найдена — распознавание будет на "
                     "процессоре, рекомендуем быструю модель.")
        ttk.Label(self._body, text=found, wraplength=500, justify="left").pack(
            anchor="w", pady=(0, 10))
        self._quality_var = tk.IntVar(value=quality_index_for_model(self._cfg["model"]))
        for i, (label, _model) in enumerate(QUALITY_PRESETS):
            ttk.Radiobutton(self._body, text=label, variable=self._quality_var,
                            value=i, command=self._on_quality).pack(anchor="w", pady=2)

    def _on_quality(self):
        model = QUALITY_PRESETS[self._quality_var.get()][1]
        self._cfg["model"] = model
        if model == "large-v3":
            self._cfg["device"] = "auto"
        elif self._gpu is None:
            self._cfg["device"] = "cpu"
        self._need_cuda = self._cfg["device"] == "auto"

    def _step_download(self):
        self._title("Загрузка компонентов")
        need_dlls = self._need_cuda and not any(paths.cuda_dir().glob("*.dll"))
        size_note = fetch.MODEL_SIZES[self._cfg["model"]] / 1e9
        parts = [f"модель ({size_note:.1f} ГБ)"]
        if need_dlls:
            parts.insert(0, "библиотеки NVIDIA (~0.6 ГБ)")
        ttk.Label(self._body, wraplength=500, justify="left",
                  text="Будут загружены: " + ", ".join(parts) + ".").pack(anchor="w")
        self._bar = ttk.Progressbar(self._body, maximum=100)
        self._bar.pack(fill="x", pady=12)
        self._status_var = tk.StringVar(value="")
        ttk.Label(self._body, textvariable=self._status_var).pack(anchor="w")
        self._dl_btn = ttk.Button(self._body, text="Начать загрузку",
                                  command=lambda: self._start_download(need_dlls))
        self._dl_btn.pack(pady=8)
        ttk.Label(self._body, foreground="#666", wraplength=500, justify="left", text=(
            "Можно нажать «Далее» и пропустить — тогда всё скачается при первом "
            "распознавании (придётся подождать).")).pack(anchor="w")
        if self._download_thread is not None and self._download_thread.is_alive():
            # Вернулись на шаг во время загрузки — показываем живой прогресс.
            self._dl_btn.config(state="disabled")
            self._next_btn.config(state="disabled")
            self._back_btn.config(state="disabled")
            self._poll_download()

    def _start_download(self, need_dlls):
        if self._download_thread is not None and self._download_thread.is_alive():
            return
        self._dl_btn.config(state="disabled")
        self._next_btn.config(state="disabled")
        self._back_btn.config(state="disabled")
        self._download_error = None
        self._progress = {"text": "Готовлюсь…", "percent": 0.0, "done": False}

        def work():
            try:
                if self._cancel_download:
                    return
                if need_dlls:
                    paths.cuda_dir().mkdir(parents=True, exist_ok=True)
                    with tempfile.TemporaryDirectory() as tmp:
                        fetch.fetch_cuda(
                            paths.cuda_dir(), tmp,
                            lambda pkg, d, t: self._progress.update(
                                text=f"NVIDIA: {pkg} {d // 1048576} / {max(t, 1) // 1048576} МБ",
                                percent=(d / t * 40) if t else 0.0))
                if self._cancel_download:
                    return
                base = fetch.hf_cache_size()
                total = fetch.MODEL_SIZES[self._cfg["model"]]
                watcher_stop = threading.Event()

                def watch():
                    while not watcher_stop.wait(0.5):
                        grown = fetch.hf_cache_size() - base
                        self._progress.update(
                            text=f"Модель: {grown // 1048576} / ~{total // 1048576} МБ",
                            percent=40 + min(60.0, grown / total * 60))

                threading.Thread(target=watch, daemon=True).start()
                try:
                    fetch.fetch_model(self._cfg["model"])
                finally:
                    watcher_stop.set()
                self._progress.update(text="Готово!", percent=100.0, done=True)
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
            self._status_var.set(f"Не получилось: {self._download_error}")
            self._dl_btn.config(text="Повторить", state="normal")

    def _step_mic(self):
        self._title("Микрофон")
        devices = ["Системный по умолчанию"] + dedupe_input_devices(sd.query_devices())
        self._mic_box = ttk.Combobox(self._body, values=devices, state="readonly", width=45)
        cur = self._cfg["input_device"]
        self._mic_box.current(devices.index(cur) if cur in devices else 0)
        self._mic_box.pack(anchor="w", pady=(0, 10))
        self._mic_box.bind("<<ComboboxSelected>>", lambda e: self._open_mic())
        ttk.Label(self._body, text="Скажите что-нибудь — полоска должна дёргаться:").pack(anchor="w")
        self._level_bar = ttk.Progressbar(self._body, maximum=100)
        self._level_bar.pack(fill="x", pady=8)
        self._open_mic()
        self._poll_mic()

    def _mic_device(self):
        val = self._mic_box.get()
        return None if val == "Системный по умолчанию" else val

    def _open_mic(self):
        self._close_mic()
        self._cfg["input_device"] = self._mic_device()
        try:
            def cb(indata, frames, t, status):
                self._mic_level = float(np.sqrt((indata ** 2).mean()))
            self._mic_stream = sd.InputStream(
                samplerate=16000, channels=1, dtype="float32",
                device=self._cfg["input_device"], callback=cb)
            self._mic_stream.start()
        except Exception:
            log.exception("Не удалось открыть микрофон в мастере")
            self._mic_stream = None

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

    def _step_hotkey(self):
        self._title("Клавиша диктовки")
        self._hotkey_var = tk.StringVar(value=hk.human_label(self._cfg["hotkey"]))
        ttk.Label(self._body, textvariable=self._hotkey_var,
                  font=("Segoe UI", 11)).pack(anchor="w", pady=(0, 8))
        self._hk_btn = ttk.Button(self._body, text="Изменить", command=self._capture)
        self._hk_btn.pack(anchor="w")
        ttk.Label(self._body, foreground="#666", wraplength=500, justify="left", text=(
            "Зажмите эту клавишу (или комбинацию) — идёт запись; отпустите — "
            "текст напечатается. Изменить можно в любой момент в Настройках.")).pack(
            anchor="w", pady=(10, 0))

    def _ensure_listener(self):
        if self._listener is None:
            self._listener = hk.HotkeyListener(
                on_press=lambda: None, on_release=lambda: None,
                combo=hk.names_to_vks(self._cfg["hotkey"]))
            self._listener_thread = threading.Thread(
                target=self._listener.run, daemon=True)
            self._listener_thread.start()

    def _capture(self):
        self._ensure_listener()
        self._hk_btn.config(state="disabled")
        self._next_btn.config(state="disabled")
        self._back_btn.config(state="disabled")
        self._hotkey_var.set("Нажмите комбинацию… (Esc — отмена)")
        self._capture_state = "wait"
        self._listener.start_capture(
            lambda names: setattr(self, "_capture_state", names or "cancel"))
        self._poll_capture()

    def _poll_capture(self):
        if not self._hk_btn.winfo_exists():
            return
        state = self._capture_state
        if state == "wait":
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
        self._title("Всё готово")
        ttk.Label(self._body, wraplength=500, justify="left", text=(
            "После нажатия «Готово» загрузится модель распознавания — дождитесь "
            "уведомления «Готов» в трее (значок у часов).\n\n"
            f"Затем зажмите {hk.human_label(self._cfg['hotkey'])} и говорите — "
            "текст появится там, где стоит курсор.\n\n"
            "Настройки в любой момент: правый клик по значку в трее → «Настройки…».")).pack(anchor="w")
