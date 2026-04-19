from __future__ import annotations

import logging
from typing import Protocol

LOGGER = logging.getLogger(__name__)

SERVICE_NAME = "jarvis-desktop-ai"
SPOTIFY_CLIENT_ID_USERNAME = "spotify_client_id"
GROQ_API_KEY_USERNAME = "groq_api_key"
ELEVENLABS_API_KEY_USERNAME = "elevenlabs_api_key"
ELEVENLABS_VOICE_ID_USERNAME = "elevenlabs_voice_id"


class KeyringBackend(Protocol):
    def get_password(self, service: str, username: str) -> str | None: ...
    def set_password(self, service: str, username: str, password: str) -> None: ...
    def delete_password(self, service: str, username: str) -> None: ...


class CredentialStore:
    """Minimal keyring wrapper. Used only for the Spotify client_id so the
    user can set it via the settings dialog without editing .env by hand."""

    def __init__(self, backend: KeyringBackend | None = None, service: str = SERVICE_NAME) -> None:
        self._service = service
        self._backend = backend if backend is not None else self._load_default_backend()

    def get(self, key: str) -> str | None:
        if self._backend is None:
            return None
        try:
            value = self._backend.get_password(self._service, key)
        except Exception as exc:
            LOGGER.warning("credential_store_get_failed", extra={"event_data": {"error": str(exc), "key": key}})
            return None
        return value.strip() if isinstance(value, str) and value.strip() else None

    def set(self, key: str, value: str) -> bool:
        if self._backend is None:
            return False
        try:
            self._backend.set_password(self._service, key, value)
            return True
        except Exception as exc:
            LOGGER.warning("credential_store_set_failed", extra={"event_data": {"error": str(exc), "key": key}})
            return False

    def delete(self, key: str) -> bool:
        if self._backend is None:
            return False
        try:
            self._backend.delete_password(self._service, key)
            return True
        except Exception as exc:
            LOGGER.warning("credential_store_delete_failed", extra={"event_data": {"error": str(exc), "key": key}})
            return False

    @staticmethod
    def _load_default_backend() -> KeyringBackend | None:
        try:
            import keyring
        except ImportError:
            LOGGER.warning("keyring_not_installed")
            return None
        return keyring  # type: ignore[return-value]
