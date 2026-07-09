import json
import logging
import os
from pathlib import Path

log = logging.getLogger(__name__)

DEFAULTS = {
    "model": "large-v3",
    "device": "auto",           # auto | cuda | cpu
    "compute_type": "int8_float16",
    "language": "auto",         # auto | ru | en
    "hotkey": ["ctrl_left"],    # список имён клавиш (см. hotkey.VK_NAMES)
    "sounds": True,
    "overlay_scale": 0.6,       # размер пилюли-оверлея (1.0 = 200×64 лог. пикселей)
    "min_duration_sec": 0.3,
    "paste_mode": "auto",       # auto (консоль → печать, иначе Ctrl+V) | clipboard | type
    "input_device": None,       # имя/индекс устройства sounddevice; None = системное
    "samplerate": 16000,
}

_HOTKEY_V1 = {"left_ctrl": ["ctrl_left"], "right_ctrl": ["ctrl_right"]}


def _migrate_hotkey(value):
    if isinstance(value, str):
        migrated = _HOTKEY_V1.get(value)
        if migrated is None:
            log.warning("Неизвестный hotkey %r из конфига v1, использую ctrl_right", value)
            return ["ctrl_right"]
        return list(migrated)
    if isinstance(value, list) and value and all(isinstance(x, str) for x in value):
        return list(value)
    log.warning("Некорректный hotkey %r, использую значение по умолчанию", value)
    return list(DEFAULTS["hotkey"])


def load_config(path):
    path = Path(path)
    cfg = dict(DEFAULTS)
    if not path.exists():
        cfg["hotkey"] = list(cfg["hotkey"])
        return cfg
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        log.warning("config.json повреждён, использую настройки по умолчанию", exc_info=True)
        cfg["hotkey"] = list(cfg["hotkey"])
        return cfg
    if not isinstance(data, dict):
        log.warning("config.json не является объектом, использую настройки по умолчанию")
        cfg["hotkey"] = list(cfg["hotkey"])
        return cfg
    for k, v in data.items():
        if k not in DEFAULTS:
            continue
        if k != "hotkey" and not _valid_type(k, v):
            # Конфиг редактируют руками: "16000" вместо 16000 не должен
            # ронять приложение на старте — берём дефолт и предупреждаем.
            log.warning("config.json: %s=%r — неверный тип, использую %r",
                        k, v, DEFAULTS[k])
            continue
        cfg[k] = v
    cfg["hotkey"] = _migrate_hotkey(cfg["hotkey"])
    cfg["hotkey"] = list(cfg["hotkey"])
    return cfg


def _valid_type(key, value):
    default = DEFAULTS[key]
    if key == "input_device":            # имя, индекс или None (системный)
        return value is None or isinstance(value, (str, int))
    if isinstance(default, bool):
        return isinstance(value, bool)
    if isinstance(default, float):       # float принимает и int (0.3 ← 1)
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if isinstance(default, int):
        return isinstance(value, int) and not isinstance(value, bool)
    return isinstance(value, type(default))


def save_config(path, cfg):
    # Атомарно: краш/выключение посреди записи не должны оставлять битый
    # JSON (он молча откатил бы пользователя на дефолты при старте).
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)
