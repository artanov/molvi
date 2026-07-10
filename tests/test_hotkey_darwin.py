"""Таблица клавиш macOS и автомат PTT поверх неё. Чистый Python —
гоняется на любой ОС (обвязку event tap не трогает)."""
import pytest

from molvi.hotkey import WM_KEYDOWN, WM_KEYUP, HotkeyListener
from molvi.platform.darwin import hotkey as dhk


def test_vk_codes_unique():
    assert len(set(dhk.VK_NAMES.values())) == len(dhk.VK_NAMES)


def test_default_hotkey_resolvable_and_labeled():
    vks = dhk.names_to_vks(dhk.DEFAULT_HOTKEY)
    assert vks == [0x36]  # kVK_RightCommand
    assert dhk.human_label(dhk.DEFAULT_HOTKEY) == "⌘ Cmd справа"


def test_unknown_name_raises():
    with pytest.raises(ValueError):
        dhk.names_to_vks(["insert"])  # клавиши Insert на маке нет


def test_capture_normalizes_with_mac_codes():
    # Порядок: модификаторы по vk, затем остальные — как в Windows-версии.
    vks = {dhk.VK_NAMES["x"], dhk.VK_NAMES["win_right"], dhk.VK_NAMES["ctrl_left"]}
    assert dhk.normalize_capture(vks) == ["win_right", "ctrl_left", "x"]


def test_state_machine_with_mac_table_and_escape():
    events, captured = [], []
    hl = HotkeyListener(
        on_press=lambda: events.append("press"),
        on_release=lambda: events.append("release"),
        combo=dhk.names_to_vks(["win_right"]),
        table=dhk.TABLE,
    )
    hl._handle(WM_KEYDOWN, dhk.VK_NAMES["win_right"])
    hl._handle(WM_KEYUP, dhk.VK_NAMES["win_right"])
    assert events == ["press", "release"]
    # Esc в захвате — отмена: код Esc у мака свой (0x35), не Windows-овский.
    hl.start_capture(captured.append)
    hl._handle(WM_KEYDOWN, dhk.VK_ESCAPE)
    assert captured == [None]


def test_capture_returns_names_via_mac_table():
    captured = []
    hl = dhk.HotkeyListener(
        on_press=lambda: None, on_release=lambda: None,
        combo=dhk.names_to_vks(dhk.DEFAULT_HOTKEY),
    )
    hl.start_capture(captured.append)
    hl._handle(WM_KEYDOWN, dhk.VK_NAMES["win_left"])
    hl._handle(WM_KEYDOWN, dhk.VK_NAMES["v"])
    hl._handle(WM_KEYUP, dhk.VK_NAMES["v"])
    hl._handle(WM_KEYUP, dhk.VK_NAMES["win_left"])
    assert captured == [["win_left", "v"]]


# --- трансляция CGEvent → автомат (_on_event: чистая логика, без Quartz) ---

def _make_listener(combo=("win_right",)):
    events = []
    hl = dhk.HotkeyListener(
        on_press=lambda: events.append("press"),
        on_release=lambda: events.append("release"),
        combo=dhk.names_to_vks(list(combo)),
    )
    return hl, events


def test_flags_changed_maps_to_down_up():
    hl, events = _make_listener()
    rcmd, mask = 0x36, 0x0010
    hl._on_event(12, rcmd, mask, 0)   # flagsChanged: бит правого Cmd взведён
    assert events == ["press"]
    hl._on_event(12, rcmd, 0, 0)      # бит снят — клавиша отпущена
    assert events == ["press", "release"]


def test_plain_keys_use_keydown_keyup():
    hl, events = _make_listener(combo=("f5",))
    f5 = dhk.VK_NAMES["f5"]
    hl._on_event(10, f5, 0, 0)
    hl._on_event(11, f5, 0, 0)
    assert events == ["press", "release"]


def test_injected_cmd_v_does_not_trigger_ptt():
    # Наша собственная вставка Cmd+V не должна дёргать хоткей с Cmd.
    hl, events = _make_listener(combo=("win_left",))
    lcmd, mask = 0x37, 0x0008
    hl._on_event(12, lcmd, mask, dhk.INJECT_MAGIC)
    hl._on_event(10, dhk.VK_NAMES["v"], mask, dhk.INJECT_MAGIC)
    hl._on_event(11, dhk.VK_NAMES["v"], mask, dhk.INJECT_MAGIC)
    hl._on_event(12, lcmd, 0, dhk.INJECT_MAGIC)
    assert events == []


def test_autorepeat_keydown_suppressed():
    hl, events = _make_listener(combo=("f5",))
    f5 = dhk.VK_NAMES["f5"]
    for _ in range(5):                # автоповтор: keyDown сыплется, keyUp нет
        hl._on_event(10, f5, 0, 0)
    hl._on_event(11, f5, 0, 0)
    assert events == ["press", "release"]


def test_capslock_and_fn_ignored():
    hl, events = _make_listener()
    hl._on_event(12, 0x39, 0x10000, 0)  # capslock: toggle, PTT невозможен
    hl._on_event(12, 0x3F, 0x800000, 0)  # fn
    assert events == []


def test_modifier_combo_via_flags_changed():
    # Комбо из двух модификаторов: каждый приходит отдельным flagsChanged
    # с накопленными битами.
    hl, events = _make_listener(combo=("shift_left", "ctrl_left"))
    shift, ctrl = 0x38, 0x3B
    hl._on_event(12, shift, 0x0002, 0)
    assert events == []
    hl._on_event(12, ctrl, 0x0002 | 0x0001, 0)
    assert events == ["press"]
    hl._on_event(12, shift, 0x0001, 0)  # shift отпущен, ctrl ещё зажат
    assert events == ["press", "release"]
