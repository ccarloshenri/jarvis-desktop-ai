from __future__ import annotations

from dataclasses import dataclass

from jarvis.models.action_result import ActionResult
from jarvis.models.command import Command


@dataclass(frozen=True, slots=True)
class InteractionResult:
    transcript: str
    command: Command | None
    action_result: ActionResult | None
    spoken_response: str
