from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


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
