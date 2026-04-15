from __future__ import annotations

from dataclasses import dataclass

from jarvis.enums.action_type import ActionType


@dataclass(frozen=True, slots=True)
class Command:
    action: ActionType
    target: str
