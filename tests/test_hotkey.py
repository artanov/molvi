from voiceflow.hotkey import WM_KEYDOWN, WM_KEYUP, VK_RCONTROL, HotkeyListener


def _make():
    events = []
    hl = HotkeyListener(
        on_press=lambda: events.append("press"),
        on_release=lambda: events.append("release"),
    )
    return hl, events


def test_press_release_cycle():
    hl, events = _make()
    hl._handle(WM_KEYDOWN, VK_RCONTROL)
    hl._handle(WM_KEYUP, VK_RCONTROL)
    assert events == ["press", "release"]


def test_autorepeat_suppressed():
    hl, events = _make()
    for _ in range(5):
        hl._handle(WM_KEYDOWN, VK_RCONTROL)  # Windows шлёт KEYDOWN каждые ~30 мс
    hl._handle(WM_KEYUP, VK_RCONTROL)
    assert events == ["press", "release"]


def test_other_keys_ignored():
    hl, events = _make()
    hl._handle(WM_KEYDOWN, 0x41)  # 'A'
    hl._handle(WM_KEYUP, 0x41)
    assert events == []


def test_release_without_press_ignored():
    hl, events = _make()
    hl._handle(WM_KEYUP, VK_RCONTROL)
    assert events == []
