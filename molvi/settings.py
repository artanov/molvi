import logging
import tkinter as tk
from tkinter import ttk

import sounddevice as sd

from molvi import autostart
from molvi import hotkey as hk

log = logging.getLogger(__name__)

QUALITY_PRESETS = [
    ("Максимальное — large-v3 (нужна NVIDIA, ~3 ГБ)", "large-v3"),
    ("Среднее — small (~500 МБ)", "small"),
    ("Быстрое — base (~150 МБ)", "base"),
]
LANGUAGES = [("Авто", "auto"), ("Русский", "ru"), ("English", "en")]
_DEFAULT_DEVICE_LABEL = "Системный по умолчанию"


def quality_index_for_model(model):
    for i, (_label, m) in enumerate(QUALITY_PRESETS):
        if m == model:
            return i
    return 0


def language_index(code):
    for i, (_label, c) in enumerate(LANGUAGES):
        if c == code:
            return i
    return 0


def dedupe_input_devices(devices):
    seen, out = set(), []
    for d in devices:
        if d.get("max_input_channels", 0) <= 0:
            continue
        name = d["name"]
        if name not in seen:
            seen.add(name)
            out.append(name)
    return out


def device_choices(device_names, current):
    """→ (values_list, initial_index, mapping) для комбобокса микрофона."""
    values = [_DEFAULT_DEVICE_LABEL] + list(device_names)
    mapping = {_DEFAULT_DEVICE_LABEL: None}
    for name in device_names:
        mapping[name] = name
    if current is not None and current not in device_names:
        label = f"Текущее: {current}"
        values.insert(1, label)
        mapping[label] = current
        return values, 1, mapping
    idx = values.index(current) if current in values else 0
    return values, idx, mapping


class SettingsWindow:
    """Окно настроек. Создавать и использовать только в tk-потоке."""

    def __init__(self, root, cfg, listener, on_save):
        self._cfg = dict(cfg)
        self._listener = listener
        self._on_save = on_save
        self._hotkey_names = list(cfg["hotkey"])
        self._capture_result = "idle"

        win = self._win = tk.Toplevel(root)
        win.title("Molvi — настройки")
        win.resizable(False, False)
        win.attributes("-topmost", True)
        frm = ttk.Frame(win, padding=16)
        frm.grid()
        frm.columnconfigure(1, minsize=280)

        ttk.Label(frm, text="Клавиша диктовки:").grid(row=0, column=0, sticky="w", pady=4)
        self._hotkey_var = tk.StringVar(value=hk.human_label(self._hotkey_names))
        ttk.Label(frm, textvariable=self._hotkey_var).grid(row=0, column=1, sticky="w")
        self._hotkey_btn = ttk.Button(frm, text="Изменить", command=self._change_hotkey)
        self._hotkey_btn.grid(row=0, column=2, padx=(8, 0))

        ttk.Label(frm, text="Микрофон:").grid(row=1, column=0, sticky="w", pady=4)
        device_names = dedupe_input_devices(sd.query_devices())
        values, idx, self._device_mapping = device_choices(device_names, cfg["input_device"])
        self._mic = ttk.Combobox(frm, values=values, state="readonly", width=40)
        self._mic.current(idx)
        self._mic.grid(row=1, column=1, columnspan=2, sticky="we")

        ttk.Label(frm, text="Язык:").grid(row=2, column=0, sticky="w", pady=4)
        self._lang = ttk.Combobox(
            frm, values=[label for label, _ in LANGUAGES], state="readonly"
        )
        self._lang.current(language_index(cfg["language"]))
        self._lang.grid(row=2, column=1, columnspan=2, sticky="we")

        ttk.Label(frm, text="Качество:").grid(row=3, column=0, sticky="w", pady=4)
        self._quality = ttk.Combobox(
            frm, values=[label for label, _ in QUALITY_PRESETS], state="readonly"
        )
        self._quality.current(quality_index_for_model(cfg["model"]))
        self._quality.grid(row=3, column=1, columnspan=2, sticky="we")

        self._sounds_var = tk.BooleanVar(value=bool(cfg["sounds"]))
        ttk.Checkbutton(frm, text="Звуки записи", variable=self._sounds_var).grid(
            row=4, column=0, columnspan=3, sticky="w", pady=4
        )

        try:
            autostart_now = autostart.is_enabled()
        except OSError:
            autostart_now = False
        self._autostart_var = tk.BooleanVar(value=autostart_now)
        ttk.Checkbutton(
            frm, text="Запускать вместе с Windows", variable=self._autostart_var
        ).grid(row=5, column=0, columnspan=3, sticky="w", pady=4)

        btns = ttk.Frame(frm)
        btns.grid(row=6, column=0, columnspan=3, pady=(12, 0))
        self._save_btn = ttk.Button(btns, text="Сохранить", command=self._save)
        self._save_btn.grid(row=0, column=0, padx=4)
        self._cancel_btn = ttk.Button(btns, text="Отмена", command=self._close)
        self._cancel_btn.grid(row=0, column=1, padx=4)
        self._win.protocol("WM_DELETE_WINDOW", self._close)

    def _close(self):
        if self._capture_result == "wait":
            return  # идёт захват — сначала завершите комбинацию или нажмите Esc
        self._win.destroy()

    # --- hotkey capture ---
    def _change_hotkey(self):
        self._hotkey_btn.config(state="disabled")
        self._save_btn.config(state="disabled")
        self._cancel_btn.config(state="disabled")
        self._hotkey_var.set("Нажмите комбинацию… (Esc — отмена)")
        self._capture_result = "wait"
        # колбэк придёт из потока хука — только записываем результат
        self._listener.start_capture(self._on_captured)
        self._win.after(100, self._poll_capture)

    def _on_captured(self, names):
        self._capture_result = names if names else "cancel"

    def _poll_capture(self):
        if not self.alive():
            return
        result = self._capture_result
        if result == "wait":
            self._win.after(100, self._poll_capture)
            return
        if isinstance(result, list):
            self._hotkey_names = result
        self._capture_result = "idle"
        self._hotkey_var.set(hk.human_label(self._hotkey_names))
        self._hotkey_btn.config(state="normal")
        self._save_btn.config(state="normal")
        self._cancel_btn.config(state="normal")

    # --- save ---
    def _save(self):
        if self._capture_result == "wait":
            return
        cfg = dict(self._cfg)
        cfg["hotkey"] = list(self._hotkey_names)
        cfg["input_device"] = self._device_mapping[self._mic.get()]
        cfg["language"] = LANGUAGES[self._lang.current()][1]
        cfg["model"] = QUALITY_PRESETS[self._quality.current()][1]
        cfg["sounds"] = bool(self._sounds_var.get())
        self._on_save(cfg, bool(self._autostart_var.get()))
        self._win.destroy()

    def alive(self):
        try:
            return bool(self._win.winfo_exists())
        except tk.TclError:
            return False

    def lift_window(self):
        self._win.deiconify()
        self._win.lift()
