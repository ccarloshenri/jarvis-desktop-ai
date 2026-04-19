"""Output of an entity resolution pass: was the name a good match, and how sure are we?"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ConfidenceTier(str, Enum):
    """Three-way confidence bucket driving the correction policy.

    Kept intentionally coarse. The exact numeric threshold for HIGH vs
    MEDIUM is a judgment call that varies per resolver (app name matching
    uses different signal than Spotify search), so each resolver decides
    which tier its raw score maps to — the downstream correction service
    only cares about the tier.
    """

    HIGH = "high"      # apply correction automatically
    MEDIUM = "medium"  # ask the user for confirmation
    LOW = "low"        # don't correct — there's no strong evidence


@dataclass(frozen=True, slots=True)
class ResolutionResult:
    """One resolver's verdict on a user-spoken target.

    The correction service never invents a `resolved` value itself — it
    always comes from a real entity (an installed app, a Spotify search
    hit, a Discord contact). If a resolver has nothing to say, it
    returns None; a ResolutionResult with tier=LOW still represents a
    deliberate "not confident enough to substitute" decision, which is
    different from the resolver not being applicable at all.

    `resolved` vs `spoken_form`: the executor needs a deterministic query
    it can re-run (e.g., "Lua Cheia Marina Sena" so Spotify finds the
    exact track), but the confirmation question spoken to the user should
    sound natural ("Marina Sena"). Resolvers populate both when the two
    differ; when `spoken_form` is empty, the caller falls back to `resolved`.
    """

    original: str
    resolved: str
    confidence: float
    tier: ConfidenceTier
    alternatives: tuple[str, ...] = field(default_factory=tuple)
    source: str = ""
    spoken_form: str = ""

    @property
    def is_changed(self) -> bool:
        return self.resolved.strip().lower() != self.original.strip().lower()

    @property
    def spoken(self) -> str:
        return self.spoken_form or self.resolved
