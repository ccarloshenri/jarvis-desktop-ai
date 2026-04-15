from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

DecisionType = Literal["action", "chat"]


@dataclass(frozen=True, slots=True)
class LLMDecision:
    type: DecisionType
    spoken_response: str
    app: str | None = None
    action: str | None = None
    parameters: dict[str, Any] = field(default_factory=dict)

    @property
    def is_action(self) -> bool:
        return self.type == "action" and bool(self.action)
