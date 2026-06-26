from __future__ import annotations

import argparse
import importlib
import importlib.util
import os
import shutil
import sys
from pathlib import Path
from typing import List

from .analysis import build_playbook_analysis, parse_ansible_failures, static_risk_scan
from .checks import check_env, check_inventory_exists, check_playbook_exists, check_prod_guard
from .config import default_config, default_config_path, get_api_config, get_risk_rules, get_settings, load_config, masked_config, write_config, write_default_config
from .engine import build_ansible_command, run_ansible_validation, run_command
from .models import CheckResult
from .output import print_decision_analysis, print_line, print_result, summarize_results, write_json_report
from .agent.orchestrator import run_goal_workflow


def load_runtime_config(args: argparse.Namespace) -> dict:
    return load_config(getattr(args, "config", None))


def cmd_doctor(args: argparse.Namespace) -> int:
    checks: List[CheckResult] = []
    checks.append(CheckResult("python", "PASS", sys.executable))

    ansible = shutil.which("ansible-playbook")
    checks.append(CheckResult("ansible-playbook", "PASS" if ansible else "WARN", ansible or "not found", "install ansible or configure --engine" if not ansible else None))

    if importlib.util.find_spec("yaml"):
        checks.append(CheckResult("pyyaml", "PASS", "available"))
    else:
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
        config = load_runtime_config(args)
        analysis = build_playbook_analysis(args.playbook, get_risk_rules(config))
    except Exception as exc:
        print_line(f"[FAIL] failed to inspect playbook: {exc}")
        return 1

    print_line("Playbook Inspection")
    print_line(f"File: {args.playbook}")
    print_line()
    print_decision_analysis(analysis)
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    try:
        config = load_runtime_config(args)
        risk_rules = get_risk_rules(config)
        settings = get_settings(config)
    except Exception as exc:
        print_line(f"[FAIL] failed to load configuration: {exc}")
        return 1

    engine = args.engine or settings["default_engine"]
    results: List[CheckResult] = []
    results.append(check_playbook_exists(args.playbook))
    results.append(check_inventory_exists(args.inventory))
    results.append(check_env(args.env))

    if any(r.status == "FAIL" for r in results):
        for result in results:
            print_result(result)
        write_json_report(results, args.report)
        return summarize_results(results)

    results.extend(static_risk_scan(args.playbook, risk_rules))
    results.extend(run_ansible_validation(args.playbook, args.inventory, args.limit, args.env, args.extra_var, engine))

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
        config = load_runtime_config(args)
        risk_rules = get_risk_rules(config)
        settings = get_settings(config)
        engine = args.engine or settings["default_engine"]
        analysis = build_playbook_analysis(args.playbook, risk_rules)
        print_line()
        print_decision_analysis(analysis)
    except Exception as exc:
        print_line(f"[WARN] decision analysis unavailable: {exc}")
        engine = args.engine

    guard = check_prod_guard(args.env, args.apply, args.confirm)
    print_result(guard)
    if guard.status == "FAIL":
        return 1

    mode = "apply" if args.apply else "dry-run"
    cmd = build_ansible_command(engine, args.playbook, args.inventory, args.limit, args.env, args.extra_var, mode)

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


def cmd_config_show(args: argparse.Namespace) -> int:
    try:
        yaml = importlib.import_module("yaml")
        config = load_runtime_config(args)
    except Exception as exc:
        print_line(f"[FAIL] failed to load configuration: {exc}")
        return 1

    print(yaml.safe_dump(masked_config(config), sort_keys=False), end="")
    return 0


def cmd_config_init(args: argparse.Namespace) -> int:
    path = Path(getattr(args, "config", None)) if getattr(args, "config", None) else default_config_path()
    if path.exists():
        print_line(f"[INFO] configuration already exists: {path}")
        return 0

    try:
        written = write_default_config(str(path))
    except Exception as exc:
        print_line(f"[FAIL] failed to initialize configuration: {exc}")
        return 1

    print_line(f"Configuration written: {written}")
    return 0


def cmd_goal(args: argparse.Namespace) -> int:
    return run_goal_workflow(args)


def _load_writable_config(args: argparse.Namespace) -> tuple[dict, Path]:
    path = Path(getattr(args, "config", None)) if getattr(args, "config", None) else default_config_path()
    if path.exists():
        return load_config(str(path)), path
    if getattr(args, "config", None):
        return default_config(), path
    return load_config(None), path


def cmd_api_set(args: argparse.Namespace) -> int:
    try:
        config, path = _load_writable_config(args)
        api = get_api_config(config)
    except Exception as exc:
        print_line(f"[FAIL] failed to load configuration: {exc}")
        return 1

    api_key = args.api_key
    if args.api_key_env:
        api_key = os.environ.get(args.api_key_env)
        if not api_key:
            print_line(f"[FAIL] environment variable not found or empty: {args.api_key_env}")
            return 1

    deepseek = api.get("deepseek", {})
    if not api_key and not deepseek.get("api_key"):
        print_line("[FAIL] DeepSeek API key is required. Use --api-key or --api-key-env.")
        return 1

    if api_key:
        deepseek["api_key"] = api_key
    if args.base_url:
        deepseek["base_url"] = args.base_url
    if args.model:
        deepseek["model"] = args.model
    if args.timeout is not None:
        deepseek["timeout"] = args.timeout

    deepseek["enabled"] = True
    api["provider"] = "deepseek"
    api["deepseek"] = deepseek
    config["api"] = api

    try:
        written = write_config(config, str(path))
    except Exception as exc:
        print_line(f"[FAIL] failed to write configuration: {exc}")
        return 1

    print_line(f"DeepSeek API configured: {written}")
    print_line(f"Model: {deepseek.get('model')}")
    print_line(f"Base URL: {deepseek.get('base_url')}")
    return 0


def cmd_api_show(args: argparse.Namespace) -> int:
    try:
        yaml = importlib.import_module("yaml")
        config = load_runtime_config(args)
        api = masked_config(config).get("api", {})
    except Exception as exc:
        print_line(f"[FAIL] failed to load API configuration: {exc}")
        return 1

    print(yaml.safe_dump(api, sort_keys=False), end="")
    return 0


def cmd_api_disable(args: argparse.Namespace) -> int:
    try:
        config, path = _load_writable_config(args)
        api = get_api_config(config)
        deepseek = api.get("deepseek", {})
    except Exception as exc:
        print_line(f"[FAIL] failed to load configuration: {exc}")
        return 1

    deepseek["enabled"] = False
    api["provider"] = None
    api["deepseek"] = deepseek
    config["api"] = api

    try:
        written = write_config(config, str(path))
    except Exception as exc:
        print_line(f"[FAIL] failed to write configuration: {exc}")
        return 1

    print_line(f"DeepSeek API disabled: {written}")
    return 0
