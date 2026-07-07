import ctypes
import ctypes.wintypes as wintypes
import logging
import queue
import tkinter as tk
from pathlib import Path

log = logging.getLogger(__name__)

GWL_EXSTYLE = -20
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080

KEY_COLOR = "#ff00fe"
ASSETS = Path(__file__).parent / "assets"
_IMAGE_FILES = {"recording": "recording.png", "transcribing": "transcribing.png"}
_BASE_SIZE = (400, 128)   # размер PNG; соответствует 192 DPI (200%)

_TEXT_STATES = {
    "recording": ("●  Запись…", "#c0392b"),
    "transcribing": ("⏳  Распознаю…", "#2c3e50"),
}


class Overlay:
    """Мини-окно поверх всех окон. Не забирает фокус (WS_EX_NOACTIVATE) —
    иначе вставка ушла бы в оверлей, а не в активное приложение."""

    def __init__(self):
        self._queue = queue.Queue()
        self._on_open_settings = None
        self._root = tk.Tk()
        self._root.withdraw()
        self._root.overrideredirect(True)
        self._root.attributes("-topmost", True)
        # Стиль WS_EX_NOACTIVATE должен стоять ДО первого показа окна,
        # иначе первый deiconify() украдёт фокус у активного приложения.
        self._root.update_idletasks()
        self._apply_no_activate()
        self._images = self._load_images()
        if self._images:
            self._root.configure(bg=KEY_COLOR)
            self._root.attributes("-transparentcolor", KEY_COLOR)
            self._label = tk.Label(self._root, bg=KEY_COLOR, bd=0)
            w, h = self._images["recording"].width(), self._images["recording"].height()
        else:
            self._root.attributes("-alpha", 0.92)
            self._label = tk.Label(
                self._root, text="", font=("Segoe UI", 12, "bold"),
                fg="white", bg="#c0392b", padx=18, pady=8,
            )
            w, h = 190, 44
        self._label.pack()
        sw = self._root.winfo_screenwidth()
        sh = self._root.winfo_screenheight()
        self._root.geometry(f"{w}x{h}+{(sw - w) // 2}+{sh - 140 - h + 44}")
        self._root.after(50, self._poll)

    @property
    def root(self):
        return self._root

    def _hwnd(self):
        user32 = ctypes.windll.user32
        user32.GetParent.argtypes = [wintypes.HWND]
        user32.GetParent.restype = wintypes.HWND
        return user32.GetParent(self._root.winfo_id()) or self._root.winfo_id()

    def _apply_no_activate(self):
        user32 = ctypes.windll.user32
        user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
        user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
        user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
        hwnd = self._hwnd()
        style = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
        user32.SetWindowLongPtrW(
            hwnd, GWL_EXSTYLE, style | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW
        )

    def _dpi(self):
        try:
            user32 = ctypes.windll.user32
            user32.GetDpiForWindow.argtypes = [wintypes.HWND]
            user32.GetDpiForWindow.restype = wintypes.UINT
            return user32.GetDpiForWindow(self._hwnd()) or 96
        except Exception:
            return 96

    def _load_images(self):
        """PNG → PhotoImage, скомпонованные на ключевой цвет; None при любой проблеме."""
        try:
            from PIL import Image, ImageTk
            scale = self._dpi() / 192
            size = (max(1, int(_BASE_SIZE[0] * scale)), max(1, int(_BASE_SIZE[1] * scale)))
            images = {}
            for state, fname in _IMAGE_FILES.items():
                path = ASSETS / fname
                if not path.is_file():
                    log.warning("Нет %s — оверлей в текстовом режиме", fname)
                    return None
                img = Image.open(path).convert("RGBA").resize(size, Image.LANCZOS)
                # Ключевой цвет прозрачен только при ТОЧНОМ совпадении, поэтому
                # полупрозрачные пиксели сглаживания дали бы розовую кайму.
                # Примешиваем края к тёмному матту и делаем альфу бинарной.
                matte = Image.new("RGBA", size, "#232029")
                matte.alpha_composite(img)
                hard_alpha = img.getchannel("A").point(lambda a: 255 if a >= 128 else 0)
                bg = Image.new("RGB", size, KEY_COLOR)
                bg.paste(matte.convert("RGB"), mask=hard_alpha)
                images[state] = ImageTk.PhotoImage(bg, master=self._root)
            return images
        except Exception:
            log.warning("Не удалось загрузить картинки оверлея", exc_info=True)
            return None

    def _poll(self):
        try:
            while True:
                state = self._queue.get_nowait()
                if state == "quit":
                    self._root.destroy()
                    return
                if state == "settings":
                    if self._on_open_settings is not None:
                        self._on_open_settings()
                elif state == "hide":
                    self._root.withdraw()
                elif self._images:
                    self._label.config(image=self._images[state])
                    self._root.deiconify()
                else:
                    text, bg = _TEXT_STATES[state]
                    self._label.config(text=text, bg=bg)
                    self._root.deiconify()
        except queue.Empty:
            pass
        self._root.after(50, self._poll)

    # --- потокобезопасный интерфейс (Controller, Tray) ---
    def show_recording(self):
        self._queue.put("recording")

    def show_transcribing(self):
        self._queue.put("transcribing")

    def hide(self):
        self._queue.put("hide")

    def open_settings(self):
        self._queue.put("settings")

    def set_settings_opener(self, fn):
        self._on_open_settings = fn

    def schedule_quit(self):
        self._queue.put("quit")

    def run(self):
        self._root.mainloop()
