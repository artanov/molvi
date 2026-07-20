import pytest

pytest.importorskip("pystray", reason="трей — только при установленном pystray")

from molvi.i18n import tr
from molvi.tray import Tray


def _make_tray():
    copied = []
    tray = Tray(
        on_toggle_pause=lambda: False,
        on_exit=lambda: None,
        on_copy_last=lambda: copied.append(True),
    )
    return tray, copied


def test_copy_last_menu_item_calls_callback():
    tray, copied = _make_tray()
    tray._copy_last(None, None)
    assert copied == [True]


def test_copy_last_menu_item_present():
    # Пункт «Скопировать последний текст» — второй (после «Настройки…»),
    # всегда активен: гейтинга через enabled= больше нет (pystray не
    # перечитывает его после update_menu(), см. отвергнутые альтернативы).
    tray, _ = _make_tray()
    item = tuple(tray._icon.menu.items)[1]
    assert item.text == tr("tray.copy_last")
    assert item._action == tray._copy_last


def test_default_callbacks_are_safe():
    # Tray создаётся в app.py до загрузки модели — дефолты не должны падать.
    tray = Tray(on_toggle_pause=lambda: False, on_exit=lambda: None)
    tray._copy_last(None, None)
