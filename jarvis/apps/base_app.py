from __future__ import annotations

from abc import ABC, abstractmethod

from jarvis.models.action_result import ActionResult
from jarvis.models.command import Command


class BaseApp(ABC):
    """A high-level integration with a third-party application.

    A BaseApp owns its own automation backend(s), context/memory, and
    knows how to dispatch a typed Command to the right internal service.
    The `SystemActionExecutor` only delegates — it does not need to know
    *how* an app is automated.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Stable identifier (e.g. 'discord', 'spotify')."""

    @abstractmethod
    def can_handle(self, command: Command) -> bool:
        """True if this app accepts the given command's action."""

    @abstractmethod
    def execute(self, command: Command) -> ActionResult:
        """Execute the command. Should never raise for expected failures."""
