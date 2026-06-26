from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


def build_run_id() -> str:
    return datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")


def default_trace_path(run_id: str) -> Path:
    return Path.cwd() / ".safe-tool" / "runs" / f"{run_id}.json"


def default_log_path(run_id: str) -> Path:
    return Path.cwd() / ".safe-tool" / "runs" / f"{run_id}.log"


def write_trace(trace: Dict[str, Any], output_path: Optional[str] = None) -> Path:
    path = Path(output_path) if output_path else default_trace_path(trace["run_id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(trace, indent=2, ensure_ascii=False), encoding="utf-8")
    return path
