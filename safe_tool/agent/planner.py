from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional


@dataclass
class GoalPlan:
    goal: str
    playbook: Optional[str]
    inventory: Optional[str]
    env: Optional[str]
    limit: Optional[str]
    extra_vars: List[str]
    apply: bool
    confidence: float
    missing_fields: List[str]
    notes: List[str]
    playbook_candidates: List[str]
    inventory_candidates: List[str]


ENV_ALIASES = {
    "dev": "dev",
    "develop": "dev",
    "development": "dev",
    "开发": "dev",
    "test": "test",
    "testing": "test",
    "测试": "test",
    "stage": "stage",
    "staging": "stage",
    "预发": "stage",
    "prod": "prod",
    "production": "prod",
    "生产": "prod",
}

DRY_RUN_HINTS = {"dry-run", "dryrun", "仅检查", "只检查", "检查", "模拟", "预演"}
APPLY_HINTS = {"apply", "发布", "执行", "上线", "部署", "run", "rollout"}


def infer_playbook(goal: str) -> Optional[str]:
    match = re.search(r"([\w./-]+\.ya?ml)", goal)
    if match:
        return match.group(1)
    return None


def infer_inventory(goal: str) -> Optional[str]:
    match = re.search(r"([\w./-]+\.ini)", goal)
    if match:
        return match.group(1)
    return None


def infer_env(goal: str) -> Optional[str]:
    lowered = goal.lower()
    for token, normalized in ENV_ALIASES.items():
        if token in lowered or token in goal:
            return normalized
    return None


def infer_apply(goal: str, explicit_apply: Optional[bool]) -> bool:
    if explicit_apply is not None:
        return explicit_apply

    lowered = goal.lower()
    if any(hint in lowered or hint in goal for hint in DRY_RUN_HINTS):
        return False
    if any(hint in lowered or hint in goal for hint in APPLY_HINTS):
        return True
    return False


def discover_candidates(pattern: str) -> List[str]:
    root = Path.cwd()
    return sorted(str(path.relative_to(root)) for path in root.glob(pattern) if path.is_file())


def clamp_confidence(value: float) -> float:
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return round(value, 2)


def _hint_value(semantic_hints: Optional[Any], field: str) -> Optional[Any]:
    if not semantic_hints:
        return None
    return getattr(semantic_hints, field, None)


def build_goal_plan(
    goal: str,
    args_playbook: Optional[str],
    args_inventory: Optional[str],
    args_env: Optional[str],
    args_limit: Optional[str],
    extra_vars: List[str],
    explicit_apply: Optional[bool],
    default_env: Optional[str],
    semantic_hints: Optional[Any] = None,
) -> GoalPlan:
    notes: List[str] = []
    missing_fields: List[str] = []
    confidence = 0.0

    playbook_candidates = discover_candidates("*.yml") + discover_candidates("*.yaml")
    inventory_candidates = discover_candidates("*.ini")

    semantic_playbook = _hint_value(semantic_hints, "playbook")
    playbook = args_playbook or semantic_playbook or infer_playbook(goal)
    if args_playbook:
        confidence += 0.42
        notes.append("playbook from --playbook")
    elif semantic_playbook:
        confidence += 0.38
        notes.append("playbook inferred by semantic parser")
    elif playbook:
        confidence += 0.35
        notes.append("playbook inferred from goal")
    elif len(playbook_candidates) == 1:
        playbook = playbook_candidates[0]
        confidence += 0.2
        notes.append("playbook auto-selected from workspace candidate")
    else:
        missing_fields.append("playbook")
        if playbook_candidates:
            notes.append("multiple playbooks detected; please specify --playbook")

    semantic_inventory = _hint_value(semantic_hints, "inventory")
    inventory = args_inventory or semantic_inventory or infer_inventory(goal)
    if args_inventory:
        confidence += 0.2
        notes.append("inventory from -i/--inventory")
    elif semantic_inventory:
        confidence += 0.18
        notes.append("inventory inferred by semantic parser")
    elif inventory:
        confidence += 0.15
        notes.append("inventory inferred from goal")
    elif len(inventory_candidates) == 1:
        inventory = inventory_candidates[0]
        confidence += 0.1
        notes.append("inventory auto-selected from workspace candidate")

    semantic_env = _hint_value(semantic_hints, "env")
    env = args_env or semantic_env or infer_env(goal) or default_env
    if args_env:
        confidence += 0.2
        notes.append("env from --env")
    elif semantic_env:
        confidence += 0.18
        notes.append("env inferred by semantic parser")
    elif infer_env(goal):
        confidence += 0.15
        notes.append("env inferred from goal")
    elif default_env:
        confidence += 0.05
        notes.append("env from default settings")

    semantic_apply = _hint_value(semantic_hints, "apply")
    apply = semantic_apply if explicit_apply is None and semantic_apply is not None else infer_apply(goal, explicit_apply)
    lowered = goal.lower()
    if explicit_apply is not None:
        confidence += 0.1
        notes.append("execution mode from explicit CLI flag")
    elif semantic_apply is not None:
        confidence += 0.09
        notes.append("execution mode inferred by semantic parser")
    elif any(hint in lowered or hint in goal for hint in DRY_RUN_HINTS | APPLY_HINTS):
        confidence += 0.08
        notes.append("execution mode inferred from goal")
    else:
        confidence += 0.04
        notes.append("execution mode defaulted to dry-run")

    semantic_extra_vars = _hint_value(semantic_hints, "extra_vars") or []
    combined_extra_vars = list(dict.fromkeys(list(semantic_extra_vars) + extra_vars))
    semantic_limit = _hint_value(semantic_hints, "limit")
    if semantic_hints:
        semantic_confidence = float(_hint_value(semantic_hints, "confidence") or 0.0)
        confidence += semantic_confidence * 0.05
        for item in _hint_value(semantic_hints, "notes") or []:
            notes.append(f"semantic parser: {item}")

    return GoalPlan(
        goal=goal,
        playbook=playbook,
        inventory=inventory,
        env=env,
        limit=args_limit or semantic_limit,
        extra_vars=combined_extra_vars,
        apply=apply,
        confidence=clamp_confidence(confidence),
        missing_fields=missing_fields,
        notes=notes,
        playbook_candidates=playbook_candidates,
        inventory_candidates=inventory_candidates,
    )
