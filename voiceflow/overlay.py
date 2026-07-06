import ctypes
import queue
import tkinter as tk

GWL_EXSTYLE = -20
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080

_STATES = {
    "recording": ("●  Запись…", "#c0392b"),
    "transcribing": ("⏳  Распознаю…", "#2c3e50"),
}


class Overlay:
    """Мини-окно поверх всех окон. Не забирает фокус (WS_EX_NOACTIVATE) —
    иначе вставка ушла бы в оверлей, а не в активное приложение."""

    def __init__(self):
        self._queue = queue.Queue()
        self._root = tk.Tk()
        self._root.withdraw()
        self._root.overrideredirect(True)
        self._root.attributes("-topmost", True)
        self._root.attributes("-alpha", 0.92)
        self._label = tk.Label(
            self._root, text="", font=("Segoe UI", 12, "bold"),
            fg="white", bg="#c0392b", padx=18, pady=8,
        )
        self._label.pack()
        w, h = 190, 44
        sw = self._root.winfo_screenwidth()
        sh = self._root.winfo_screenheight()
        self._root.geometry(f"{w}x{h}+{(sw - w) // 2}+{sh - 140}")
        self._no_activate_applied = False
        self._root.after(50, self._poll)

    def _apply_no_activate(self):
        hwnd = ctypes.windll.user32.GetParent(self._root.winfo_id()) or self._root.winfo_id()
        style = ctypes.windll.user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
        ctypes.windll.user32.SetWindowLongPtrW(
            hwnd, GWL_EXSTYLE, style | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW
        )
        self._no_activate_applied = True

    def _poll(self):
        try:
            while True:
                state = self._queue.get_nowait()
                if state == "quit":
                    self._root.destroy()
                    return
                if state == "hide":
                    self._root.withdraw()
                else:
                    text, bg = _STATES[state]
                    self._label.config(text=text, bg=bg)
                    self._root.deiconify()
                    if not self._no_activate_applied:
                        self._apply_no_activate()
        except queue.Empty:
            pass
        self._root.after(50, self._poll)

    # --- потокобезопасный интерфейс для Controller ---
    def show_recording(self):
        self._queue.put("recording")

    def show_transcribing(self):
        self._queue.put("transcribing")

    def hide(self):
        self._queue.put("hide")

    def schedule_quit(self):
        self._queue.put("quit")

    def run(self):
        self._root.mainloop()
