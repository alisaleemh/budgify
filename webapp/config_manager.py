from __future__ import annotations

from pathlib import Path
from typing import Dict, List
import yaml

DEFAULT_CONFIG: Dict[str, object] = {
    "bank_loaders": {
        "amex": "transaction_tracker.loaders.amex.AmexLoader",
        "canadiantire": "transaction_tracker.loaders.canadiantire.CanadianTireLoader",
        "tdvisa": "transaction_tracker.loaders.tdvisa.TDVisaLoader",
        "hometrust": "transaction_tracker.loaders.hometrust.HomeTrustLoader",
    },
    "output_modules": {
        "csv": "transaction_tracker.outputs.csv_output.CSVOutput",
        "sheets": "transaction_tracker.outputs.sheets_output.SheetsOutput",
        "excel": "transaction_tracker.outputs.excel_output.ExcelOutput",
    },
    "manual_transactions_file": "manual.yaml",
    "categories": {
        "restaurants": [],
        "groceries": [],
        "fun": [],
        "fuel": [],
    },
    "data_dir": "./data",
    "db_path": "budgify.db",
    "google": {
        "service_account_file": "/path/to/service-account.json",
        "sheet_folder_id": "GOOGLE_DRIVE_FOLDER_ID",
        "owner_email": "your.email@example.com",
    },
}

CONFIG_PATH = Path("/appdata/config.yaml")
LINKED_CONFIG_PATH = Path("/app/config.yaml")


def _merge_defaults(current: Dict[str, object], defaults: Dict[str, object]) -> Dict[str, object]:
    """Merge missing default keys into the current config recursively."""
    merged = dict(current)
    for key, value in defaults.items():
        if key not in merged:
            merged[key] = value
        elif isinstance(value, dict) and isinstance(merged[key], dict):
            merged[key] = _merge_defaults(merged[key], value)
    return merged


def ensure_config_file() -> Dict[str, object]:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    config: Dict[str, object] = {}

    if CONFIG_PATH.exists():
        config = load_config()
    elif LINKED_CONFIG_PATH.exists():
        config = load_config(LINKED_CONFIG_PATH)
        save_config(config)
    else:
        save_config(DEFAULT_CONFIG)
        config = DEFAULT_CONFIG

    _ensure_symlink()
    return config


def _ensure_symlink() -> None:
    LINKED_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    if LINKED_CONFIG_PATH.exists() or LINKED_CONFIG_PATH.is_symlink():
        try:
            if LINKED_CONFIG_PATH.resolve() == CONFIG_PATH.resolve():
                return
        except FileNotFoundError:
            pass
        LINKED_CONFIG_PATH.unlink(missing_ok=True)
    LINKED_CONFIG_PATH.symlink_to(CONFIG_PATH)


def load_config(path: Path | None = None) -> Dict[str, object]:
    target = path or CONFIG_PATH
    if not target.exists():
        return DEFAULT_CONFIG
    with target.open("r", encoding="utf-8") as fp:
        data = yaml.safe_load(fp) or {}
    return _merge_defaults(data, DEFAULT_CONFIG)


def save_config(config: Dict[str, object]) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CONFIG_PATH.open("w", encoding="utf-8") as fp:
        yaml.safe_dump(config, fp, sort_keys=False)
    _ensure_symlink()


def add_category(name: str) -> Dict[str, object]:
    config = load_config()
    categories: Dict[str, List[object]] = config.get("categories", {})  # type: ignore[assignment]
    if name not in categories:
        categories[name] = []
    config["categories"] = categories
    save_config(config)
    return config


def delete_category(name: str) -> Dict[str, object]:
    config = load_config()
    categories: Dict[str, List[object]] = config.get("categories", {})  # type: ignore[assignment]
    categories.pop(name, None)
    config["categories"] = categories
    save_config(config)
    return config


def rename_category(old_name: str, new_name: str) -> Dict[str, object]:
    config = load_config()
    categories: Dict[str, List[object]] = config.get("categories", {})  # type: ignore[assignment]
    if old_name in categories and new_name:
        categories[new_name] = categories.pop(old_name)
    config["categories"] = categories
    save_config(config)
    return config
