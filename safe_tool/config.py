from __future__ import annotations

import importlib
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Optional

from .constants import RISK_MODULES


DEFAULT_SETTINGS: Dict[str, Any] = {
    "default_engine": "ansible",
    "default_env": "dev",
    "require_prod_confirm": True,
    "dry_run_by_default": True,
    "min_goal_confidence_to_apply": 0.75,
}

DEFAULT_API_CONFIG: Dict[str, Any] = {
    "provider": None,
    "deepseek": {
        "enabled": False,
        "api_key": None,
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat",
        "timeout": 30,
    },
}


def default_config_path() -> Path:
    return Path.cwd() / "config.yaml"


def default_config() -> Dict[str, Any]:
    return {
        "risk_rules": deepcopy(RISK_MODULES),
        "settings": deepcopy(DEFAULT_SETTINGS),
        "api": deepcopy(DEFAULT_API_CONFIG),
    }


def _merge_nested_defaults(defaults: Dict[str, Any], data: Dict[str, Any]) -> Dict[str, Any]:
    merged = deepcopy(defaults)
    for key, value in data.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_nested_defaults(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config(config_path: Optional[str] = None) -> dict:
    path = Path(config_path) if config_path else default_config_path()
    if not path.exists():
        if config_path:
            raise RuntimeError(f"configuration file not found: {path}")
        return default_config()

    try:
        yaml = importlib.import_module("yaml")
    except ImportError as exc:
        raise RuntimeError("PyYAML is required. Install it with: python3 -m pip install pyyaml") from exc

    try:
        with path.open("r", encoding="utf-8") as file_obj:
            data = yaml.safe_load(file_obj) or {}
    except yaml.YAMLError as exc:
        raise RuntimeError(f"failed to parse configuration file {path}: {exc}") from exc
    except OSError as exc:
        raise RuntimeError(f"failed to read configuration file {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise RuntimeError(f"invalid configuration file {path}: expected a YAML mapping")

    merged = default_config()
    if "risk_rules" in data:
        if not isinstance(data["risk_rules"], dict):
            raise RuntimeError(f"invalid configuration file {path}: risk_rules must be a mapping")
        merged["risk_rules"].update(data["risk_rules"])
    if "settings" in data:
        if not isinstance(data["settings"], dict):
            raise RuntimeError(f"invalid configuration file {path}: settings must be a mapping")
        merged["settings"].update(data["settings"])
    if "api" in data:
        if not isinstance(data["api"], dict):
            raise RuntimeError(f"invalid configuration file {path}: api must be a mapping")
        merged["api"] = _merge_nested_defaults(DEFAULT_API_CONFIG, data["api"])

    return merged


def write_config(config: Dict[str, Any], path: Optional[str] = None) -> Path:
    target = Path(path) if path else default_config_path()

    try:
        yaml = importlib.import_module("yaml")
    except ImportError as exc:
        raise RuntimeError("PyYAML is required. Install it with: python3 -m pip install pyyaml") from exc

    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        target.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"failed to write configuration file {target}: {exc}") from exc
    return target


def write_default_config(path: Optional[str] = None) -> Path:
    target = Path(path) if path else default_config_path()
    if target.exists():
        return target

    try:
        yaml = importlib.import_module("yaml")
    except ImportError as exc:
        raise RuntimeError("PyYAML is required. Install it with: python3 -m pip install pyyaml") from exc

    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        target.write_text(yaml.safe_dump(default_config(), sort_keys=False), encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"failed to write configuration file {target}: {exc}") from exc
    return target


def mask_secret(value: Optional[str]) -> Optional[str]:
    if not value:
        return value
    if len(value) <= 8:
        return "********"
    return value[:4] + "..." + value[-4:]


def masked_config(config: Dict[str, Any]) -> Dict[str, Any]:
    data = deepcopy(config)
    api = data.get("api", {})
    if isinstance(api, dict):
        for provider_config in api.values():
            if isinstance(provider_config, dict) and "api_key" in provider_config:
                provider_config["api_key"] = mask_secret(provider_config.get("api_key"))
    return data


def get_risk_rules(config: dict) -> dict:
    rules = config.get("risk_rules", {})
    if not isinstance(rules, dict):
        raise RuntimeError("invalid configuration: risk_rules must be a mapping")
    return rules


def get_settings(config: dict) -> dict:
    settings = config.get("settings", {})
    if not isinstance(settings, dict):
        raise RuntimeError("invalid configuration: settings must be a mapping")
    merged = deepcopy(DEFAULT_SETTINGS)
    merged.update(settings)
    return merged


def get_api_config(config: dict) -> dict:
    api = config.get("api", {})
    if not isinstance(api, dict):
        raise RuntimeError("invalid configuration: api must be a mapping")
    return _merge_nested_defaults(DEFAULT_API_CONFIG, api)
