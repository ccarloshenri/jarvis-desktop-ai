from __future__ import annotations

from dataclasses import dataclass

from jarvis.enums.action_type import ActionType


@dataclass(frozen=True, slots=True)
class ActionResult:
    success: bool
    message: str
    action: ActionType
    target: str
