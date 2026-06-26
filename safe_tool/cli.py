from __future__ import annotations

import argparse
import os
from typing import List, Optional

from .commands import cmd_api_disable, cmd_api_set, cmd_api_show, cmd_check, cmd_config_init, cmd_config_show, cmd_debug, cmd_doctor, cmd_goal, cmd_inspect, cmd_run


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="safe", description="Safety CLI for Ansible-compatible operations")
    parser.add_argument("--engine", default=os.environ.get("SAFE_ENGINE", "ansible"), help="executor engine: ansible or a command name/path; default: ansible")
    parser.add_argument("--config", help="configuration file path; default: ./config.yaml when present")

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

    api = sub.add_parser("api", help="configure LLM API providers for Agent goal understanding")
    api_sub = api.add_subparsers(dest="api_command", required=True)

    api_set = api_sub.add_parser("set", help="configure an API provider")
    api_set.add_argument("provider", choices=["deepseek"], help="API provider")
    api_set.add_argument("--api-key", help="DeepSeek API key; alternatively use --api-key-env")
    api_set.add_argument("--api-key-env", help="read API key from an environment variable")
    api_set.add_argument("--base-url", default="https://api.deepseek.com", help="DeepSeek-compatible API base URL")
    api_set.add_argument("--model", default="deepseek-chat", help="DeepSeek model name")
    api_set.add_argument("--timeout", type=int, default=30, help="API request timeout seconds")
    api_set.set_defaults(func=cmd_api_set)

    api_show = api_sub.add_parser("show", help="show API configuration with secrets masked")
    api_show.set_defaults(func=cmd_api_show)

    api_disable = api_sub.add_parser("disable", help="disable the configured API provider")
    api_disable.set_defaults(func=cmd_api_disable)

    goal = sub.add_parser("goal", help="run the Agent MVP workflow from a natural-language goal")
    goal.add_argument("goal", nargs="+", help="natural-language goal, for example: safe goal '安全发布 demo.yml 到 dev'")
    goal.add_argument("--playbook", help="playbook path; overrides goal inference")
    goal.add_argument("-i", "--inventory", help="inventory file/path")
    goal.add_argument("--limit", help="limit target hosts")
    goal.add_argument("--env", help="environment name")
    goal.add_argument("-e", "--extra-var", action="append", default=[], help="extra variable, can be repeated")
    goal.add_argument("--apply", dest="apply_mode", action="store_true", default=None, help="allow actual apply mode after approval gates")
    goal.add_argument("--dry-run", dest="apply_mode", action="store_false", help="force dry-run mode")
    goal.add_argument("--approve", action="store_true", help="approve non-production apply gates")
    goal.add_argument("--confirm", help="required value PROD when applying to prod")
    goal.add_argument("--timeout", type=int, default=600, help="execution timeout seconds")
    goal.add_argument("--report", help="write JSON check report")
    goal.add_argument("--trace-out", help="write Agent trace JSON to a specific path")
    goal.set_defaults(func=cmd_goal)

    config = sub.add_parser("config", help="show or initialize configuration")
    config_sub = config.add_subparsers(dest="config_command", required=True)

    config_show = config_sub.add_parser("show", help="print effective configuration")
    config_show.set_defaults(func=cmd_config_show)

    config_init = config_sub.add_parser("init", help="write default config.yaml in the current directory")
    config_init.set_defaults(func=cmd_config_init)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)
