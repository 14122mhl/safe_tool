from __future__ import annotations

from typing import Dict


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
