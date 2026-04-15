from __future__ import annotations

from abc import ABC, abstractmethod


class ILLM(ABC):
    @abstractmethod
    def interpret(self, text: str) -> str:
        """Interpret raw text into a natural-language response."""
