from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class ICommandInterpreter(ABC):
    @abstractmethod
    def interpret(self, text: str) -> dict[str, Any] | None:
        """Interpret text into a command payload when it represents a system action.

        Returns either a flat ``{"action": ..., "target": ...}`` dict for simple
        commands or a nested ``{"action": ..., "parameters": {...}}`` dict for
        richer ones (e.g. Discord). Both shapes are accepted by ``CommandMapper``.
        """
