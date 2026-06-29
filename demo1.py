from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import List

from safe_tool.analysis import build_playbook_analysis, parse_ansible_failures, static_risk_scan
from safe_tool.checks import check_env, check_inventory_exists, check_playbook_exists, check_prod_guard
from safe_tool.config import get_risk_rules, get_settings, load_config, masked_config
from safe_tool.engine import build_ansible_command, run_ansible_validation, run_command
from safe_tool.models import CheckResult
from safe_tool.output import print_decision_analysis, print_line, print_result, summarize_results, write_json_report


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parent

    parser = argparse.ArgumentParser(
        description="Comprehensive safe-tool demo: config, analysis, checks, command build, optional execute, and CLI showcase",
    )
    parser.add_argument("--playbook", default=str(repo_root / "demo.yml"), help="path to playbook")
    parser.add_argument("--inventory", default=str(repo_root / "inventory.ini"), help="path to inventory")
    parser.add_argument("--config", default=str(repo_root / "config.yaml"), help="path to config file")
    parser.add_argument("--env", default="dev", help="environment name")
    parser.add_argument("--engine", default="ansible", help="executor engine name/path")
    parser.add_argument("--limit", help="host limit expression")
    parser.add_argument("-e", "--extra-var", action="append", default=[], help="extra var, can be repeated")
    parser.add_argument("--report", default=str(repo_root / "demo1-report.json"), help="JSON report output path")
    parser.add_argument("--timeout", type=int, default=120, help="execution timeout seconds")

    parser.add_argument("--run-exec", action="store_true", help="actually run ansible command")
    parser.add_argument("--apply", action="store_true", help="when --run-exec is set, run in apply mode")
    parser.add_argument("--confirm", help="required value PROD for production apply")
    parser.add_argument("--cli-demo", action="store_true", help="also run a short CLI subprocess demo")

    return parser.parse_args()


def print_header(title: str) -> None:
    print_line()
    print_line("=" * 78)
    print_line(title)
    print_line("=" * 78)


def run_preflight(args: argparse.Namespace, risk_rules: dict) -> List[CheckResult]:
    checks: List[CheckResult] = []
    checks.append(check_playbook_exists(args.playbook))
    checks.append(check_inventory_exists(args.inventory))
    checks.append(check_env(args.env))

    if any(item.status == "FAIL" for item in checks):
        return checks

    checks.extend(static_risk_scan(args.playbook, risk_rules))
    checks.extend(
        run_ansible_validation(
            playbook=args.playbook,
            inventory=args.inventory,
            limit=args.limit,
            env=args.env,
            extra_vars=args.extra_var,
            engine=args.engine,
        )
    )
    return checks


def maybe_execute(args: argparse.Namespace) -> int:
    print_header("5) Execution Command (optional)")

    mode = "apply" if args.apply else "dry-run"

    guard = check_prod_guard(args.env, args.apply, args.confirm)
    print_result(guard)
    if guard.status == "FAIL":
        return 1

    command = build_ansible_command(
        engine=args.engine,
        playbook=args.playbook,
        inventory=args.inventory,
        limit=args.limit,
        env=args.env,
        extra_vars=args.extra_var,
        mode=mode,
    )

    print_line("Planned command:")
    print_line(" ".join(command))

    if not args.run_exec:
        print_line("Skipped execution. Use --run-exec to run this command.")
        return 0

    result = run_command(command, timeout=args.timeout)

    if result.stdout:
        print_line("\n--- stdout ---")
        print(result.stdout, end="")
    if result.stderr:
        print_line("\n--- stderr ---")
        print(result.stderr, end="")

    if result.exit_code == 0:
        print_line("\nExecution succeeded.")
        return 0

    print_line(f"\nExecution failed with exit code: {result.exit_code}")
    failed_tasks, failed_hosts, fatal_lines = parse_ansible_failures((result.stdout or "") + "\n" + (result.stderr or ""))

    print_line(f"failed_tasks: {len(failed_tasks)}")
    for task in failed_tasks:
        print_line(f"- {task}")

    print_line(f"failed_hosts: {len(failed_hosts)}")
    for host in failed_hosts:
        print_line(f"- {host}")

    if fatal_lines:
        print_line("fatal_lines:")
        for line in fatal_lines:
            print_line(f"- {line}")

    return result.exit_code


def run_cli_showcase(repo_root: Path, args: argparse.Namespace) -> None:
    print_header("6) CLI Subprocess Showcase")

    commands = [
        [sys.executable, str(repo_root / "safe.py"), "doctor"],
        [sys.executable, str(repo_root / "safe.py"), "inspect", args.playbook, "--config", args.config],
        [
            sys.executable,
            str(repo_root / "safe.py"),
            "check",
            args.playbook,
            "-i",
            args.inventory,
            "--env",
            args.env,
            "--config",
            args.config,
        ],
    ]

    for cmd in commands:
        print_line(f"$ {' '.join(cmd)}")
        proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if proc.stdout:
            print(proc.stdout, end="")
        if proc.stderr:
            print(proc.stderr, end="")
        print_line(f"[exit={proc.returncode}]")
        print_line("-" * 78)


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parent

    print_header("1) Load Config")
    config = load_config(args.config)
    print(masked_config(config))

    risk_rules = get_risk_rules(config)
    settings = get_settings(config)
    print_line(f"Loaded settings: {settings}")

    print_header("2) Static Analysis")
    analysis = build_playbook_analysis(args.playbook, risk_rules)
    print_decision_analysis(analysis)

    print_header("3) Preflight Checks")
    checks = run_preflight(args, risk_rules)
    for item in checks:
        print_result(item)

    print_header("4) Check Summary + Report")
    check_exit = summarize_results(checks)
    write_json_report(checks, args.report)

    exec_exit = maybe_execute(args)

    if args.cli_demo:
        run_cli_showcase(repo_root, args)

    print_header("Done")
    print_line(f"Report path: {args.report}")
    print_line(f"Check exit: {check_exit}")
    print_line(f"Execution exit: {exec_exit}")

    # Keep demo friendly: if checks failed but execution was skipped, still return check status.
    return exec_exit if args.run_exec else check_exit


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Interrupted by user.")
        raise SystemExit(130)
