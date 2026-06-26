from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class SemanticGoalHints:
    playbook: Optional[str]
    inventory: Optional[str]
    env: Optional[str]
    limit: Optional[str]
    extra_vars: List[str]
    apply: Optional[bool]
    confidence: float
    notes: List[str]


class DeepSeekGoalParser:
    def __init__(self, api_key: str, base_url: str, model: str, timeout: int = 30) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def parse_goal(self, goal: str, playbook_candidates: List[str], inventory_candidates: List[str]) -> SemanticGoalHints:
        content = self._chat(goal, playbook_candidates, inventory_candidates)
        data = self._parse_json(content)
        return SemanticGoalHints(
            playbook=self._optional_str(data.get("playbook")),
            inventory=self._optional_str(data.get("inventory")),
            env=self._optional_str(data.get("env")),
            limit=self._optional_str(data.get("limit")),
            extra_vars=self._string_list(data.get("extra_vars")),
            apply=self._optional_bool(data.get("apply")),
            confidence=self._confidence(data.get("confidence")),
            notes=self._string_list(data.get("notes")),
        )

    def _chat(self, goal: str, playbook_candidates: List[str], inventory_candidates: List[str]) -> str:
        payload = {
            "model": self.model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You parse deployment/safety goals into JSON only. "
                        "Do not invent file paths. Choose only from candidates or return null. "
                        "Allowed env values: dev, test, stage, staging, prod, production. "
                        "Return keys: playbook, inventory, env, limit, extra_vars, apply, confidence, notes. "
                        "Use apply=true only when the user clearly asks to execute/apply/deploy/release. "
                        "Use apply=false for check, dry-run, preview, validate, inspect."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "goal": goal,
                            "playbook_candidates": playbook_candidates,
                            "inventory_candidates": inventory_candidates,
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
        }
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"DeepSeek API request failed with HTTP {exc.code}: {detail[:300]}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"DeepSeek API request failed: {exc.reason}") from exc

        data = json.loads(body)
        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError("DeepSeek API returned no choices")
        message = choices[0].get("message") or {}
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("DeepSeek API returned empty content")
        return content

    @staticmethod
    def _parse_json(content: str) -> Dict[str, Any]:
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"DeepSeek goal parser returned invalid JSON: {content[:300]}") from exc
        if not isinstance(data, dict):
            raise RuntimeError("DeepSeek goal parser returned a non-object JSON value")
        return data

    @staticmethod
    def _optional_str(value: Any) -> Optional[str]:
        if isinstance(value, str) and value.strip():
            return value.strip()
        return None

    @staticmethod
    def _optional_bool(value: Any) -> Optional[bool]:
        if isinstance(value, bool):
            return value
        return None

    @staticmethod
    def _string_list(value: Any) -> List[str]:
        if not isinstance(value, list):
            return []
        return [item.strip() for item in value if isinstance(item, str) and item.strip()]

    @staticmethod
    def _confidence(value: Any) -> float:
        if isinstance(value, (int, float)):
            if value < 0:
                return 0.0
            if value > 1:
                return 1.0
            return round(float(value), 2)
        return 0.0