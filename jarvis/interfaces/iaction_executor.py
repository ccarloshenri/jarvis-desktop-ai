from __future__ import annotations

from abc import ABC, abstractmethod

from jarvis.models.action_result import ActionResult
from jarvis.models.command import Command


class IActionExecutor(ABC):
    @abstractmethod
    def execute(self, command: Command) -> ActionResult:
        """Execute the given command."""
