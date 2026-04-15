"""Resolves a natural-language query to an exact Spotify URI using the
public Web API for metadata only — no user login, no playback endpoints.

Token strategy: the Spotify Web Player issues anonymous access tokens via
`https://open.spotify.com/get_access_token`. We reuse that mechanism. These
tokens have enough scope to call `/v1/search` and nothing else (no playback,
no user data), which exactly matches what we need.

Best-result selection:
- If the top artist's normalized name equals the normalized query, pick
  the artist (user likely said an artist name).
- Else if there is a top track, pick it.
- Else if there is a top playlist, pick it.
- Otherwise, return None.
"""

from __future__ import annotations

import logging
import time
import unicodedata
from dataclasses import dataclass
from typing import Literal

import requests

LOGGER = logging.getLogger(__name__)

_ANON_TOKEN_URL = "https://open.spotify.com/get_access_token?reason=transport&productType=web_player"
_SEARCH_URL = "https://api.spotify.com/v1/search"
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
_TOKEN_REFRESH_MARGIN_S = 30

SearchKind = Literal["track", "artist", "playlist"]


@dataclass
class SearchResult:
    uri: str
    kind: SearchKind
    name: str
    subtitle: str


class SpotifySearchError(Exception):
    pass


class SpotifySearchProvider:
    def __init__(self) -> None:
        self._token: str | None = None
        self._token_expires_at: float = 0.0

    def search(self, query: str) -> SearchResult | None:
        query = query.strip()
        if not query:
            return None
        try:
            token = self._get_token()
        except SpotifySearchError as exc:
            LOGGER.warning("spotify_search_token_failed", extra={"event_data": {"error": str(exc)}})
            return None

        try:
            response = requests.get(
                _SEARCH_URL,
                params={"q": query, "type": "track,artist,playlist", "limit": 5, "market": "from_token"},
                headers={"Authorization": f"Bearer {token}", "User-Agent": _USER_AGENT},
                timeout=10,
            )
        except requests.RequestException as exc:
            LOGGER.warning("spotify_search_http_failed", extra={"event_data": {"error": str(exc)}})
            return None
        if response.status_code == 401:
            self._token = None
            LOGGER.warning("spotify_search_token_rejected")
            return None
        if response.status_code != 200:
            LOGGER.warning(
                "spotify_search_bad_status",
                extra={"event_data": {"status": response.status_code, "body": response.text[:200]}},
            )
            return None

        return self._pick_best(query, response.json())

    def _pick_best(self, query: str, payload: dict) -> SearchResult | None:
        normalized_query = self._normalize(query)

        artists = (payload.get("artists") or {}).get("items") or []
        tracks = (payload.get("tracks") or {}).get("items") or []
        playlists = [p for p in ((payload.get("playlists") or {}).get("items") or []) if p]

        if artists:
            top_artist = artists[0]
            if self._normalize(top_artist.get("name", "")) == normalized_query:
                return SearchResult(
                    uri=top_artist["uri"],
                    kind="artist",
                    name=top_artist.get("name", ""),
                    subtitle="artist",
                )

        if tracks:
            top_track = tracks[0]
            artist_names = ", ".join(a.get("name", "") for a in top_track.get("artists", []))
            return SearchResult(
                uri=top_track["uri"],
                kind="track",
                name=top_track.get("name", ""),
                subtitle=artist_names,
            )

        if artists:
            top_artist = artists[0]
            return SearchResult(
                uri=top_artist["uri"],
                kind="artist",
                name=top_artist.get("name", ""),
                subtitle="artist",
            )

        if playlists:
            top_playlist = playlists[0]
            return SearchResult(
                uri=top_playlist["uri"],
                kind="playlist",
                name=top_playlist.get("name", ""),
                subtitle=(top_playlist.get("owner") or {}).get("display_name", ""),
            )

        return None

    def _normalize(self, text: str) -> str:
        stripped = unicodedata.normalize("NFKD", text)
        return "".join(ch for ch in stripped if not unicodedata.combining(ch)).strip().lower()

    def _get_token(self) -> str:
        if self._token is not None and time.time() < self._token_expires_at - _TOKEN_REFRESH_MARGIN_S:
            return self._token
        try:
            response = requests.get(
                _ANON_TOKEN_URL,
                headers={"User-Agent": _USER_AGENT, "Accept": "application/json"},
                timeout=10,
            )
        except requests.RequestException as exc:
            raise SpotifySearchError(f"token request failed: {exc}") from exc
        if response.status_code != 200:
            raise SpotifySearchError(
                f"token endpoint returned {response.status_code}: {response.text[:200]}"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise SpotifySearchError(f"token response not JSON: {exc}") from exc
        access_token = payload.get("accessToken")
        expires_at_ms = payload.get("accessTokenExpirationTimestampMs")
        if not access_token or not expires_at_ms:
            raise SpotifySearchError("token payload missing fields")
        self._token = access_token
        self._token_expires_at = float(expires_at_ms) / 1000.0
        LOGGER.debug(
            "spotify_anon_token_acquired",
            extra={"event_data": {"expires_at": self._token_expires_at}},
        )
        return self._token
