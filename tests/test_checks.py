from __future__ import annotations

from pathlib import Path

from safe_tool.checks import check_env, check_playbook_exists


def test_check_playbook_exists_passes_for_existing_file(tmp_path: Path) -> None:
    playbook = tmp_path / "demo.yml"
    playbook.write_text("---\n", encoding="utf-8")

    result = check_playbook_exists(str(playbook))

    assert result.status == "PASS"


def test_check_playbook_exists_fails_for_missing_file(tmp_path: Path) -> None:
    result = check_playbook_exists(str(tmp_path / "missing.yml"))

    assert result.status == "FAIL"


def test_check_env_passes_for_dev() -> None:
    result = check_env("dev")

    assert result.status == "PASS"


def test_check_env_fails_for_invalid_env() -> None:
    result = check_env("invalid")

    assert result.status == "FAIL"
