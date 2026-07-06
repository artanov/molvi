import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

DEFAULTS = {
    "model": "large-v3",
    "device": "auto",           # auto | cuda | cpu
    "compute_type": "int8_float16",
    "language": "auto",         # auto | ru | en
    "hotkey": "right_ctrl",     # right_ctrl | left_ctrl
    "min_duration_sec": 0.3,
    "paste_mode": "auto",       # auto (консоль → печать, иначе Ctrl+V) | clipboard | type
    "input_device": None,       # имя/индекс устройства sounddevice; None = системное
    "samplerate": 16000,
}


def load_config(path):
    path = Path(path)
    cfg = dict(DEFAULTS)
    if not path.exists():
        return cfg
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        log.warning("config.json повреждён, использую настройки по умолчанию", exc_info=True)
        return cfg
    cfg.update({k: v for k, v in data.items() if k in DEFAULTS})
    return cfg
