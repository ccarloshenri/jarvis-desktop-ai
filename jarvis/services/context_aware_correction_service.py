"""Orchestrates entity resolvers to turn raw commands into context-validated ones.

Three possible outcomes per command:

- **applied**: a resolver returned HIGH confidence and the command's target
  is rewritten to the resolved value. Proceeds immediately.
- **needs_confirmation**: a resolver returned MEDIUM confidence — strong
  enough to suggest a correction but not strong enough to auto-apply.
  The correction is held for the next turn; the assistant speaks a
  confirmation question and waits for a yes/no reply.
- **unchanged**: no resolver applied, or all resolvers returned LOW. The
  command flows through as-is.

Rationale for the three-tier policy:

Auto-correcting on weak evidence silently rewrites user intent ("I said
Mari Dançando and it played Marina Sena"). Never correcting forces the
user to always be Whisper-perfect. Asking on medium confidence splits
the difference — the user confirms or denies once, and the system
learns what they actually meant.

Resolvers are consulted in order; the first `can_handle` wins. Two
resolvers shouldn't overlap on the same ActionType, so ordering is only
a tiebreaker for correctness, not a priority list.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from enum import Enum
from typing import Sequence

from jarvis.interfaces.ientity_resolver import IEntityResolver
from jarvis.models.command import Command
from jarvis.models.resolution import ConfidenceTier, ResolutionResult
from jarvis.utils.performance import Category, log, timed

LOGGER = logging.getLogger(__name__)


class CorrectionOutcome(str, Enum):
    APPLIED = "applied"
    NEEDS_CONFIRMATION = "needs_confirmation"
    UNCHANGED = "unchanged"


@dataclass(frozen=True, slots=True)
class CorrectionResult:
    outcome: CorrectionOutcome
    command: Command
    # Populated when outcome == NEEDS_CONFIRMATION — the caller stashes
    # it as pending state and speaks the candidate for user confirmation.
    candidate_command: Command | None = None
    resolution: ResolutionResult | None = None


class ContextAwareCorrectionService:
    def __init__(self, resolvers: Sequence[IEntityResolver]) -> None:
        self._resolvers = list(resolvers)

    def correct(self, command: Command) -> CorrectionResult:
        resolver = self._pick_resolver(command)
        if resolver is None:
            return CorrectionResult(outcome=CorrectionOutcome.UNCHANGED, command=command)

        with timed(Category.PARSER, "entity resolve", resolver=resolver.name) as m:
            resolution = resolver.resolve(command)
            m["tier"] = resolution.tier.value if resolution else "n/a"

        if resolution is None:
            return CorrectionResult(outcome=CorrectionOutcome.UNCHANGED, command=command)

        log(
            Category.PARSER,
            f"resolved target {resolution.original!r} -> {resolution.resolved!r}",
            tier=resolution.tier.value,
            confidence=round(resolution.confidence, 3),
            source=resolution.source,
            changed=resolution.is_changed,
        )

        if resolution.tier == ConfidenceTier.HIGH and resolution.is_changed:
            corrected = self._rewrite_target(command, resolution.resolved)
            return CorrectionResult(
                outcome=CorrectionOutcome.APPLIED,
                command=corrected,
                resolution=resolution,
            )
        if resolution.tier == ConfidenceTier.MEDIUM and resolution.is_changed:
            candidate = self._rewrite_target(command, resolution.resolved)
            return CorrectionResult(
                outcome=CorrectionOutcome.NEEDS_CONFIRMATION,
                command=command,
                candidate_command=candidate,
                resolution=resolution,
            )
        return CorrectionResult(
            outcome=CorrectionOutcome.UNCHANGED,
            command=command,
            resolution=resolution,
        )

    def _pick_resolver(self, command: Command) -> IEntityResolver | None:
        for resolver in self._resolvers:
            if resolver.can_handle(command):
                return resolver
        return None

    def _rewrite_target(self, command: Command, new_target: str) -> Command:
        # Mirror the new target into `parameters["target"]` too: some
        # executor paths read from parameters rather than the top-level
        # field, and leaving them out of sync would silently regress.
        params = dict(command.parameters or {})
        if "target" in params:
            params["target"] = new_target
        return replace(command, target=new_target, parameters=params)
