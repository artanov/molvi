from molvi.settings import (
    LANGUAGES, QUALITY_PRESETS, _DEFAULT_DEVICE_LABEL,
    dedupe_input_devices, device_choices, language_index, quality_index_for_model,
)


def test_quality_presets_models():
    import sys
    top = "large-v3-turbo" if sys.platform == "darwin" else "large-v3"
    assert [m for _, m in QUALITY_PRESETS] == [top, "small", "base"]


def test_quality_index_for_model():
    assert quality_index_for_model("small") == 1
    assert quality_index_for_model("no-such") == 0


def test_language_index():
    assert [c for _, c in LANGUAGES] == ["auto", "ru", "en"]
    assert language_index("ru") == 1
    assert language_index("xx") == 0


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
