from __future__ import annotations

from abc import ABC, abstractmethod

from jarvis.models.command import Command
from jarvis.models.resolution import ResolutionResult


class IEntityResolver(ABC):
    """Maps a user-spoken target to a real, currently-existing entity.

    Key contract: resolvers do NOT fabricate corrections. They look up the
    spoken target against a concrete source of truth — installed apps,
    Spotify search results, contacts — and report confidence based on
    how well the spoken form matched that source. A resolver that has no
    source to check against should return None, not a forced low-confidence
    result, so the downstream correction service can distinguish
    "not applicable here" from "applicable but nothing matched".
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Short identifier used in logs."""

    @abstractmethod
    def can_handle(self, command: Command) -> bool:
        """Return True if this resolver knows how to validate the command's target."""

    @abstractmethod
    def resolve(self, command: Command) -> ResolutionResult | None:
        """Look up the command's target against this resolver's entity source.

        Returns None if the lookup isn't applicable at all (e.g., target is
        empty, or the required upstream service is unreachable). Returns a
        ResolutionResult otherwise — tier=LOW is a valid answer meaning
        "I looked and can't back a correction".
        """
