import pytest

pytest.importorskip("pystray", reason="трей — только при установленном pystray")

from molvi.tray import Tray


def _make_tray(has_text):
    copied = []
    tray = Tray(
        on_toggle_pause=lambda: False,
        on_exit=lambda: None,
        on_copy_last=lambda: copied.append(True),
        has_last_text=lambda: has_text["value"],
    )
    return tray, copied


def test_copy_last_menu_item_calls_callback():
    has_text = {"value": True}
    tray, copied = _make_tray(has_text)
    tray._copy_last(None, None)
    assert copied == [True]


def test_copy_last_enabled_follows_has_last_text():
    has_text = {"value": False}
    tray, copied = _make_tray(has_text)
    # Пункт «Скопировать последний текст» — второй (после «Настройки…»).
    item = tuple(tray._icon.menu.items)[1]
    assert item.enabled is False   # диктовок ещё не было — пункт серый
    has_text["value"] = True
    assert item.enabled is True


def test_default_callbacks_are_safe():
    # Tray создаётся в app.py до загрузки модели — дефолты не должны падать.
    tray = Tray(on_toggle_pause=lambda: False, on_exit=lambda: None)
    tray._copy_last(None, None)
    item = tuple(tray._icon.menu.items)[1]
    assert item.enabled is False
