from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import List, Optional

from .models import CheckResult, PlaybookAnalysis


def print_line(message: str = "") -> None:
    print(message)


def print_result(result: CheckResult) -> None:
    prefix = {"PASS": "[PASS]", "WARN": "[WARN]", "FAIL": "[FAIL]"}.get(result.status, "[INFO]")
    print_line(f"{prefix} {result.name}: {result.message}")
    if result.remediation:
        print_line(f"       remediation: {result.remediation}")


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
