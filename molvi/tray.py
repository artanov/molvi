import threading

import pystray
from PIL import Image, ImageDraw

from molvi import theme
from molvi.i18n import tr


def _make_icon_image(color=theme.CORAL):
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((8, 8, 56, 56), fill=color)
    d.ellipse((26, 18, 38, 40), fill=theme.CREAM)   # стилизованный микрофон
    d.rectangle((30, 40, 34, 50), fill=theme.CREAM)
    return img


class Tray:
    def __init__(self, on_toggle_pause, on_exit, on_settings=None):
        self._on_toggle_pause = on_toggle_pause
        self._on_exit = on_exit
        self._on_settings = on_settings or (lambda: None)
        self._paused = False
        self._icon = pystray.Icon(
            "Molvi", _make_icon_image(), "Molvi",
            menu=pystray.Menu(
                pystray.MenuItem(lambda item: tr("tray.settings"), self._settings),
                pystray.MenuItem(
                    lambda item: tr("tray.resume") if self._paused else tr("tray.pause"),
                    self._toggle,
                ),
                pystray.MenuItem(lambda item: tr("tray.quit"), self._exit),
            ),
        )

    def _settings(self, icon, item):
        self._on_settings()

    def _toggle(self, icon, item):
        self._paused = self._on_toggle_pause()
        color = theme.WARN if self._paused else theme.CORAL
        self._icon.icon = _make_icon_image(color)

    def _exit(self, icon, item):
        threading.Thread(target=self._on_exit, daemon=True).start()

    def start(self):
        self._icon.run_detached()

    def refresh(self):
        """Перечитать подписи меню (после смены языка интерфейса)."""
        try:
            self._icon.update_menu()
        except Exception:
            pass  # как и notify — best effort

    def notify(self, msg):
        try:
            self._icon.notify(msg, "Molvi")
        except Exception:
            pass  # уведомление — best effort, не роняем обработку

    def stop(self):
        self._icon.stop()
