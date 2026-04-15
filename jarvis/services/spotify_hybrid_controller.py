"""Hybrid Spotify controller.

Uses the Web API (anonymous tokens, no user login) ONLY to resolve a natural
language query to an exact Spotify URI. Playback/opening is delegated to the
local Spotify Desktop app via Ctrl+K + URI paste + Enter.

This sidesteps both limitations we hit earlier:
- Web API playback endpoints require OAuth with user login → avoided.
- Pure keyboard search was fuzzy and could open the wrong thing → now the
  pasted value is the exact URI of the right item, not a text query.
"""

from __future__ import annotations

import logging
import os
import sys

from jarvis.services.spotify_desktop_controller import SpotifyDesktopController
from jarvis.services.spotify_search_provider import SpotifySearchProvider

LOGGER = logging.getLogger(__name__)


class SpotifyHybridController:
    def __init__(
        self,
        search_provider: SpotifySearchProvider | None = None,
        desktop_controller: SpotifyDesktopController | None = None,
    ) -> None:
        self._search = search_provider or SpotifySearchProvider()
        self._desktop = desktop_controller or SpotifyDesktopController()

    def search_and_play(self, query: str) -> bool:
        result = self._search.search(query)
        if result is None:
            LOGGER.warning("spotify_hybrid_no_result", extra={"event_data": {"query": query}})
            return False
        LOGGER.info(
            "spotify_hybrid_resolved",
            extra={
                "event_data": {
                    "query": query,
                    "kind": result.kind,
                    "uri": result.uri,
                    "name": result.name,
                    "subtitle": result.subtitle,
                }
            },
        )
        if not self._desktop.open_uri(result.uri):
            LOGGER.warning("spotify_hybrid_open_failed", extra={"event_data": {"uri": result.uri}})
            return False
        return True

    def open_search_fallback(self, query: str) -> bool:
        if sys.platform != "win32":
            return False
        try:
            os.startfile(f"spotify:search:{query}")  # type: ignore[attr-defined]
            return True
        except OSError:
            return False
