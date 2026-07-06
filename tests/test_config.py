import json

from voiceflow.config import DEFAULTS, load_config


def test_missing_file_returns_defaults(tmp_path):
    cfg = load_config(tmp_path / "nope.json")
    assert cfg == DEFAULTS
    assert cfg is not DEFAULTS  # копия, а не ссылка


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
