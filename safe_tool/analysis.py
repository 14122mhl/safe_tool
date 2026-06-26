from __future__ import annotations

import importlib
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .constants import RISK_MODULES, RISK_ORDER, TASK_RESERVED_KEYS
from .models import CheckResult, PlaybookAnalysis, TaskAnalysis


def load_yaml_file(path: str) -> Any:
    try:
        yaml = importlib.import_module("yaml")
    except ImportError as exc:
        raise RuntimeError("PyYAML is required. Install it with: python3 -m pip install pyyaml") from exc

    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


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


def get_module_risk(module: Optional[str], risk_rules: Optional[Dict[str, Dict[str, str]]] = None) -> Tuple[str, str, str]:
    short_name = normalize_module_name(module)
    if not short_name:
        return "UNKNOWN", "could not detect module", "review task manually"

    rules = risk_rules or RISK_MODULES
    rule = rules.get(short_name)
    if rule:
        return rule["risk"], rule["reason"], rule["recommendation"]

    return "LOW", "module is not marked as state-changing by current rules", "safe to inspect; still review before production apply"


def build_playbook_analysis(playbook: str, risk_rules: Optional[Dict[str, Dict[str, str]]] = None) -> PlaybookAnalysis:
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
            risk, reason, recommendation = get_module_risk(module, risk_rules)

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


def static_risk_scan(playbook: str, risk_rules: Optional[Dict[str, Dict[str, str]]] = None) -> List[CheckResult]:
    path = Path(playbook)
    if not path.exists():
        return []

    results: List[CheckResult] = []
    try:
        analysis = build_playbook_analysis(playbook, risk_rules)
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
