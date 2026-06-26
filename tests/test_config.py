from __future__ import annotations

from pathlib import Path

from safe_tool.config import get_api_config, get_risk_rules, load_config, masked_config, write_config, write_default_config


def test_load_config_returns_defaults_without_config_yaml(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    config = load_config()

    assert "risk_rules" in config
    assert "settings" in config
    assert "api" in config


def test_write_default_config_creates_config_yaml(tmp_path: Path) -> None:
    target = tmp_path / "config.yaml"

    written = write_default_config(str(target))

    assert written == target
    assert target.exists()


def test_get_risk_rules_returns_risk_rules(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    config = load_config()

    rules = get_risk_rules(config)

    assert "copy" in rules


def test_api_config_persists_and_masks_secret(tmp_path: Path) -> None:
    target = tmp_path / "config.yaml"
    config = load_config()
    api = get_api_config(config)
    api["provider"] = "deepseek"
    api["deepseek"]["enabled"] = True
    api["deepseek"]["api_key"] = "sk-1234567890"
    config["api"] = api

    write_config(config, str(target))

    loaded = load_config(str(target))
    masked = masked_config(loaded)

    assert get_api_config(loaded)["deepseek"]["api_key"] == "sk-1234567890"
    assert masked["api"]["deepseek"]["api_key"] == "sk-1...7890"
