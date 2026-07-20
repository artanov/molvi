import logging
import math
import queue
import time
import tkinter as tk

from molvi import theme
from molvi.i18n import tr
from molvi.platform import overlay as _plat

log = logging.getLogger(__name__)

_BASE_SIZE = (400, 128)   # логический размер пилюли; соответствует 192 DPI (200%)

# Храним ключи, а не готовый текст: перевод берётся при показе — язык
# интерфейса мог смениться в Настройках уже после старта приложения.
_TEXT_STATES = {
    "recording": ("overlay.recording", theme.RECORDING),
    "transcribing": ("overlay.transcribing", theme.TRANSCRIBING),
}

N_BARS = 17
_FRAME_MS = 33           # ~30 кадров/с
_MIN_BAR = 0.08          # доля высоты: «плоская» тишина всё же видна

# Цвета эквалайзера и точки-индикатора по состояниям
_STATE_COLORS = {
    "recording": {"bars": theme.CREAM, "dot": theme.CORAL},
    "transcribing": {"bars": theme.WARN, "dot": theme.WARN},
}
# Автономная «волна обработки»: уровень для состояний без микрофона
_IDLE_LEVELS = {"recording": None, "transcribing": 0.35}


def compute_position(workarea, w, h, bottom_margin=96):
    """Позиция пилюли: низ-центр рабочей области монитора → (x, y)."""
    left, _top, right, bottom = workarea
    return left + (right - left - w) // 2, bottom - bottom_margin - h


def bar_heights(level, t, n=N_BARS):
    """Высоты баров (0..1): бегущая волна, дышащая от громкости голоса.

    level — огибающая громкости 0..1, t — счётчик кадров. Колокол к центру
    плюс разбегающиеся фазы дают «ходьбу волнами», а не дёргание поодиночке.
    """
    heights = []
    for i in range(n):
        bell = 0.35 + 0.65 * math.sin(math.pi * (i + 0.5) / n)
        wave = 0.55 + 0.45 * math.sin(t * 0.22 + i * 0.9)
        heights.append(min(1.0, _MIN_BAR + min(level, 1.0) * bell * wave))
    return heights


def eta_text(deadline, now):
    """Текст счётчика остатка обработки; None — не показывать.

    Оценка может соврать в меньшую сторону — при просрочке показываем
    «~0 с», а не отрицательные числа."""
    if deadline is None:
        return None
    return tr("overlay.eta", sec=max(0, math.ceil(deadline - now)))


class Overlay:
    """Мини-окно поверх всех окон. Не забирает фокус (платформенный трюк:
    WS_EX_NOACTIVATE / activationPolicy) — иначе вставка ушла бы в оверлей,
    а не в активное приложение."""

    def __init__(self, scale=1.0):
        self._scale = scale
        self._queue = queue.Queue()
        self._on_open_settings = None
        self._level_source = None      # callable → громкость 0..1 (Recorder.level)
        self._anim_state = None        # None | "recording" | "transcribing"
        self._anim_running = False
        self._env = 0.0                # огибающая громкости (атака/спад)
        self._t = 0                    # счётчик кадров
        self._eta_deadline = None      # monotonic-дедлайн счётчика «~N с»
        self._root = tk.Tk()
        self._root.withdraw()
        self._root.overrideredirect(True)
        self._root.attributes("-topmost", True)
        # «Не красть фокус» должно стоять ДО первого показа окна,
        # иначе первый deiconify() украдёт фокус у активного приложения.
        self._root.update_idletasks()
        _plat.apply_no_activate(self._root)
        self._canvas = None
        pill, bg = self._make_pill_image()
        if pill is not None:
            w, h = pill.width(), pill.height()
            self._root.configure(bg=bg)
            self._canvas = tk.Canvas(self._root, width=w, height=h,
                                     bg=bg, highlightthickness=0, bd=0)
            self._canvas.create_image(0, 0, image=pill, anchor="nw")
            self._pill = pill  # держим ссылку от GC
            self._build_scene(w, h)
            self._canvas.pack()
        else:
            self._root.attributes("-alpha", 0.92)
            self._label = tk.Label(
                self._root, text="", font=("Segoe UI", 12, "bold"),
                fg=theme.CREAM, bg=theme.RECORDING, padx=18, pady=8,
            )
            self._label.pack()
            w, h = 190, 44
        self._w, self._h = w, h
        self._place()
        # На маке окно уже размаплено невидимым (см. darwin.apply_no_activate) —
        # возвращаем его в «скрытое» состояние после примерки геометрии.
        _plat.hide_window(self._root)
        self._root.after(50, self._poll)

    @property
    def root(self):
        return self._root

    def _place(self):
        area = _plat.monitor_workarea()
        if area is None:  # запасной вариант: первичный экран по метрикам tk
            area = (0, 0, self._root.winfo_screenwidth(),
                    self._root.winfo_screenheight())
        x, y = compute_position(area, self._w, self._h)
        self._root.geometry(f"{self._w}x{self._h}+{x}+{y}")

    def _make_pill_image(self):
        """Фон-пилюля, отрисованная на лету → (PhotoImage, цвет фона);
        (None, None) → текстовый fallback.

        Края рисуем с суперсэмплингом; превращение RGBA в отображаемое
        изображение и способ прозрачности — платформенные
        (ключевой цвет на Windows, настоящая альфа на macOS)."""
        try:
            from PIL import Image, ImageDraw
            scale = _plat.dpi(self._root) / 192 * self._scale
            size = (max(1, int(_BASE_SIZE[0] * scale)), max(1, int(_BASE_SIZE[1] * scale)))
            ss = 4
            big = Image.new("RGBA", (size[0] * ss, size[1] * ss), (0, 0, 0, 0))
            d = ImageDraw.Draw(big)
            d.rounded_rectangle(
                (0, 0, size[0] * ss - 1, size[1] * ss - 1),
                radius=size[1] * ss // 2,
                fill=theme.rgba(theme.INK_800, 255),
                outline=theme.rgba(theme.INK_600, 255),
                width=2 * ss,
            )
            img = big.resize(size, Image.LANCZOS)
            # Прозрачность включаем ПОСЛЕ успешной конвертации картинки:
            # упади она — текстовый fallback рисуется в обычном окне, а не
            # в уже «продырявленном».
            photo = _plat.pill_to_photoimage(self._root, img)
            bg = _plat.enable_transparency(self._root)
            return photo, bg
        except Exception:
            log.warning("Не удалось отрисовать пилюлю оверлея", exc_info=True)
            return None, None

    def _build_scene(self, w, h):
        """Точка-индикатор слева + бары эквалайзера. Геометрия — от пилюли."""
        self._dot_r = h * 0.09
        self._dot_cx = h * 0.52
        self._cy = h / 2
        self._dot = self._canvas.create_oval(0, 0, 0, 0, width=0,
                                             fill=theme.CORAL)
        # Счётчик «~N с» — на месте точки: в жёлтом состоянии точка
        # малоинформативна, а места справа от баров нет.
        self._eta_item = self._canvas.create_text(
            h * 0.55, self._cy, text="", anchor="center",
            fill=theme.WARN, font=("Segoe UI", max(8, int(h * 0.18)), "bold"))
        x0 = h * 0.92
        x1 = w - h * 0.42
        step = (x1 - x0) / N_BARS
        bar_w = step * 0.52
        self._max_half = h * 0.30
        self._bars = []
        self._bar_x = []
        for i in range(N_BARS):
            bx = x0 + i * step + (step - bar_w) / 2
            self._bar_x.append((bx, bx + bar_w))
            self._bars.append(self._canvas.create_rectangle(
                bx, self._cy - 2, bx + bar_w, self._cy + 2,
                width=0, fill=theme.CREAM))

    def _apply_state_colors(self, state):
        colors = _STATE_COLORS[state]
        for bar in self._bars:
            self._canvas.itemconfigure(bar, fill=colors["bars"])
        self._canvas.itemconfigure(self._dot, fill=colors["dot"])

    def _animate(self):
        state = self._anim_state
        if state is None or self._canvas is None:
            self._anim_running = False
            return
        self._t += 1
        level = _IDLE_LEVELS[state]
        if level is None:  # запись: живой уровень с микрофона
            raw = 0.0
            if self._level_source is not None:
                try:
                    raw = min(1.0, float(self._level_source()) * 9.0)
                except Exception:
                    raw = 0.0
            # Быстрая атака, плавный спад — волна не дёргается на паузах речи.
            self._env = raw if raw > self._env else self._env * 0.82
            level = self._env
        for bar, (bx0, bx1), h in zip(self._bars, self._bar_x,
                                      bar_heights(level, self._t)):
            half = max(2.0, h * self._max_half)
            self._canvas.coords(bar, bx0, self._cy - half, bx1, self._cy + half)
        show_eta = state == "transcribing" and self._eta_deadline is not None
        txt = eta_text(self._eta_deadline, time.monotonic()) if show_eta else None
        self._canvas.itemconfigure(self._eta_item, text=txt or "")
        pulse = 1.0 + (0.18 * math.sin(self._t * 0.16) if state == "recording" else 0.0)
        r = 0.0 if show_eta else self._dot_r * pulse   # счётчик вместо точки
        self._canvas.coords(self._dot, self._dot_cx - r, self._cy - r,
                            self._dot_cx + r, self._cy + r)
        self._root.after(_FRAME_MS, self._animate)

    def _start_anim(self, state):
        self._anim_state = state
        self._env = 0.0
        self._apply_state_colors(state)
        if not self._anim_running:
            self._anim_running = True
            self._animate()

    def _poll(self):
        while True:
            try:
                state = self._queue.get_nowait()
            except queue.Empty:
                break
            eta_sec = None
            if isinstance(state, tuple):
                state, eta_sec = state
            if state == "quit":
                self._root.destroy()
                return
            # Ошибка обработки одного состояния (например, упавшее открытие
            # настроек) не должна обрывать цикл: иначе перестал бы работать
            # и "quit" — приложение зависало бы навсегда при выходе.
            try:
                if state == "settings":
                    if self._on_open_settings is not None:
                        self._on_open_settings()
                elif state == "hide":
                    self._anim_state = None
                    self._eta_deadline = None
                    _plat.hide_window(self._root)
                elif self._canvas is not None:
                    self._start_anim(state)
                    self._eta_deadline = (None if eta_sec is None
                                          else time.monotonic() + eta_sec)
                    self._place()  # монитор активного окна — куда и печатаем
                    _plat.show_window(self._root)
                else:
                    key, bg = _TEXT_STATES[state]
                    self._label.config(text=tr(key), bg=bg)
                    self._place()
                    _plat.show_window(self._root)
            except Exception:
                log.exception("Оверлей: ошибка обработки состояния %r", state)
        self._root.after(50, self._poll)

    # --- потокобезопасный интерфейс (Controller, Tray) ---
    def show_recording(self):
        self._queue.put("recording")

    def show_transcribing(self, eta_sec=None):
        self._queue.put(("transcribing", eta_sec))

    def hide(self):
        self._queue.put("hide")

    def open_settings(self):
        self._queue.put("settings")

    def set_settings_opener(self, fn):
        self._on_open_settings = fn

    def set_level_source(self, fn):
        """fn() → текущая громкость микрофона 0..1 (читается в tk-потоке)."""
        self._level_source = fn

    def schedule_quit(self):
        self._queue.put("quit")

    def run(self):
        self._root.mainloop()
