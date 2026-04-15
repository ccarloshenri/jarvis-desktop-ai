from __future__ import annotations

from abc import ABC, abstractmethod


class ICommandInterpreter(ABC):
    @abstractmethod
    def interpret(self, text: str) -> dict[str, str] | None:
        """Interpret text into a command payload when it represents a system action."""
