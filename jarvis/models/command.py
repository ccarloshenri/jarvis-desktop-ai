from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jarvis.enums.action_type import ActionType


@dataclass(frozen=True, slots=True)
class Command:
    action: ActionType
    target: str
    parameters: dict[str, Any] = field(default_factory=dict)

    def param(self, key: str, default: Any = None) -> Any:
        return self.parameters.get(key, default)
