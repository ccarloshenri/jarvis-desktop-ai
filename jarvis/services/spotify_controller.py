"""Controls the user's Spotify Desktop via the Spotify Web API.

Auth: OAuth PKCE (no client_secret, no credentials in repo). See
`SpotifyPkceAuth` for details.

Playback strategy:
1. Search the track via `GET /v1/search?type=track&limit=1`.
2. Discover the user's active device via `GET /v1/me/player/devices`.
   Prefer an already-active device. If none is active but a desktop device
   is available, transfer playback to it.
3. `PUT /v1/me/player/play` with `{ "uris": ["spotify:track:..."] }` targeted
   at that device. Spotify Desktop (already running on the user's machine)
   starts playing the correct track.

No UIA, no pywinauto, no keyboard simulation, no client_secret.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
import webbrowser
from pathlib import Path
from urllib.parse import quote_plus

import requests

from jarvis.services.spotify_auth import SpotifyAuthError, SpotifyPkceAuth

LOGGER = logging.getLogger(__name__)

_API_BASE = "https://api.spotify.com/v1"
_SPOTIFY_PROCESS_NAME = "spotify.exe"
_DEVICE_WAIT_SECONDS = 4.0
_DEVICE_POLL_INTERVAL = 0.4


class SpotifyController:
    def __init__(self, auth: SpotifyPkceAuth | None = None) -> None:
        self._auth = auth or SpotifyPkceAuth()

    def search(self, query: str, limit: int = 5) -> list[dict]:
        """Return top Spotify search results for `query` without playing.

        Used by the entity resolver to measure how well the spoken target
        matched real Spotify content. Distinct from search_and_play so the
        resolver never triggers playback as a side effect of validating.

        Returns an empty list on any error (auth unavailable, network,
        HTTP, empty results) — the resolver treats that as "no evidence".
        """
        query = query.strip()
        if not query:
            return []
        try:
            token = self._auth.get_access_token()
        except SpotifyAuthError as exc:
            LOGGER.debug(
                "spotify_search_auth_unavailable",
                extra={"event_data": {"error": str(exc)}},
            )
            return []
        try:
            response = requests.get(
                f"{_API_BASE}/search",
                params={"q": query, "type": "track", "limit": max(1, min(limit, 10))},
                headers={"Authorization": f"Bearer {token}"},
                timeout=5,
            )
        except requests.RequestException as exc:
            LOGGER.debug("spotify_search_failed", extra={"event_data": {"error": str(exc)}})
            return []
        if response.status_code != 200:
            return []
        items = response.json().get("tracks", {}).get("items", []) or []
        return [
            {
                "uri": item.get("uri", ""),
                "name": item.get("name", ""),
                "artist": ", ".join(a.get("name", "") for a in item.get("artists", [])),
            }
            for item in items
        ]

    def search_and_play(self, query: str) -> bool:
        query = query.strip()
        if not query:
            return False

        try:
            token = self._auth.get_access_token()
        except SpotifyAuthError as exc:
            LOGGER.warning("spotify_auth_unavailable", extra={"event_data": {"error": str(exc)}})
            return False

        track = self._search_first_track(token, query)
        if track is None:
            LOGGER.warning("spotify_search_no_results", extra={"event_data": {"query": query}})
            return False

        device_id = self._ensure_active_device(token)
        if device_id is None:
            LOGGER.warning("spotify_no_device_available")
            return False

        if not self._play_track(token, device_id, track["uri"]):
            return False

        LOGGER.info(
            "spotify_played",
            extra={
                "event_data": {
                    "query": query,
                    "track": track["name"],
                    "artist": track["artist"],
                }
            },
        )
        return True

    def _search_first_track(self, token: str, query: str) -> dict | None:
        try:
            response = requests.get(
                f"{_API_BASE}/search",
                params={"q": query, "type": "track", "limit": 1},
                headers={"Authorization": f"Bearer {token}"},
                timeout=10,
            )
        except requests.RequestException as exc:
            LOGGER.warning("spotify_search_failed", extra={"event_data": {"error": str(exc)}})
            return None
        if response.status_code != 200:
            LOGGER.warning(
                "spotify_search_http_error",
                extra={"event_data": {"status": response.status_code, "body": response.text[:200]}},
            )
            return None
        items = response.json().get("tracks", {}).get("items", [])
        if not items:
            return None
        first = items[0]
        return {
            "uri": first["uri"],
            "name": first.get("name", ""),
            "artist": ", ".join(a.get("name", "") for a in first.get("artists", [])),
        }

    def _ensure_active_device(self, token: str) -> str | None:
        """Return a device_id to play on, starting the desktop app if needed."""
        device = self._pick_device(token)
        if device is not None:
            return device["id"]

        self._launch_desktop_app()
        deadline = time.perf_counter() + _DEVICE_WAIT_SECONDS
        while time.perf_counter() < deadline:
            device = self._pick_device(token)
            if device is not None:
                return device["id"]
            time.sleep(_DEVICE_POLL_INTERVAL)
        return None

    def _pick_device(self, token: str) -> dict | None:
        try:
            response = requests.get(
                f"{_API_BASE}/me/player/devices",
                headers={"Authorization": f"Bearer {token}"},
                timeout=8,
            )
        except requests.RequestException:
            return None
        if response.status_code != 200:
            return None
        devices = response.json().get("devices", [])
        if not devices:
            return None
        for device in devices:
            if device.get("is_active"):
                return device
        for device in devices:
            if device.get("type", "").lower() == "computer":
                return device
        return devices[0]

    def _launch_desktop_app(self) -> None:
        if sys.platform != "win32":
            return
        exe = self._resolve_spotify_exe()
        try:
            if exe is not None:
                subprocess.Popen([str(exe)], close_fds=True)
            else:
                os.startfile("spotify:")  # type: ignore[attr-defined]
        except Exception as exc:
            LOGGER.debug("spotify_launch_failed", extra={"event_data": {"error": str(exc)}})

    def _resolve_spotify_exe(self) -> Path | None:
        candidates = [
            Path(os.environ.get("APPDATA", "")) / "Spotify" / "Spotify.exe",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WindowsApps" / "Spotify.exe",
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return None

    def _play_track(self, token: str, device_id: str, track_uri: str) -> bool:
        try:
            response = requests.put(
                f"{_API_BASE}/me/player/play",
                params={"device_id": device_id},
                json={"uris": [track_uri]},
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                timeout=10,
            )
        except requests.RequestException as exc:
            LOGGER.warning("spotify_play_failed", extra={"event_data": {"error": str(exc)}})
            return False
        if response.status_code in (200, 202, 204):
            return True
        LOGGER.warning(
            "spotify_play_http_error",
            extra={"event_data": {"status": response.status_code, "body": response.text[:200]}},
        )
        return False

    def open_search_fallback(self, query: str) -> bool:
        """Fallback: just open Spotify search via URI. Used when API is unavailable."""
        try:
            if sys.platform == "win32":
                os.startfile(f"spotify:search:{query}")  # type: ignore[attr-defined]
            else:
                webbrowser.open(f"https://open.spotify.com/search/{quote_plus(query)}")
            return True
        except OSError:
            return False
