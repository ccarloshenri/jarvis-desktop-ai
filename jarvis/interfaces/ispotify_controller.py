from __future__ import annotations

from typing import Protocol


class ISpotifyController(Protocol):
    def search_and_play(self, query: str) -> bool: ...
    def open_search_fallback(self, query: str) -> bool: ...
