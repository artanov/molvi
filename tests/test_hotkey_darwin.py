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
