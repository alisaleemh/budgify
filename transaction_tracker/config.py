# transaction_tracker/config.py
from __future__ import annotations

from copy import deepcopy

import yaml


DEFAULT_CONFIG = {
    "analytics": {
        "enabled": True,
        "sampling_rate": 1.0,
        "dev_logging": False,
    }
}


def _merge_defaults(config: dict, defaults: dict) -> dict:
    merged = deepcopy(defaults)
    for key, value in config.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_defaults(value, merged[key])
        else:
            merged[key] = value
    return merged


def load_config(path):
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    if not isinstance(raw, dict):
        return deepcopy(DEFAULT_CONFIG)
    return _merge_defaults(raw, DEFAULT_CONFIG)
