from voiceflow.settings import (
    LANGUAGES, QUALITY_PRESETS,
    dedupe_input_devices, language_index, quality_index_for_model,
)


def test_quality_presets_models():
    assert [m for _, m in QUALITY_PRESETS] == ["large-v3", "small", "base"]


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
