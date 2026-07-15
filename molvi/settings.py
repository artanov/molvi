import logging
import sys
import tkinter as tk
from tkinter import ttk

import sounddevice as sd

from molvi.i18n import tr
from molvi.platform import autostart
from molvi.platform import hotkey as hk

log = logging.getLogger(__name__)


# Пресеты/языки — функции, а не модульные константы: перевод берётся в момент
# вызова, иначе окно застыло бы на языке, который был активен при импорте.
def quality_presets():
    if sys.platform == "darwin":
        return [
            (tr("settings.quality.max_mac"), "large-v3-turbo"),
            (tr("settings.quality.small"), "small"),
            (tr("settings.quality.base"), "base"),
        ]
    return [
        (tr("settings.quality.max_win"), "large-v3"),
        (tr("settings.quality.small"), "small"),
        (tr("settings.quality.base"), "base"),
    ]


def language_choices():
    return [(tr("settings.lang.auto"), "auto"),
            (tr("settings.lang.ru"), "ru"),
            (tr("settings.lang.en"), "en")]


def ui_language_choices():
    # Названия языков — на самом языке: «Русский» ищет русскоязычный.
    return [(tr("settings.ui_lang.auto"), "auto"), ("Русский", "ru"), ("English", "en")]


def quality_index_for_model(model):
    for i, (_label, m) in enumerate(quality_presets()):
        if m == model:
            return i
    return 0


def language_index(code):
    for i, (_label, c) in enumerate(language_choices()):
        if c == code:
            return i
    return 0


def ui_language_index(code):
    for i, (_label, c) in enumerate(ui_language_choices()):
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
    default_label = tr("settings.default_device")
    values = [default_label] + list(device_names)
    mapping = {default_label: None}
    for name in device_names:
        mapping[name] = name
    if current is not None and current not in device_names:
        label = tr("settings.current_device", name=current)
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
        win.title(tr("settings.title"))
        win.resizable(False, False)
        win.attributes("-topmost", True)
        frm = ttk.Frame(win, padding=16)
        frm.grid()
        frm.columnconfigure(1, minsize=280)

        ttk.Label(frm, text=tr("settings.hotkey")).grid(row=0, column=0, sticky="w", pady=4)
        self._hotkey_var = tk.StringVar(value=hk.human_label(self._hotkey_names))
        ttk.Label(frm, textvariable=self._hotkey_var).grid(row=0, column=1, sticky="w")
        self._hotkey_btn = ttk.Button(frm, text=tr("settings.change"), command=self._change_hotkey)
        self._hotkey_btn.grid(row=0, column=2, padx=(8, 0))

        ttk.Label(frm, text=tr("settings.microphone")).grid(row=1, column=0, sticky="w", pady=4)
        device_names = dedupe_input_devices(sd.query_devices())
        values, idx, self._device_mapping = device_choices(device_names, cfg["input_device"])
        self._mic = ttk.Combobox(frm, values=values, state="readonly", width=40)
        self._mic.current(idx)
        self._mic.grid(row=1, column=1, columnspan=2, sticky="we")

        ttk.Label(frm, text=tr("settings.language")).grid(row=2, column=0, sticky="w", pady=4)
        self._languages = language_choices()
        self._lang = ttk.Combobox(
            frm, values=[label for label, _ in self._languages], state="readonly"
        )
        self._lang.current(language_index(cfg["language"]))
        self._lang.grid(row=2, column=1, columnspan=2, sticky="we")

        ttk.Label(frm, text=tr("settings.ui_language")).grid(row=3, column=0, sticky="w", pady=4)
        self._ui_langs = ui_language_choices()
        self._ui_lang = ttk.Combobox(
            frm, values=[label for label, _ in self._ui_langs], state="readonly"
        )
        self._ui_lang.current(ui_language_index(cfg.get("ui_language", "auto")))
        self._ui_lang.grid(row=3, column=1, columnspan=2, sticky="we")

        ttk.Label(frm, text=tr("settings.quality")).grid(row=4, column=0, sticky="w", pady=4)
        self._presets = quality_presets()
        self._quality = ttk.Combobox(
            frm, values=[label for label, _ in self._presets], state="readonly"
        )
        self._quality.current(quality_index_for_model(cfg["model"]))
        self._quality.grid(row=4, column=1, columnspan=2, sticky="we")

        self._sounds_var = tk.BooleanVar(value=bool(cfg["sounds"]))
        ttk.Checkbutton(frm, text=tr("settings.sounds"), variable=self._sounds_var).grid(
            row=5, column=0, columnspan=3, sticky="w", pady=4
        )

        try:
            autostart_now = autostart.is_enabled()
        except OSError:
            autostart_now = False
        self._autostart_var = tk.BooleanVar(value=autostart_now)
        ttk.Checkbutton(
            frm, text=tr(autostart.LABEL_KEY), variable=self._autostart_var
        ).grid(row=6, column=0, columnspan=3, sticky="w", pady=4)

        btns = ttk.Frame(frm)
        btns.grid(row=7, column=0, columnspan=3, pady=(12, 0))
        self._save_btn = ttk.Button(btns, text=tr("settings.save"), command=self._save)
        self._save_btn.grid(row=0, column=0, padx=4)
        self._cancel_btn = ttk.Button(btns, text=tr("settings.cancel"), command=self._close)
        self._cancel_btn.grid(row=0, column=1, padx=4)
        self._win.protocol("WM_DELETE_WINDOW", self._close)

    def _close(self):
        if self._capture_result == "wait":
            # Идёт захват — отменяем его, а не блокируем закрытие: если поток
            # хука мёртв, Esc никогда не придёт и окно осталось бы навсегда.
            self._listener.cancel_capture()
            self._capture_result = "idle"
        self._win.destroy()

    # --- hotkey capture ---
    def _change_hotkey(self):
        self._hotkey_btn.config(state="disabled")
        self._save_btn.config(state="disabled")
        self._cancel_btn.config(state="disabled")
        self._hotkey_var.set(tr("settings.press_combo"))
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
            if self._listener.dead:
                # Хук мёртв (например, на маке без «Мониторинга ввода») —
                # колбэк не придёт; отменяем захват, иначе «Сохранить» и
                # «Отмена» остались бы выключенными навсегда.
                self._listener.cancel_capture()
                result = self._capture_result = "cancel"
            else:
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
        cfg["language"] = self._languages[self._lang.current()][1]
        cfg["ui_language"] = self._ui_langs[self._ui_lang.current()][1]
        cfg["model"] = self._presets[self._quality.current()][1]
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
