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
