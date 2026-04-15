from __future__ import annotations

import json
import re
from typing import Any

from jarvis.enums.action_type import ActionType


class LLMResponseParser:
    def extract_payload(self, raw_text: str) -> dict[str, str]:
        json_match = re.search(r"\{.*\}", raw_text, re.DOTALL)
        candidate = json_match.group(0) if json_match else raw_text
        payload = json.loads(candidate)
        return self.normalize_payload(payload)

    def normalize_payload(self, payload: dict[str, Any]) -> dict[str, str]:
        action_value = str(payload.get("action", "")).strip().lower()
        target = str(payload.get("target", "")).strip().lower()
        ActionType(action_value)
        if not target:
            raise ValueError("Target is required.")
        return {"action": action_value, "target": target}
