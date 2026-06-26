from __future__ import annotations

from pathlib import Path
from typing import Optional

from .constants import PROD_NAMES, VALID_ENVS
from .models import CheckResult


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
