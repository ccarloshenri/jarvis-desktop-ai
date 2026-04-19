"""Resolves an app name the user spoke against apps actually installed on the machine.

Uses the existing WindowsApplicationFinder + ApplicationMatcher so the
ranking logic stays consistent with how the finder itself picks an app
to launch — we're not building a second, parallel notion of "best match".

Confidence tiers come from how decisively the top-scored candidate beats
everything else:
- HIGH: top is a clear winner (strong score AND dominates runner-up)
- MEDIUM: top is plausible but has a close runner-up
- LOW: top barely scored above noise

The finder's internal 200 floor is used as the "definitely unusable"
cutoff. Below that we return a LOW-tier result rather than None — the
caller (correction service) then knows a lookup happened but didn't
find evidence strong enough to substitute.
"""

from __future__ import annotations

import logging

from jarvis.enums.action_type import ActionType
from jarvis.implementations.system.application_matcher import ApplicationMatcher
from jarvis.implementations.system.windows_application_finder import WindowsApplicationFinder
from jarvis.interfaces.ientity_resolver import IEntityResolver
from jarvis.models.application_candidate import ApplicationCandidate
from jarvis.models.command import Command
from jarvis.models.resolution import ConfidenceTier, ResolutionResult

LOGGER = logging.getLogger(__name__)


# Tuned empirically against ApplicationMatcher's scoring scale (~10_000
# for exact match, ~200 for weak fuzzy). A top score under this floor
# means "nothing on this machine looks like what the user said".
_MIN_SCORE_FLOOR = 200.0
_MIN_HIGH_SCORE = 500.0
_MIN_MEDIUM_SCORE = 280.0
# A top candidate only counts as a "clear winner" if it beats the
# runner-up by this much. Prevents auto-correcting to "VS Code" when the
# user said something that could plausibly be VS Code *or* VSCode Insiders.
_HIGH_DOMINANCE_MARGIN = 200.0

_SUPPORTED_ACTIONS = {ActionType.OPEN_APP, ActionType.CLOSE_APP}


class AppEntityResolver(IEntityResolver):
    def __init__(
        self,
        application_finder: WindowsApplicationFinder,
        matcher: ApplicationMatcher | None = None,
    ) -> None:
        self._finder = application_finder
        self._matcher = matcher or ApplicationMatcher()

    @property
    def name(self) -> str:
        return "apps"

    def can_handle(self, command: Command) -> bool:
        return command.action in _SUPPORTED_ACTIONS

    def resolve(self, command: Command) -> ResolutionResult | None:
        target = (command.target or "").strip()
        if not target:
            return None
        candidates = self._finder.candidates()
        if not candidates:
            return None

        scored: list[tuple[float, ApplicationCandidate]] = [
            (self._matcher.score(target, c), c) for c in candidates
        ]
        scored.sort(key=lambda item: item[0], reverse=True)

        top_score, top_candidate = scored[0]
        runner_up_score = scored[1][0] if len(scored) > 1 else 0.0

        if top_score < _MIN_SCORE_FLOOR:
            return ResolutionResult(
                original=target,
                resolved=target,
                confidence=0.0,
                tier=ConfidenceTier.LOW,
                source=self.name,
            )

        # Normalize the raw score into a 0-1 confidence so the caller
        # can log and compare across resolvers. Capped at 1.0 for the
        # trivial "exact match" case (score = 10_000).
        confidence = min(top_score / 1500.0, 1.0)
        tier = self._tier_for(top_score, runner_up_score)
        resolved_name = top_candidate.name

        alternatives = tuple(
            c.name for score, c in scored[1:4] if score >= _MIN_SCORE_FLOOR
        )
        LOGGER.debug(
            "app_resolver_scored",
            extra={
                "event_data": {
                    "target": target,
                    "top": resolved_name,
                    "top_score": top_score,
                    "runner_up": runner_up_score,
                    "tier": tier.value,
                }
            },
        )
        return ResolutionResult(
            original=target,
            resolved=resolved_name,
            confidence=confidence,
            tier=tier,
            alternatives=alternatives,
            source=self.name,
        )

    def _tier_for(self, top_score: float, runner_up_score: float) -> ConfidenceTier:
        margin = top_score - runner_up_score
        if top_score >= _MIN_HIGH_SCORE and margin >= _HIGH_DOMINANCE_MARGIN:
            return ConfidenceTier.HIGH
        if top_score >= _MIN_MEDIUM_SCORE:
            return ConfidenceTier.MEDIUM
        return ConfidenceTier.LOW
