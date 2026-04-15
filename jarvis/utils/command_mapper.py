from __future__ import annotations

from jarvis.enums.action_type import ActionType
from jarvis.models.command import Command


class CommandMapper:
    def from_payload(self, payload: dict[str, str]) -> Command:
        action_value = (payload.get("action") or "").strip()
        target = (payload.get("target") or "").strip()
        if not action_value or not target:
            raise ValueError("Command payload must contain non-empty 'action' and 'target'.")
        return Command(action=ActionType(action_value), target=target)
