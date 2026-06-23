#!/usr/bin/env python3
"""
safe.py - Production-style safety CLI for Ansible-compatible infrastructure operations.

Purpose:
  Provide a safety gate in front of Ansible execution.
  The tool performs static inspection, preflight validation, dry-run execution,
  failure-log parsing, and decision-oriented risk output.

Commands:
  safe doctor
      Check local toolchain dependencies.

  safe inspect <playbook>
      Inspect playbook structure, hosts, tasks, modules, and task-level risk.

  safe check <playbook>
      Run preflight checks without applying changes.
      Includes local validation, static risk scan, ansible syntax-check,
      host listing, and task listing.

  safe run <playbook>
      Run checks first, print decision analysis, then dry-run by default.
      Use --apply to actually apply changes.
      Production apply requires --confirm PROD.

  safe debug <logfile>
      Parse Ansible output/log file and summarize failed tasks, failed hosts,
      and fatal lines.

Execution engine:
  Default engine is upstream Ansible through ansible-playbook.
  Later this can be adapted to DWAnsible by replacing the executor adapter.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


VALID_ENVS = {"dev", "test", "stage", "staging", "prod", "production"}
PROD_NAMES = {"prod", "production"}

TASK_RESERVED_KEYS = {
    "name",
    "when",
    "tags",
    "register",
    "become",
    "become_user",
    "become_method",
    "vars",
    "loop",
    "with_items",
    "with_dict",
    "with_fileglob",
    "with_nested",
    "delegate_to",
    "ignore_errors",
    "changed_when",
    "failed_when",
    "notify",
    "environment",
    "args",
    "retries",
    "delay",
    "until",
    "block",
    "rescue",
    "always",
    "check_mode",
    "diff",
}

RISK_MODULES: Dict[str, Dict[str, str]] = {
    "shell": {
        "risk": "HIGH",
        "reason": "runs arbitrary shell commands and may change system state",
        "recommendation": "review command content carefully and run with --limit first",
    },
    "raw": {
        "risk": "HIGH",
        "reason": "runs raw commands without normal module safety abstractions",
        "recommendation": "avoid production execution without manual review",
    },
    "script": {
        "risk": "HIGH",
        "reason": "runs external scripts whose behavior may not be visible in the playbook",
        "recommendation": "review script content before execution",
    },
    "service": {
        "risk": "HIGH",
        "reason": "may start, stop, or restart services and affect availability",
        "recommendation": "avoid full rollout; use --limit or staged rollout",
    },
    "systemd": {
        "risk": "HIGH",
        "reason": "may alter service state through systemd",
        "recommendation": "use --limit and validate service impact before apply",
    },
    "reboot": {
        "risk": "HIGH",
        "reason": "will reboot target machines",
        "recommendation": "run in controlled batches and verify redundancy",
    },
    "mount": {
        "risk": "HIGH",
        "reason": "may change filesystem mount state",
        "recommendation": "validate target paths and rollback plan before apply",
    },
    "command": {
        "risk": "MEDIUM",
        "reason": "runs commands directly on target hosts",
        "recommendation": "review command idempotency and dry-run behavior",
    },
    "copy": {
        "risk": "MEDIUM",
        "reason": "modifies files on target hosts",
        "recommendation": "review --diff output before apply",
    },
    "template": {
        "risk": "MEDIUM",
        "reason": "renders and writes configuration files",
        "recommendation": "review generated diff and service reload impact",
    },
    "file": {
        "risk": "MEDIUM",
        "reason": "changes files, directories, ownership, or permissions",
        "recommendation": "verify paths and ownership before apply",
    },
    "lineinfile": {
        "risk": "MEDIUM",
        "reason": "edits files in-place",
        "recommendation": "review diff output before apply",
    },
    "replace": {
        "risk": "MEDIUM",
        "reason": "performs pattern-based file replacement",
        "recommendation": "validate regex and review diff output",
    },
    "user": {
        "risk": "MEDIUM",
        "reason": "changes user accounts or attributes",
        "recommendation": "confirm account scope before apply",
    },
    "group": {
        "risk": "MEDIUM",
        "reason": "changes group accounts or membership-related state",
        "recommendation": "confirm group scope before apply",
    },
    "package": {
        "risk": "MEDIUM",
        "reason": "installs, removes, or upgrades packages",
        "recommendation": "review package changes and service impact",
    },
    "apt": {
        "risk": "MEDIUM",
        "reason": "changes packages on Debian/Ubuntu hosts",
        "recommendation": "review package changes before apply",
    },
    "yum": {
        "risk": "MEDIUM",
        "reason": "changes packages on Yum-based hosts",
        "recommendation": "review package changes before apply",
    },
    "dnf": {
        "risk": "MEDIUM",
        "reason": "changes packages on DNF-based hosts",
        "recommendation": "review package changes before apply",
    },
    "pip": {
        "risk": "MEDIUM",
        "reason": "changes Python packages on target hosts",
        "recommendation": "confirm virtualenv or system package scope",
    },
    "git": {
        "risk": "MEDIUM",
        "reason": "changes repository content on target hosts",
        "recommendation": "confirm branch, revision, and target directory",
    },
    "unarchive": {
        "risk": "MEDIUM",
        "reason": "extracts archive content to target paths",
        "recommendation": "verify destination path and overwrite behavior",
    },
    "cron": {
        "risk": "MEDIUM",
        "reason": "changes scheduled jobs",
        "recommendation": "confirm schedule and command content",
    },
    "debug": {
        "risk": "LOW",
        "reason": "prints information only",
        "recommendation": "safe to inspect; ensure no secrets are printed",
    },
    "set_fact": {
        "risk": "LOW",
        "reason": "sets Ansible facts during execution",
        "recommendation": "safe unless used to drive later risky tasks",
    },
}

RISK_ORDER = {"UNKNOWN": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3}


@dataclass
class CheckResult:
    name: str
    status: str
    message: str
    remediation: Optional[str] = None


@dataclass
class CommandResult:
    exit_code: int
    stdout: str
    stderr: str
    command: List[str]


@dataclass
class TaskAnalysis:
    play_index: int
    play_name: str
    hosts: str
    task_index: int
    task_name: str
    module: Optional[str]
    normalized_module: Optional[str]
    risk: str
    reason: str
    recommendation: str


@dataclass
class PlaybookAnalysis:
    playbook: str
    tasks: List[TaskAnalysis]
    overall_risk: str
    recommendations: List[str]


def print_line(message: str = "") -> None:
    print(message)


def print_result(result: CheckResult) -> None:
    prefix = {"PASS": "[PASS]", "WARN": "[WARN]", "FAIL": "[FAIL]"}.get(result.status, "[INFO]")
    print_line(f"{prefix} {result.name}: {result.message}")
    if result.remediation:
        print_line(f"       remediation: {result.remediation}")


def run_command(command: List[str], timeout: int = 120) -> CommandResult:
    try:
        proc = subprocess.run(
            command,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
        return CommandResult(proc.returncode, proc.stdout, proc.stderr, command)
    except FileNotFoundError:
        return CommandResult(127, "", f"command not found: {command[0]}", command)
    except subprocess.TimeoutExpired as exc:
        return CommandResult(124, exc.stdout or "", exc.stderr or "timeout", command)


def load_yaml_file(path: str) -> Any:
    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError("PyYAML is required. Install it with: python3 -m pip install pyyaml") from exc

    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def resolve_engine(engine: str) -> Optional[str]:
    if engine == "ansible":
        return shutil.which("ansible-playbook")
    return shutil.which(engine) or engine


def build_ansible_command(
    engine: str,
    playbook: str,
    inventory: Optional[str],
    limit: Optional[str],
    env: Optional[str],
    extra_vars: List[str],
    mode: str,
) -> List[str]:
    resolved = resolve_engine(engine)
    if not resolved:
        resolved = "ansible-playbook"

    cmd = [resolved]

    if mode == "syntax":
        cmd += ["--syntax-check"]
    elif mode == "list-hosts":
        cmd += ["--list-hosts"]
    elif mode == "list-tasks":
        cmd += ["--list-tasks"]
    elif mode == "dry-run":
        cmd += ["--check", "--diff"]
    elif mode == "apply":
        pass
    else:
        raise ValueError(f"unknown mode: {mode}")

    if inventory:
        cmd += ["-i", inventory]
    if limit:
        cmd += ["--limit", limit]
    if env:
        cmd += ["-e", f"env={env}"]
    for item in extra_vars:
        cmd += ["-e", item]

    cmd.append(playbook)
    return cmd


def check_playbook_exists(playbook: str) -> CheckResult:
    path = Path(playbook)
    if path.exists() and path.is_file():
        return CheckResult("playbook_exists", "PASS", f"found {path}")
    return CheckResult("playbook_exists", "FAIL", f"playbook not found: {playbook}", "pass a real playbook path")


def check_inventory_exists(inventory: Optional[str]) -> CheckResult:
    if not inventory:
        return CheckResult("inventory", "WARN", "no inventory provided", "use -i inventory.ini for meaningful host checks")
    path = Path(inventory)
    if path.exists():
        return CheckResult("inventory", "PASS", f"found {path}")
    return CheckResult("inventory", "FAIL", f"inventory not found: {inventory}", "verify -i path")


def check_env(env: Optional[str]) -> CheckResult:
    if not env:
        return CheckResult("env", "WARN", "no env provided", "use --env dev/test/prod when playbook behavior depends on env")
    if env in VALID_ENVS:
        return CheckResult("env", "PASS", f"env={env}")
    return CheckResult("env", "FAIL", f"invalid env: {env}", f"allowed: {', '.join(sorted(VALID_ENVS))}")


def check_prod_guard(env: Optional[str], apply: bool, confirm: Optional[str]) -> CheckResult:
    if env not in PROD_NAMES:
        return CheckResult("prod_guard", "PASS", "not a production environment")
    if not apply:
        return CheckResult("prod_guard", "PASS", "production dry-run only")
    if confirm == "PROD":
        return CheckResult("prod_guard", "PASS", "production apply explicitly confirmed")
    return CheckResult("prod_guard", "FAIL", "production apply is blocked", "add --confirm PROD only after review")


def parse_host_count(output: str) -> Optional[int]:
    match = re.search(r"hosts\s*\((\d+)\)", output)
    if match:
        return int(match.group(1))
    return None


def run_ansible_validation(
    playbook: str,
    inventory: Optional[str],
    limit: Optional[str],
    env: Optional[str],
    extra_vars: List[str],
    engine: str,
) -> List[CheckResult]:
    results: List[CheckResult] = []

    syntax_cmd = build_ansible_command(engine, playbook, inventory, limit, env, extra_vars, "syntax")
    syntax = run_command(syntax_cmd)
    if syntax.exit_code == 0:
        results.append(CheckResult("ansible_syntax", "PASS", "syntax check passed"))
    elif syntax.exit_code == 127:
        results.append(CheckResult("ansible_syntax", "WARN", "ansible-playbook not found; skipped syntax check", "install ansible or pass --engine to an existing executor"))
    else:
        source = syntax.stderr or syntax.stdout
        detail = source.strip().splitlines()[-1] if source.strip() else "syntax check failed"
        results.append(CheckResult("ansible_syntax", "FAIL", detail, "fix playbook syntax before running"))

    if inventory:
        hosts_cmd = build_ansible_command(engine, playbook, inventory, limit, env, extra_vars, "list-hosts")
        hosts = run_command(hosts_cmd)
        if hosts.exit_code == 0:
            host_count = parse_host_count(hosts.stdout)
            msg = "host listing succeeded"
            if host_count is not None:
                msg += f"; hosts matched={host_count}"
            results.append(CheckResult("ansible_list_hosts", "PASS", msg))
        elif hosts.exit_code == 127:
            results.append(CheckResult("ansible_list_hosts", "WARN", "ansible-playbook not found; skipped host listing"))
        else:
            source = hosts.stderr or hosts.stdout
            detail = source.strip().splitlines()[-1] if source.strip() else "host listing failed"
            results.append(CheckResult("ansible_list_hosts", "FAIL", detail, "verify inventory, --limit and host pattern"))

        tasks_cmd = build_ansible_command(engine, playbook, inventory, limit, env, extra_vars, "list-tasks")
        tasks = run_command(tasks_cmd)
        if tasks.exit_code == 0:
            results.append(CheckResult("ansible_list_tasks", "PASS", "task listing succeeded"))
        elif tasks.exit_code == 127:
            results.append(CheckResult("ansible_list_tasks", "WARN", "ansible-playbook not found; skipped task listing"))
        else:
            source = tasks.stderr or tasks.stdout
            detail = source.strip().splitlines()[-1] if source.strip() else "task listing failed"
            results.append(CheckResult("ansible_list_tasks", "WARN", detail, "inspect playbook manually if task listing is unavailable"))

    return results


def normalize_module_name(module: Optional[str]) -> Optional[str]:
    if not module:
        return None
    return module.split(".")[-1]


def find_task_module(task: Dict[str, Any]) -> Optional[str]:
    for key, value in task.items():
        if key in TASK_RESERVED_KEYS:
            continue
        if isinstance(value, (dict, str, list, bool, int, float, type(None))):
            return key
    return None


def get_module_risk(module: Optional[str]) -> Tuple[str, str, str]:
    short_name = normalize_module_name(module)
    if not short_name:
        return "UNKNOWN", "could not detect module", "review task manually"

    rule = RISK_MODULES.get(short_name)
    if rule:
        return rule["risk"], rule["reason"], rule["recommendation"]

    return "LOW", "module is not marked as state-changing by current rules", "safe to inspect; still review before production apply"


def build_playbook_analysis(playbook: str) -> PlaybookAnalysis:
    data = load_yaml_file(playbook)
    if data is None:
        data = []
    if not isinstance(data, list):
        raise ValueError("invalid playbook format: expected a list of plays")

    tasks: List[TaskAnalysis] = []
    recommendations: List[str] = []
    max_risk = "LOW"

    for play_index, play in enumerate(data, start=1):
        if not isinstance(play, dict):
            continue

        play_name = str(play.get("name", ""))
        hosts = str(play.get("hosts", ""))
        play_tasks = play.get("tasks", []) or []

        if hosts == "all":
            recommendations.append("play targets all hosts; use --limit or staged rollout for production-like environments")
            if RISK_ORDER["HIGH"] > RISK_ORDER[max_risk]:
                max_risk = "HIGH"

        for task_index, task in enumerate(play_tasks, start=1):
            if not isinstance(task, dict):
                continue

            task_name = str(task.get("name", ""))
            module = find_task_module(task)
            normalized = normalize_module_name(module)
            risk, reason, recommendation = get_module_risk(module)

            if hosts == "all" and risk in {"MEDIUM", "HIGH"}:
                risk = "HIGH"
                reason = reason + "; task targets all hosts"
                recommendation = "use --limit or staged rollout to reduce blast radius"

            if RISK_ORDER[risk] > RISK_ORDER[max_risk]:
                max_risk = risk

            if recommendation not in recommendations:
                recommendations.append(recommendation)

            tasks.append(
                TaskAnalysis(
                    play_index=play_index,
                    play_name=play_name,
                    hosts=hosts,
                    task_index=task_index,
                    task_name=task_name,
                    module=module,
                    normalized_module=normalized,
                    risk=risk,
                    reason=reason,
                    recommendation=recommendation,
                )
            )

    return PlaybookAnalysis(playbook=playbook, tasks=tasks, overall_risk=max_risk, recommendations=recommendations)


def static_risk_scan(playbook: str) -> List[CheckResult]:
    path = Path(playbook)
    if not path.exists():
        return []

    results: List[CheckResult] = []
    try:
        analysis = build_playbook_analysis(playbook)
    except Exception as exc:
        return [CheckResult("risk_scan", "WARN", f"static risk scan skipped: {exc}", "run safe inspect for details")]

    risky_modules = sorted({t.normalized_module for t in analysis.tasks if t.risk in {"MEDIUM", "HIGH"} and t.normalized_module})

    if risky_modules:
        results.append(CheckResult("risk_scan", "WARN", f"potentially state-changing modules detected: {', '.join(risky_modules)}", "review tasks and run dry-run before apply"))
    else:
        results.append(CheckResult("risk_scan", "PASS", "no high-risk module hints detected by static analysis"))

    if any(t.hosts == "all" for t in analysis.tasks):
        results.append(CheckResult("hosts_scope", "WARN", "playbook targets hosts: all", "use --limit or narrower host groups for safer rollout"))

    return results


def summarize_results(results: List[CheckResult]) -> int:
    failures = [r for r in results if r.status == "FAIL"]
    warnings = [r for r in results if r.status == "WARN"]
    passes = [r for r in results if r.status == "PASS"]
    print_line()
    print_line(f"Summary: {len(failures)} failed, {len(warnings)} warning(s), {len(passes)} passed")
    return 1 if failures else 0


def write_json_report(results: List[CheckResult], path: Optional[str]) -> None:
    if not path:
        return
    data = [asdict(r) for r in results]
    Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")
    print_line(f"Report written: {path}")


def print_decision_analysis(analysis: PlaybookAnalysis) -> None:
    print_line("Decision Analysis")
    print_line(f"Playbook: {analysis.playbook}")
    print_line(f"Overall Risk: {analysis.overall_risk}")
    print_line()

    if not analysis.tasks:
        print_line("No tasks detected.")
        print_line()
        return

    for task in analysis.tasks:
        print_line(f"- Play {task.play_index}: {task.play_name}")
        print_line(f"  Hosts: {task.hosts}")
        print_line(f"  Task {task.task_index}: {task.task_name}")
        print_line(f"  Module: {task.module or 'unknown'}")
        print_line(f"  Risk: {task.risk}")
        print_line(f"  Reason: {task.reason}")
        print_line(f"  Recommendation: {task.recommendation}")
        print_line()

    if analysis.recommendations:
        print_line("Global Recommendations:")
        for item in analysis.recommendations:
            print_line(f"- {item}")
        print_line()


def cmd_doctor(args: argparse.Namespace) -> int:
    checks: List[CheckResult] = []
    checks.append(CheckResult("python", "PASS", sys.executable))

    ansible = shutil.which("ansible-playbook")
    checks.append(CheckResult("ansible-playbook", "PASS" if ansible else "WARN", ansible or "not found", "install ansible or configure --engine" if not ansible else None))

    try:
        import yaml  # noqa: F401
        checks.append(CheckResult("pyyaml", "PASS", "available"))
    except ImportError:
        checks.append(CheckResult("pyyaml", "WARN", "not installed", "install with: python3 -m pip install pyyaml"))

    for check in checks:
        print_result(check)

    return summarize_results(checks)


def cmd_inspect(args: argparse.Namespace) -> int:
    path = Path(args.playbook)
    if not path.exists():
        print_line(f"[FAIL] playbook not found: {args.playbook}")
        return 1

    try:
        analysis = build_playbook_analysis(args.playbook)
    except Exception as exc:
        print_line(f"[FAIL] failed to inspect playbook: {exc}")
        return 1

    print_line("Playbook Inspection")
    print_line(f"File: {args.playbook}")
    print_line()
    print_decision_analysis(analysis)
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    results: List[CheckResult] = []
    results.append(check_playbook_exists(args.playbook))
    results.append(check_inventory_exists(args.inventory))
    results.append(check_env(args.env))

    if any(r.status == "FAIL" for r in results):
        for result in results:
            print_result(result)
        write_json_report(results, args.report)
        return summarize_results(results)

    results.extend(static_risk_scan(args.playbook))
    results.extend(run_ansible_validation(args.playbook, args.inventory, args.limit, args.env, args.extra_var, args.engine))

    for result in results:
        print_result(result)

    write_json_report(results, args.report)
    return summarize_results(results)


def cmd_run(args: argparse.Namespace) -> int:
    check_args = argparse.Namespace(**vars(args))
    check_exit = cmd_check(check_args)
    if check_exit != 0:
        print_line("Run blocked because checks failed.")
        return check_exit

    try:
        analysis = build_playbook_analysis(args.playbook)
        print_line()
        print_decision_analysis(analysis)
    except Exception as exc:
        print_line(f"[WARN] decision analysis unavailable: {exc}")

    guard = check_prod_guard(args.env, args.apply, args.confirm)
    print_result(guard)
    if guard.status == "FAIL":
        return 1

    mode = "apply" if args.apply else "dry-run"
    cmd = build_ansible_command(args.engine, args.playbook, args.inventory, args.limit, args.env, args.extra_var, mode)

    print_line()
    print_line("Execution command:")
    print_line(" ".join(cmd))
    print_line()

    result = run_command(cmd, timeout=args.timeout)

    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)

    if result.exit_code == 0:
        print_line("Execution finished successfully.")
    else:
        print_line(f"Execution failed with exit code {result.exit_code}.")

    return result.exit_code


def parse_ansible_failures(text: str) -> Tuple[List[str], List[str], List[str]]:
    failed_tasks: List[str] = []
    failed_hosts: List[str] = []
    fatal_lines: List[str] = []
    current_task = None

    for line in text.splitlines():
        task_match = re.search(r"TASK \[(.*?)\]", line)
        if task_match:
            current_task = task_match.group(1)

        if "fatal:" in line or "FAILED!" in line:
            fatal_lines.append(line.strip())
            host_match = re.search(r"fatal: \[([^\]]+)\]", line)
            if host_match:
                failed_hosts.append(host_match.group(1))
            if current_task:
                failed_tasks.append(current_task)

    return sorted(set(failed_tasks)), sorted(set(failed_hosts)), fatal_lines[:20]


def cmd_debug(args: argparse.Namespace) -> int:
    path = Path(args.logfile)
    if not path.exists():
        print_line(f"[FAIL] logfile not found: {args.logfile}")
        return 1

    text = path.read_text(errors="ignore")
    tasks, hosts, lines = parse_ansible_failures(text)

    print_line("Failure Summary")
    print_line(f"failed_tasks: {len(tasks)}")
    for item in tasks:
        print_line(f"- {item}")

    print_line(f"failed_hosts: {len(hosts)}")
    for item in hosts:
        print_line(f"- {item}")

    if lines:
        print_line("fatal_lines:")
        for line in lines:
            print_line(f"- {line}")
    else:
        print_line("No fatal/FAILED lines detected by parser.")

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="safe", description="Safety CLI for Ansible-compatible operations")
    parser.add_argument("--engine", default=os.environ.get("SAFE_ENGINE", "ansible"), help="executor engine: ansible or a command name/path; default: ansible")

    sub = parser.add_subparsers(dest="command", required=True)

    doctor = sub.add_parser("doctor", help="check local dependencies")
    doctor.set_defaults(func=cmd_doctor)

    def add_common(p: argparse.ArgumentParser) -> None:
        p.add_argument("playbook", help="path to playbook")
        p.add_argument("-i", "--inventory", help="inventory file/path")
        p.add_argument("--limit", help="limit target hosts")
        p.add_argument("--env", help="environment name")
        p.add_argument("-e", "--extra-var", action="append", default=[], help="extra variable, can be repeated")
        p.add_argument("--report", help="write JSON report")

    inspect_cmd = sub.add_parser("inspect", help="inspect playbook structure and risk")
    inspect_cmd.add_argument("playbook", help="path to playbook")
    inspect_cmd.set_defaults(func=cmd_inspect)

    check = sub.add_parser("check", help="run preflight checks only")
    add_common(check)
    check.set_defaults(func=cmd_check)

    run = sub.add_parser("run", help="check first, then dry-run by default; use --apply to change systems")
    add_common(run)
    run.add_argument("--apply", action="store_true", help="actually apply changes; default is dry-run")
    run.add_argument("--confirm", help="required value PROD when applying to prod")
    run.add_argument("--timeout", type=int, default=600, help="execution timeout seconds")
    run.set_defaults(func=cmd_run)

    debug = sub.add_parser("debug", help="parse ansible output/log file")
    debug.add_argument("logfile", help="path to ansible output log")
    debug.set_defaults(func=cmd_debug)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
