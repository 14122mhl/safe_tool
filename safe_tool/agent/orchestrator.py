from __future__ import annotations

import argparse
import os
from dataclasses import asdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from ..analysis import build_playbook_analysis, parse_ansible_failures, static_risk_scan
from ..checks import check_env, check_inventory_exists, check_playbook_exists
from ..config import get_api_config, get_risk_rules, get_settings, load_config
from ..engine import build_ansible_command, run_ansible_validation, run_command
from ..models import CheckResult
from ..output import print_decision_analysis, print_line, print_result, summarize_results, write_json_report
from .deepseek import DeepSeekGoalParser, SemanticGoalHints
from .planner import build_goal_plan, discover_candidates
from .policy import evaluate_execution_policy
from .trace import build_run_id, default_log_path, write_trace


def _serialize_checks(items: List[CheckResult]) -> List[Dict[str, Any]]:
    return [asdict(item) for item in items]


def _build_semantic_hints(goal: str, api_config: Dict[str, Any]) -> Tuple[Optional[SemanticGoalHints], List[str]]:
    notes: List[str] = []
    provider = api_config.get("provider")
    deepseek = api_config.get("deepseek", {}) if isinstance(api_config.get("deepseek"), dict) else {}
    if provider != "deepseek" or not deepseek.get("enabled"):
        return None, notes

    api_key = deepseek.get("api_key") or os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        notes.append("DeepSeek parser skipped: missing api key")
        return None, notes

    parser = DeepSeekGoalParser(
        api_key=api_key,
        base_url=str(deepseek.get("base_url") or "https://api.deepseek.com"),
        model=str(deepseek.get("model") or "deepseek-chat"),
        timeout=int(deepseek.get("timeout") or 30),
    )
    try:
        hints = parser.parse_goal(
            goal=goal,
            playbook_candidates=discover_candidates("*.yml") + discover_candidates("*.yaml"),
            inventory_candidates=discover_candidates("*.ini"),
        )
    except Exception as exc:
        notes.append(f"DeepSeek parser unavailable; used local rules: {exc}")
        return None, notes

    notes.append("DeepSeek parser produced semantic hints")
    return hints, notes


def run_goal_workflow(args: argparse.Namespace) -> int:
    started_at = datetime.utcnow().isoformat() + "Z"
    run_id = build_run_id()
    trace: Dict[str, Any] = {
        "run_id": run_id,
        "started_at": started_at,
        "goal": " ".join(args.goal),
        "steps": [],
        "status": "running",
    }

    try:
        config = load_config(getattr(args, "config", None))
        settings = get_settings(config)
        risk_rules = get_risk_rules(config)
        api_config = get_api_config(config)
    except Exception as exc:
        print_line(f"[FAIL] failed to load configuration: {exc}")
        trace["status"] = "failed"
        trace["error"] = str(exc)
        write_trace(trace, getattr(args, "trace_out", None))
        return 1

    goal_text = " ".join(args.goal)
    semantic_hints, semantic_notes = _build_semantic_hints(goal_text, api_config)

    plan = build_goal_plan(
        goal=goal_text,
        args_playbook=args.playbook,
        args_inventory=args.inventory,
        args_env=args.env,
        args_limit=args.limit,
        extra_vars=args.extra_var,
        explicit_apply=args.apply_mode,
        default_env=settings.get("default_env"),
        semantic_hints=semantic_hints,
    )
    plan.notes.extend(semantic_notes)

    trace["plan"] = asdict(plan)
    if semantic_hints:
        trace["semantic_hints"] = asdict(semantic_hints)

    print_line("Agent Plan")
    print_line(f"Goal: {plan.goal}")
    print_line(f"Playbook: {plan.playbook or 'unknown'}")
    print_line(f"Inventory: {plan.inventory or 'not provided'}")
    print_line(f"Env: {plan.env or 'not provided'}")
    print_line(f"Mode: {'apply' if plan.apply else 'dry-run'}")
    print_line(f"Plan confidence: {plan.confidence}")
    if plan.notes:
        print_line("Plan notes:")
        for item in plan.notes:
            print_line(f"- {item}")
    print_line()

    if plan.missing_fields:
        print_line("Agent Clarify")
        print_line("Missing required fields:")
        for field in plan.missing_fields:
            print_line(f"- {field}")
        if "playbook" in plan.missing_fields and plan.playbook_candidates:
            print_line("Playbook candidates:")
            for item in plan.playbook_candidates[:8]:
                print_line(f"- {item}")
        if not plan.inventory and plan.inventory_candidates:
            print_line("Inventory candidates:")
            for item in plan.inventory_candidates[:8]:
                print_line(f"- {item}")
        print_line("Please rerun with explicit flags, for example: --playbook <path> --env <dev|test|stage|prod>")
        trace["status"] = "needs_clarification"
        trace["error"] = "missing required goal fields"
        write_trace(trace, getattr(args, "trace_out", None))
        return 1

    try:
        analysis = build_playbook_analysis(plan.playbook, risk_rules)
    except Exception as exc:
        print_line(f"[FAIL] analysis failed: {exc}")
        trace["status"] = "failed"
        trace["error"] = str(exc)
        write_trace(trace, getattr(args, "trace_out", None))
        return 1

    print_line("Agent Analyze")
    print_decision_analysis(analysis)
    trace["analysis"] = {
        "overall_risk": analysis.overall_risk,
        "task_count": len(analysis.tasks),
        "recommendations": analysis.recommendations,
    }

    checks: List[CheckResult] = [
        check_playbook_exists(plan.playbook),
        check_inventory_exists(plan.inventory),
        check_env(plan.env),
    ]

    if any(item.status == "FAIL" for item in checks):
        for item in checks:
            print_result(item)
        trace["steps"].append({"name": "check", "results": _serialize_checks(checks), "exit_code": 1})
        trace["status"] = "failed"
        write_json_report(checks, args.report)
        write_trace(trace, getattr(args, "trace_out", None))
        return summarize_results(checks)

    checks.extend(static_risk_scan(plan.playbook, risk_rules))
    checks.extend(
        run_ansible_validation(
            playbook=plan.playbook,
            inventory=plan.inventory,
            limit=plan.limit,
            env=plan.env,
            extra_vars=plan.extra_vars,
            engine=args.engine or settings["default_engine"],
        )
    )

    for item in checks:
        print_result(item)

    check_exit = summarize_results(checks)
    trace["steps"].append({"name": "check", "results": _serialize_checks(checks), "exit_code": check_exit})
    write_json_report(checks, args.report)
    if check_exit != 0:
        print_line("Agent blocked: preflight checks failed.")
        trace["status"] = "failed"
        write_trace(trace, getattr(args, "trace_out", None))
        return check_exit

    allowed, reasons = evaluate_execution_policy(
        env=plan.env,
        apply=plan.apply,
        overall_risk=analysis.overall_risk,
        plan_confidence=plan.confidence,
        min_goal_confidence_to_apply=float(settings.get("min_goal_confidence_to_apply", 0.75)),
        require_prod_confirm=bool(settings.get("require_prod_confirm", True)),
        confirm=args.confirm,
        approved=bool(args.approve),
    )
    trace["steps"].append({"name": "approval", "allowed": allowed, "reasons": reasons})

    if not allowed:
        for reason in reasons:
            print_line(f"[FAIL] approval gate: {reason}")
        trace["status"] = "failed"
        write_trace(trace, getattr(args, "trace_out", None))
        return 1

    mode = "apply" if plan.apply else "dry-run"
    command = build_ansible_command(
        engine=args.engine or settings["default_engine"],
        playbook=plan.playbook,
        inventory=plan.inventory,
        limit=plan.limit,
        env=plan.env,
        extra_vars=plan.extra_vars,
        mode=mode,
    )
    print_line()
    print_line("Agent Execute")
    print_line("Execution command:")
    print_line(" ".join(command))
    print_line()

    result = run_command(command, timeout=args.timeout)
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="")

    log_path = default_log_path(run_id)
    combined = (result.stdout or "") + "\n" + (result.stderr or "")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(combined, encoding="utf-8", errors="ignore")

    trace["steps"].append(
        {
            "name": "execute",
            "mode": mode,
            "command": command,
            "exit_code": result.exit_code,
            "log_path": str(log_path),
        }
    )

    if result.exit_code == 0:
        print_line("Agent Verify")
        print_line("Execution finished successfully.")
        trace["status"] = "success"
        trace["finished_at"] = datetime.utcnow().isoformat() + "Z"
        written = write_trace(trace, getattr(args, "trace_out", None))
        print_line(f"Trace written: {written}")
        return 0

    print_line("Agent Verify")
    print_line("Execution failed; parsing failure summary from run log.")
    failed_tasks, failed_hosts, fatal_lines = parse_ansible_failures(combined)

    print_line(f"failed_tasks: {len(failed_tasks)}")
    for item in failed_tasks:
        print_line(f"- {item}")
    print_line(f"failed_hosts: {len(failed_hosts)}")
    for item in failed_hosts:
        print_line(f"- {item}")
    if fatal_lines:
        print_line("fatal_lines:")
        for line in fatal_lines:
            print_line(f"- {line}")

    trace["steps"].append(
        {
            "name": "verify",
            "failed_tasks": failed_tasks,
            "failed_hosts": failed_hosts,
            "fatal_lines": fatal_lines,
        }
    )
    trace["status"] = "failed"
    trace["finished_at"] = datetime.utcnow().isoformat() + "Z"
    written = write_trace(trace, getattr(args, "trace_out", None))
    print_line(f"Trace written: {written}")
    return result.exit_code
