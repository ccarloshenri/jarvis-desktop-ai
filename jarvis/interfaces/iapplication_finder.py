from __future__ import annotations

from abc import ABC, abstractmethod


class IApplicationFinder(ABC):
    @abstractmethod
    def find(self, name: str) -> str | None:
        """Return the best matching application path for the given name."""
