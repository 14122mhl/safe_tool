from __future__ import annotations

from pathlib import Path

from safe_tool.cli import main
from safe_tool.config import load_config


def test_api_set_writes_deepseek_configuration(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"

    exit_code = main(["--config", str(config_path), "api", "set", "deepseek", "--api-key", "sk-test", "--model", "deepseek-chat"])

    config = load_config(str(config_path))
    assert exit_code == 0
    assert config["api"]["provider"] == "deepseek"
    assert config["api"]["deepseek"]["enabled"] is True
    assert config["api"]["deepseek"]["api_key"] == "sk-test"


def test_api_show_masks_deepseek_key(tmp_path: Path, capsys) -> None:
    config_path = tmp_path / "config.yaml"
    main(["--config", str(config_path), "api", "set", "deepseek", "--api-key", "sk-1234567890"])

    exit_code = main(["--config", str(config_path), "api", "show"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "sk-1...7890" in output
    assert "sk-1234567890" not in output
