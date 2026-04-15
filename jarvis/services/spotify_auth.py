"""Spotify OAuth PKCE flow — no client_secret required.

Flow:
1. First call: generate verifier/challenge, open browser to Spotify authorize
   page, run a loopback HTTP server on 127.0.0.1:8765 to catch the redirect,
   exchange the code for access+refresh tokens, persist to disk.
2. Subsequent calls: load tokens from disk; if expired, refresh using the
   refresh_token (still no client_secret).

Token file: ~/.jarvis/spotify_token.json
"""

from __future__ import annotations

import base64
import hashlib
import http.server
import json
import logging
import os
import secrets
import threading
import time
import urllib.parse
import webbrowser
from pathlib import Path

import requests

LOGGER = logging.getLogger(__name__)

_AUTH_URL = "https://accounts.spotify.com/authorize"
_TOKEN_URL = "https://accounts.spotify.com/api/token"
_REDIRECT_HOST = "127.0.0.1"
_REDIRECT_PORT = 8765
_REDIRECT_URI = f"http://{_REDIRECT_HOST}:{_REDIRECT_PORT}/callback"
_SCOPES = "user-modify-playback-state user-read-playback-state"
_REFRESH_MARGIN_S = 60


class SpotifyAuthError(Exception):
    pass


class SpotifyPkceAuth:
    def __init__(self, client_id: str | None = None, token_path: Path | None = None) -> None:
        self._client_id = client_id or os.environ.get("SPOTIFY_CLIENT_ID", "").strip()
        self._token_path = token_path or Path.home() / ".jarvis" / "spotify_token.json"

    def get_access_token(self) -> str:
        if not self._client_id:
            raise SpotifyAuthError(
                "SPOTIFY_CLIENT_ID não configurado. Registre um app em "
                "https://developer.spotify.com/dashboard e adicione o Client ID ao .env."
            )
        token = self._load_token()
        if token is None:
            token = self._run_authorization_flow()
        elif token["expires_at"] - _REFRESH_MARGIN_S < time.time():
            token = self._refresh(token["refresh_token"])
        return token["access_token"]

    def _load_token(self) -> dict | None:
        if not self._token_path.exists():
            return None
        try:
            return json.loads(self._token_path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def _save_token(self, token: dict) -> None:
        self._token_path.parent.mkdir(parents=True, exist_ok=True)
        self._token_path.write_text(json.dumps(token), encoding="utf-8")

    def _run_authorization_flow(self) -> dict:
        verifier = secrets.token_urlsafe(64)[:96]
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .rstrip(b"=")
            .decode()
        )
        state = secrets.token_urlsafe(16)

        params = {
            "client_id": self._client_id,
            "response_type": "code",
            "redirect_uri": _REDIRECT_URI,
            "scope": _SCOPES,
            "code_challenge_method": "S256",
            "code_challenge": challenge,
            "state": state,
        }
        authorize_url = f"{_AUTH_URL}?{urllib.parse.urlencode(params)}"

        code_holder: dict[str, str] = {}

        class _Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                parsed = urllib.parse.urlparse(self.path)
                query = urllib.parse.parse_qs(parsed.query)
                if parsed.path != "/callback":
                    self.send_response(404)
                    self.end_headers()
                    return
                if query.get("state", [""])[0] != state:
                    self.send_response(400)
                    self.end_headers()
                    self.wfile.write(b"state mismatch")
                    return
                if "error" in query:
                    code_holder["error"] = query["error"][0]
                elif "code" in query:
                    code_holder["code"] = query["code"][0]
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(
                    b"<html><body><h2>Jarvis: Spotify conectado.</h2>"
                    b"<p>Pode fechar essa aba.</p></body></html>"
                )

            def log_message(self, *_args) -> None:  # silence stdout
                return

        server = http.server.HTTPServer((_REDIRECT_HOST, _REDIRECT_PORT), _Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            LOGGER.info("spotify_auth_browser_open")
            webbrowser.open(authorize_url)
            deadline = time.time() + 180
            while time.time() < deadline and "code" not in code_holder and "error" not in code_holder:
                time.sleep(0.2)
        finally:
            server.shutdown()
            server.server_close()

        if "error" in code_holder:
            raise SpotifyAuthError(f"Spotify authorization denied: {code_holder['error']}")
        if "code" not in code_holder:
            raise SpotifyAuthError("Spotify authorization timed out.")

        return self._exchange_code(code_holder["code"], verifier)

    def _exchange_code(self, code: str, verifier: str) -> dict:
        response = requests.post(
            _TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": _REDIRECT_URI,
                "client_id": self._client_id,
                "code_verifier": verifier,
            },
            timeout=15,
        )
        if response.status_code != 200:
            raise SpotifyAuthError(f"token exchange failed: {response.status_code} {response.text}")
        payload = response.json()
        token = {
            "access_token": payload["access_token"],
            "refresh_token": payload.get("refresh_token", ""),
            "expires_at": time.time() + int(payload.get("expires_in", 3600)),
        }
        self._save_token(token)
        LOGGER.info("spotify_auth_token_acquired")
        return token

    def _refresh(self, refresh_token: str) -> dict:
        response = requests.post(
            _TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": self._client_id,
            },
            timeout=15,
        )
        if response.status_code != 200:
            LOGGER.warning(
                "spotify_auth_refresh_failed",
                extra={"event_data": {"status": response.status_code}},
            )
            return self._run_authorization_flow()
        payload = response.json()
        token = {
            "access_token": payload["access_token"],
            "refresh_token": payload.get("refresh_token", refresh_token),
            "expires_at": time.time() + int(payload.get("expires_in", 3600)),
        }
        self._save_token(token)
        return token
