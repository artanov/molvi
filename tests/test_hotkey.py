import pytest

from molvi.hotkey import (
    WM_KEYDOWN, WM_KEYUP, WM_SYSKEYDOWN, WM_SYSKEYUP,
    VK_ESCAPE, VK_NAMES, HotkeyListener,
    human_label, names_to_vks, normalize_capture,
)

CTRL_L = VK_NAMES["ctrl_left"]
ALT_L = VK_NAMES["alt_left"]
X = VK_NAMES["x"]


def _make(combo=("ctrl_left", "alt_left", "x")):
    events = []
    hl = HotkeyListener(
        on_press=lambda: events.append("press"),
        on_release=lambda: events.append("release"),
        combo=names_to_vks(list(combo)),
    )
    return hl, events


def test_names_to_vks_and_unknown():
    assert names_to_vks(["ctrl_left", "x"]) == [0xA2, 0x58]
    with pytest.raises(ValueError):
        names_to_vks(["nosuchkey"])


def test_human_label():
    assert human_label(["ctrl_left", "alt_left", "x"]) == "Ctrl слева + Alt слева + X"


def test_human_label_english():
    from molvi import i18n
    i18n.set_language("en")
    try:
        assert human_label(["ctrl_left", "space"]) == "Left Ctrl + Space"
    finally:
        i18n.set_language("ru")


def test_human_label_russian_default():
    assert human_label(["ctrl_left", "space"]) == "Ctrl слева + Пробел"


def test_combo_fires_when_all_down_releases_on_any_up():
    hl, events = _make()
    hl._handle(WM_KEYDOWN, CTRL_L)
    hl._handle(WM_KEYDOWN, ALT_L)
    assert events == []
    hl._handle(WM_KEYDOWN, X)
    assert events == ["press"]
    hl._handle(WM_KEYUP, ALT_L)
    assert events == ["press", "release"]


def test_no_refire_until_full_release():
    hl, events = _make()
    for vk in (CTRL_L, ALT_L, X):
        hl._handle(WM_KEYDOWN, vk)
    hl._handle(WM_KEYUP, X)
    hl._handle(WM_KEYDOWN, X)  # дожатие без полного отпускания
    assert events == ["press", "release"]
    hl._handle(WM_KEYUP, CTRL_L)
    hl._handle(WM_KEYUP, ALT_L)
    for vk in (CTRL_L, ALT_L, X):
        hl._handle(WM_KEYDOWN, vk)
    assert events == ["press", "release", "press"]


def test_autorepeat_suppressed():
    hl, events = _make(combo=("ctrl_right",))
    vk = VK_NAMES["ctrl_right"]
    for _ in range(5):
        hl._handle(WM_KEYDOWN, vk)
    hl._handle(WM_KEYUP, vk)
    assert events == ["press", "release"]


def test_sys_messages_and_other_keys():
    hl, events = _make(combo=("alt_left",))
    hl._handle(WM_KEYDOWN, 0x41)  # 'A' — не из комбо
    hl._handle(WM_SYSKEYDOWN, ALT_L)
    hl._handle(WM_SYSKEYUP, ALT_L)
    assert events == ["press", "release"]


def test_injected_events_ignored():
    hl, events = _make(combo=("ctrl_left",))
    hl._handle(WM_KEYDOWN, CTRL_L, injected=True)
    hl._handle(WM_KEYUP, CTRL_L, injected=True)
    assert events == []


def test_set_combo_releases_active_recording():
    hl, events = _make(combo=("ctrl_left",))
    hl._handle(WM_KEYDOWN, CTRL_L)
    hl.set_combo([X])
    assert events == ["press", "release"]
    hl._handle(WM_KEYDOWN, X)
    assert events == ["press", "release", "press"]


def test_start_capture_releases_active_recording():
    hl, events = _make(combo=("ctrl_left",))
    hl._handle(WM_KEYDOWN, CTRL_L)  # active recording, key still held
    assert events == ["press"]
    captured = []
    hl.start_capture(captured.append)
    assert events == ["press", "release"]  # release fired exactly once
    # capture still works normally afterwards
    hl._handle(WM_KEYDOWN, X)
    hl._handle(WM_KEYUP, X)
    assert captured == [["x"]]
    # ctrl_left key-up (still physically down from before) must not
    # re-fire release or otherwise misbehave now that capture ended
    hl._handle(WM_KEYUP, CTRL_L)
    assert events == ["press", "release"]


def test_capture_collects_names_modifiers_first():
    hl, events = _make()
    captured = []
    hl.start_capture(captured.append)
    hl._handle(WM_KEYDOWN, X)       # порядок нажатия не важен
    hl._handle(WM_KEYDOWN, CTRL_L)
    hl._handle(WM_KEYDOWN, ALT_L)
    hl._handle(WM_KEYUP, X)
    hl._handle(WM_KEYUP, CTRL_L)
    assert captured == []           # ещё не всё отпущено
    hl._handle(WM_KEYUP, ALT_L)
    assert captured == [["ctrl_left", "alt_left", "x"]]
    assert events == []             # диктовка в захвате не дёргается


def test_capture_escape_cancels():
    hl, _ = _make()
    captured = []
    hl.start_capture(captured.append)
    hl._handle(WM_KEYDOWN, CTRL_L)
    hl._handle(WM_KEYDOWN, VK_ESCAPE)
    assert captured == [None]
    # после отмены обычная работа восстановлена
    hl._handle(WM_KEYUP, CTRL_L)


def test_capture_cancel_after_active_then_key_recaptured():
    # single-key combo активна, отменяем захват после отпускания ключа
    # PTT мид-захвате — следующее нажатие не должно проглатываться.
    hl, events = _make(combo=("ctrl_left",))
    hl._handle(WM_KEYDOWN, CTRL_L)  # active recording
    assert events == ["press"]
    captured = []
    hl.start_capture(captured.append)
    assert events == ["press", "release"]  # start_capture released active
    hl._handle(WM_KEYUP, CTRL_L)  # key released mid-capture
    hl._handle(WM_KEYDOWN, VK_ESCAPE)  # cancel
    assert captured == [None]
    # next press+release of the combo key must fire normally, not be
    # swallowed as an already-armed/never-released leftover.
    hl._handle(WM_KEYDOWN, CTRL_L)
    assert events == ["press", "release", "press"]
    hl._handle(WM_KEYUP, CTRL_L)
    assert events == ["press", "release", "press", "release"]


def test_capture_ignores_unknown_keys():
    hl, _ = _make()
    captured = []
    hl.start_capture(captured.append)
    hl._handle(WM_KEYDOWN, 0xFF)    # нет в таблице
    hl._handle(WM_KEYDOWN, X)
    hl._handle(WM_KEYUP, 0xFF)
    hl._handle(WM_KEYUP, X)
    assert captured == [["x"]]


def test_normalize_capture_orders_by_vk_within_groups():
    assert normalize_capture({VK_NAMES["x"], VK_NAMES["alt_left"], VK_NAMES["ctrl_right"]}) == [
        "ctrl_right", "alt_left", "x"
    ]


def test_cancel_capture_discards_callback_and_restores_hotkey():
    hl, events = _make()
    captured = []
    hl.start_capture(captured.append)
    hl._handle(WM_KEYDOWN, X)
    hl.cancel_capture()
    hl._handle(WM_KEYUP, X)  # завершение захвата после отмены — колбэк не зовётся
    assert captured == []
    # обычная работа хоткея восстановлена
    for vk in (CTRL_L, ALT_L, X):
        hl._handle(WM_KEYDOWN, vk)
    assert events == ["press"]
