"""Validates a Spotify play target against real Spotify catalog results.

The resolver asks Spotify for the top candidates matching the user's
transcribed target, then measures how well that target actually matches
what Spotify returned — because Spotify's fuzzy server-side search will
happily return *something* even for nonsense inputs, and we don't want
to auto-correct "mari dançando" to "Marina Sena" just because Spotify's
top hit happened to be Marina Sena.

The similarity check runs against several projections of the top result
(track name, artist name, "artist track" concat) and takes the max. A
spoken artist name like "marina sana" matches the artist projection of
a "Marina Sena - Lua Cheia" result strongly, even though the track name
has nothing to do with what the user said.

Diacritics are stripped before comparison. Whisper routinely drops
accents in pt-BR transcriptions, and penalizing "marina sena" vs
"Marina Senã" by a few points of ratio would cause us to ask for
confirmation on trivially correct matches.
"""

from __future__ import annotations

import difflib
import logging
import unicodedata

from jarvis.enums.action_type import ActionType
from jarvis.interfaces.ientity_resolver import IEntityResolver
from jarvis.models.command import Command
from jarvis.models.resolution import ConfidenceTier, ResolutionResult
from jarvis.services.spotify_controller import SpotifyController

LOGGER = logging.getLogger(__name__)


_HIGH_RATIO = 0.82
_MEDIUM_RATIO = 0.55
# Runner-up must trail the top result by this much before we call it
# a "clear winner" worthy of auto-correcting. Prevents auto-picking
# when multiple artists share a near-identical phonetic form.
_DOMINANCE_MARGIN = 0.08
_SEARCH_LIMIT = 5

_SUPPORTED_ACTIONS = {ActionType.PLAY_SPOTIFY}


class SpotifyEntityResolver(IEntityResolver):
    def __init__(self, controller: SpotifyController) -> None:
        self._controller = controller

    @property
    def name(self) -> str:
        return "spotify"

    def can_handle(self, command: Command) -> bool:
        return command.action in _SUPPORTED_ACTIONS

    def resolve(self, command: Command) -> ResolutionResult | None:
        target = (command.target or "").strip()
        if not target:
            return None
        results = self._controller.search(target, limit=_SEARCH_LIMIT)
        if not results:
            # Distinguish "search didn't run" (auth unavailable, network
            # down, etc.) from "searched and got nothing" isn't worth the
            # extra plumbing — in both cases the resolver has no evidence
            # to offer and we bail back to the original target.
            return None

        scored = [(self._similarity(target, r), r) for r in results]
        scored.sort(key=lambda item: item[0], reverse=True)

        top_ratio, top_result = scored[0]
        runner_up_ratio = scored[1][0] if len(scored) > 1 else 0.0
        tier = self._tier_for(top_ratio, runner_up_ratio)

        # The target we hand back to the executor must be something
        # Spotify can re-search deterministically later. "{track} {artist}"
        # is stable — the artist alone would pull a different track than
        # the one we validated against.
        resolved_target = self._canonical_target(top_result)

        alternatives = tuple(
            self._canonical_target(r) for _, r in scored[1:4] if _ > _MEDIUM_RATIO
        )
        LOGGER.debug(
            "spotify_resolver_scored",
            extra={
                "event_data": {
                    "target": target,
                    "top": resolved_target,
                    "top_ratio": round(top_ratio, 3),
                    "runner_up_ratio": round(runner_up_ratio, 3),
                    "tier": tier.value,
                }
            },
        )
        return ResolutionResult(
            original=target,
            resolved=resolved_target,
            confidence=top_ratio,
            tier=tier,
            alternatives=alternatives,
            source=self.name,
            spoken_form=self._spoken_form(top_result),
        )

    def _similarity(self, spoken: str, result: dict) -> float:
        spoken_norm = _normalize(spoken)
        track = _normalize(result.get("name", ""))
        artist = _normalize(result.get("artist", ""))
        candidates = [
            track,
            artist,
            f"{track} {artist}".strip(),
            f"{artist} {track}".strip(),
        ]
        return max(
            (difflib.SequenceMatcher(None, spoken_norm, c).ratio() for c in candidates if c),
            default=0.0,
        )

    def _canonical_target(self, result: dict) -> str:
        name = (result.get("name") or "").strip()
        artist = (result.get("artist") or "").strip()
        if name and artist:
            return f"{name} {artist}"
        return name or artist

    def _spoken_form(self, result: dict) -> str:
        # Prefer the artist alone for the confirmation question. "Você
        # quis dizer Marina Sena?" sounds natural; "Você quis dizer Lua
        # Cheia Marina Sena?" doesn't. When there's no artist (rare —
        # search hit a playlist or podcast), fall back to the track name.
        artist = (result.get("artist") or "").strip()
        if artist:
            return artist
        return (result.get("name") or "").strip()

    def _tier_for(self, top_ratio: float, runner_up_ratio: float) -> ConfidenceTier:
        if top_ratio >= _HIGH_RATIO and (top_ratio - runner_up_ratio) >= _DOMINANCE_MARGIN:
            return ConfidenceTier.HIGH
        if top_ratio >= _MEDIUM_RATIO:
            return ConfidenceTier.MEDIUM
        return ConfidenceTier.LOW


def _normalize(text: str) -> str:
    """Lowercase + strip diacritics. Whisper routinely drops accents
    on pt-BR transcriptions, so comparing "marina sena" against
    "Marina Senã" must treat the accent as irrelevant."""
    if not text:
        return ""
    decomposed = unicodedata.normalize("NFKD", text)
    no_accents = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join(no_accents.lower().split())
