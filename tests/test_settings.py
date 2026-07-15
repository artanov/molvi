import pytest

from molvi import i18n
from molvi.settings import (
    dedupe_input_devices, device_choices, language_choices, language_index,
    quality_index_for_model, quality_presets, ui_language_choices, ui_language_index,
)

_DEFAULT_DEVICE_LABEL = "Системный по умолчанию"


@pytest.fixture(autouse=True)
def _reset_language():
    # Тесты зависят от текущего языка i18n — фиксируем ru независимо
    # от порядка запуска файлов.
    i18n.set_language("ru")
    yield
    i18n.set_language("ru")


def test_quality_presets_models():
    import sys
    top = "large-v3-turbo" if sys.platform == "darwin" else "large-v3"
    assert [m for _, m in quality_presets()] == [top, "small", "base"]


def test_quality_presets_english():
    from molvi import i18n
    i18n.set_language("en")
    try:
        labels = [label for label, _ in quality_presets()]
        assert any("Best" in l for l in labels)
    finally:
        i18n.set_language("ru")


def test_quality_index_for_model():
    assert quality_index_for_model("small") == 1
    assert quality_index_for_model("no-such") == 0


def test_language_index():
    assert [c for _, c in language_choices()] == ["auto", "ru", "en"]
    assert language_index("ru") == 1
    assert language_index("xx") == 0


def test_ui_language_choices_codes():
    assert [code for _, code in ui_language_choices()] == ["auto", "ru", "en"]


def test_dedupe_input_devices():
    devices = [
        {"name": "Mic A", "max_input_channels": 2},
        {"name": "Speakers", "max_input_channels": 0},
        {"name": "Mic A", "max_input_channels": 2},   # дубль из другого hostapi
        {"name": "Mic B", "max_input_channels": 1},
    ]
    assert dedupe_input_devices(devices) == ["Mic A", "Mic B"]


def test_device_choices_known_name():
    names = ["Mic A", "Mic B"]
    values, idx, mapping = device_choices(names, "Mic B")
    assert values == [_DEFAULT_DEVICE_LABEL, "Mic A", "Mic B"]
    assert idx == 2
    assert mapping["Mic B"] == "Mic B"


def test_device_choices_none_is_default():
    names = ["Mic A", "Mic B"]
    values, idx, mapping = device_choices(names, None)
    assert idx == 0
    assert values[0] == _DEFAULT_DEVICE_LABEL
    assert mapping[_DEFAULT_DEVICE_LABEL] is None


def test_device_choices_unknown_value_kept_as_current():
    names = ["Mic A", "Mic B"]
    for unknown in (7, "Отключённый мик"):
        values, idx, mapping = device_choices(names, unknown)
        label = f"Текущее: {unknown}"
        assert values[1] == label
        assert idx == 1
        assert mapping[label] == unknown


def test_device_choices_english_default_label():
    from molvi import i18n
    i18n.set_language("en")
    try:
        values, idx, mapping = device_choices(["Mic A"], None)
        assert values[0] == "System default"
        assert mapping["System default"] is None
    finally:
        i18n.set_language("ru")


def test_ui_language_index():
    assert ui_language_index("ru") == 1
    assert ui_language_index("xx") == 0
