from __future__ import annotations

import re
import shutil
import subprocess
from typing import List, Optional

from .models import CheckResult, CommandResult


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
