from __future__ import annotations

from typing import List, Tuple

from ..constants import PROD_NAMES


def evaluate_execution_policy(
    env: str | None,
    apply: bool,
    overall_risk: str,
    plan_confidence: float,
    min_goal_confidence_to_apply: float,
    require_prod_confirm: bool,
    confirm: str | None,
    approved: bool,
) -> Tuple[bool, List[str]]:
    reasons: List[str] = []

    if not apply:
        return True, ["dry-run mode; approval not required"]

    if plan_confidence < min_goal_confidence_to_apply:
        reasons.append(
            f"plan confidence {plan_confidence:.2f} is below threshold {min_goal_confidence_to_apply:.2f}; rerun with explicit flags"
        )

    if not approved:
        reasons.append("apply mode requires explicit approval; add --approve")

    if overall_risk == "HIGH" and not approved:
        reasons.append("HIGH risk execution requires --approve")

    if env in PROD_NAMES and require_prod_confirm and confirm != "PROD":
        reasons.append("production apply requires --confirm PROD")

    return len(reasons) == 0, reasons
