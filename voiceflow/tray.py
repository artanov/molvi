import threading

import pystray
from PIL import Image, ImageDraw


def _make_icon_image(color="#27ae60"):
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((8, 8, 56, 56), fill=color)
    d.ellipse((26, 18, 38, 40), fill="white")   # стилизованный микрофон
    d.rectangle((30, 40, 34, 50), fill="white")
    return img


class Tray:
    def __init__(self, on_toggle_pause, on_exit):
        self._on_toggle_pause = on_toggle_pause
        self._on_exit = on_exit
        self._paused = False
        self._icon = pystray.Icon(
            "VoiceFlow", _make_icon_image(), "VoiceFlow",
            menu=pystray.Menu(
                pystray.MenuItem(
                    lambda item: "Возобновить" if self._paused else "Пауза",
                    self._toggle,
                ),
                pystray.MenuItem("Выход", self._exit),
            ),
        )

    def _toggle(self, icon, item):
        self._paused = self._on_toggle_pause()
        color = "#e67e22" if self._paused else "#27ae60"
        self._icon.icon = _make_icon_image(color)

    def _exit(self, icon, item):
        threading.Thread(target=self._on_exit, daemon=True).start()

    def start(self):
        self._icon.run_detached()

    def notify(self, msg):
        try:
            self._icon.notify(msg, "VoiceFlow")
        except Exception:
            pass  # уведомление — best effort, не роняем обработку

    def stop(self):
        self._icon.stop()
