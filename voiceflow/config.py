import json
from pathlib import Path

DEFAULTS = {
    "model": "large-v3",
    "device": "auto",           # auto | cuda | cpu
    "compute_type": "int8_float16",
    "language": "auto",         # auto | ru | en
    "min_duration_sec": 0.3,
    "paste_mode": "clipboard",  # clipboard | type
    "input_device": None,       # имя/индекс устройства sounddevice; None = системное
    "samplerate": 16000,
}


def load_config(path):
    path = Path(path)
    cfg = dict(DEFAULTS)
    if not path.exists():
        return cfg
    data = json.loads(path.read_text(encoding="utf-8"))
    cfg.update({k: v for k, v in data.items() if k in DEFAULTS})
    return cfg
