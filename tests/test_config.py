import json

from molvi.config import DEFAULTS, load_config, save_config


def test_missing_file_returns_defaults(tmp_path):
    cfg = load_config(tmp_path / "nope.json")
    assert cfg == DEFAULTS
    assert cfg is not DEFAULTS  # копия, а не ссылка
    assert cfg["hotkey"] is not DEFAULTS["hotkey"]  # и hotkey — не общий список


def test_partial_file_merges_over_defaults(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"language": "ru"}), encoding="utf-8")
    cfg = load_config(p)
    assert cfg["language"] == "ru"
    assert cfg["model"] == DEFAULTS["model"]


def test_unknown_keys_ignored(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"bogus": 1, "device": "cpu"}), encoding="utf-8")
    cfg = load_config(p)
    assert "bogus" not in cfg
    assert cfg["device"] == "cpu"


def test_corrupt_file_returns_defaults(tmp_path):
    p = tmp_path / "config.json"
    p.write_text("{not json", encoding="utf-8")
    cfg = load_config(p)
    assert cfg == DEFAULTS
    assert cfg is not DEFAULTS


def test_defaults_have_v2_keys():
    assert DEFAULTS["hotkey"] == ["ctrl_left"]
    assert DEFAULTS["sounds"] is True


def test_invalid_types_fall_back_to_defaults(tmp_path):
    """Конфиг редактируют руками: мусорные типы не должны ронять запуск."""
    p = tmp_path / "config.json"
    p.write_text(json.dumps({
        "samplerate": "16000",     # строка вместо int
        "overlay_scale": None,     # null
        "min_duration_sec": [],    # список
        "sounds": 1,               # int вместо bool
        "language": "ru",          # корректное — применяется
    }), encoding="utf-8")
    cfg = load_config(p)
    assert cfg["samplerate"] == DEFAULTS["samplerate"]
    assert cfg["overlay_scale"] == DEFAULTS["overlay_scale"]
    assert cfg["min_duration_sec"] == DEFAULTS["min_duration_sec"]
    assert cfg["sounds"] is True
    assert cfg["language"] == "ru"


def test_float_field_accepts_int(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"min_duration_sec": 1}), encoding="utf-8")
    assert load_config(p)["min_duration_sec"] == 1


def test_input_device_accepts_str_int_none(tmp_path):
    p = tmp_path / "config.json"
    for val in ("Микрофон (USB)", 3, None):
        p.write_text(json.dumps({"input_device": val}), encoding="utf-8")
        assert load_config(p)["input_device"] == val
    p.write_text(json.dumps({"input_device": [1]}), encoding="utf-8")
    assert load_config(p)["input_device"] is None


def test_save_config_atomic_leaves_no_tmp(tmp_path):
    p = tmp_path / "config.json"
    save_config(p, dict(DEFAULTS, hotkey=list(DEFAULTS["hotkey"])))
    assert json.loads(p.read_text(encoding="utf-8"))["model"] == DEFAULTS["model"]
    assert list(tmp_path.glob("*.tmp")) == []  # временный файл убран os.replace


def test_hotkey_v1_strings_migrate(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"hotkey": "left_ctrl"}), encoding="utf-8")
    assert load_config(p)["hotkey"] == ["ctrl_left"]
    p.write_text(json.dumps({"hotkey": "right_ctrl"}), encoding="utf-8")
    assert load_config(p)["hotkey"] == ["ctrl_right"]
    p.write_text(json.dumps({"hotkey": "weird"}), encoding="utf-8")
    assert load_config(p)["hotkey"] == ["ctrl_right"]


def test_hotkey_list_passes_through(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"hotkey": ["ctrl_left", "alt_left", "x"]}), encoding="utf-8")
    assert load_config(p)["hotkey"] == ["ctrl_left", "alt_left", "x"]


def test_hotkey_garbage_falls_back_to_default(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"hotkey": [1, 2]}), encoding="utf-8")
    assert load_config(p)["hotkey"] == DEFAULTS["hotkey"]
    p.write_text(json.dumps({"hotkey": []}), encoding="utf-8")
    assert load_config(p)["hotkey"] == DEFAULTS["hotkey"]


def test_save_config_round_trip(tmp_path):
    p = tmp_path / "config.json"
    cfg = load_config(p)
    cfg["hotkey"] = ["f9"]
    cfg["sounds"] = False
    save_config(p, cfg)
    loaded = load_config(p)
    assert loaded["hotkey"] == ["f9"]
    assert loaded["sounds"] is False
