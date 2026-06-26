from __future__ import annotations

from pathlib import Path

from safe_tool.agent.deepseek import SemanticGoalHints
from safe_tool.agent.planner import build_goal_plan
from safe_tool.agent.policy import evaluate_execution_policy


def test_goal_plan_infers_playbook_and_env_and_defaults_to_dry_run() -> None:
    plan = build_goal_plan(
        goal="安全发布 demo.yml 到 dev",
        args_playbook=None,
        args_inventory=None,
        args_env=None,
        args_limit=None,
        extra_vars=[],
        explicit_apply=None,
        default_env="test",
    )

    assert plan.playbook == "demo.yml"
    assert plan.env == "dev"
    assert plan.apply is True
    assert plan.confidence > 0.5
    assert plan.missing_fields == []


def test_goal_plan_accepts_explicit_apply() -> None:
    plan = build_goal_plan(
        goal="安全发布 demo.yml 到 dev",
        args_playbook=None,
        args_inventory=None,
        args_env=None,
        args_limit=None,
        extra_vars=[],
        explicit_apply=True,
        default_env="test",
    )

    assert plan.apply is True


def test_goal_plan_dry_run_hint_overrides_apply_hint() -> None:
    plan = build_goal_plan(
        goal="只检查 demo.yml 到 prod",
        args_playbook=None,
        args_inventory=None,
        args_env=None,
        args_limit=None,
        extra_vars=[],
        explicit_apply=None,
        default_env="dev",
    )

    assert plan.playbook == "demo.yml"
    assert plan.env == "prod"
    assert plan.apply is False


def test_goal_plan_marks_missing_playbook_and_lists_candidates(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "a.yml").write_text("- hosts: all\n", encoding="utf-8")
    (tmp_path / "b.yml").write_text("- hosts: all\n", encoding="utf-8")

    plan = build_goal_plan(
        goal="帮我发布到dev",
        args_playbook=None,
        args_inventory=None,
        args_env=None,
        args_limit=None,
        extra_vars=[],
        explicit_apply=None,
        default_env="dev",
    )

    assert plan.playbook is None
    assert "playbook" in plan.missing_fields
    assert len(plan.playbook_candidates) == 2


def test_goal_plan_auto_selects_single_inventory_candidate(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "demo.yml").write_text("- hosts: all\n", encoding="utf-8")
    (tmp_path / "inventory.ini").write_text("[all]\nlocalhost\n", encoding="utf-8")

    plan = build_goal_plan(
        goal="只检查 demo.yml",
        args_playbook=None,
        args_inventory=None,
        args_env=None,
        args_limit=None,
        extra_vars=[],
        explicit_apply=None,
        default_env="dev",
    )

    assert plan.inventory == "inventory.ini"


def test_goal_plan_uses_semantic_hints_when_goal_is_implicit(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "deploy.yml").write_text("- hosts: web\n", encoding="utf-8")
    (tmp_path / "inventory.ini").write_text("[web]\nlocalhost\n", encoding="utf-8")

    hints = SemanticGoalHints(
        playbook="deploy.yml",
        inventory="inventory.ini",
        env="stage",
        limit="web[0]",
        extra_vars=["version=1.2.3"],
        apply=True,
        confidence=0.9,
        notes=["goal implies staged release"],
    )

    plan = build_goal_plan(
        goal="帮我把新版本发到预发的一台机器上",
        args_playbook=None,
        args_inventory=None,
        args_env=None,
        args_limit=None,
        extra_vars=[],
        explicit_apply=None,
        default_env="dev",
        semantic_hints=hints,
    )

    assert plan.playbook == "deploy.yml"
    assert plan.inventory == "inventory.ini"
    assert plan.env == "stage"
    assert plan.limit == "web[0]"
    assert plan.extra_vars == ["version=1.2.3"]
    assert plan.apply is True
    assert plan.confidence >= 0.8


def test_policy_allows_dry_run_without_approval() -> None:
    allowed, reasons = evaluate_execution_policy(
        env="prod",
        apply=False,
        overall_risk="HIGH",
        plan_confidence=0.1,
        min_goal_confidence_to_apply=0.75,
        require_prod_confirm=True,
        confirm=None,
        approved=False,
    )

    assert allowed is True
    assert reasons == ["dry-run mode; approval not required"]


def test_policy_blocks_prod_apply_without_confirm() -> None:
    allowed, reasons = evaluate_execution_policy(
        env="prod",
        apply=True,
        overall_risk="HIGH",
        plan_confidence=0.9,
        min_goal_confidence_to_apply=0.75,
        require_prod_confirm=True,
        confirm=None,
        approved=True,
    )

    assert allowed is False
    assert "production apply requires --confirm PROD" in reasons


def test_policy_blocks_apply_when_plan_confidence_too_low() -> None:
    allowed, reasons = evaluate_execution_policy(
        env="dev",
        apply=True,
        overall_risk="LOW",
        plan_confidence=0.3,
        min_goal_confidence_to_apply=0.75,
        require_prod_confirm=True,
        confirm=None,
        approved=True,
    )

    assert allowed is False
    assert any("below threshold" in reason for reason in reasons)
