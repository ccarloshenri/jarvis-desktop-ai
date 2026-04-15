from __future__ import annotations

from jarvis.services.credential_store import CredentialStore


class FakeKeyring:
    def __init__(self) -> None:
        self.store: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.store.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.store[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        self.store.pop((service, username), None)


class FailingKeyring:
    def get_password(self, service: str, username: str) -> str | None:
        raise RuntimeError("no backend")

    def set_password(self, service: str, username: str, password: str) -> None:
        raise RuntimeError("no backend")

    def delete_password(self, service: str, username: str) -> None:
        raise RuntimeError("no backend")


def test_credential_store_set_and_get() -> None:
    store = CredentialStore(backend=FakeKeyring())
    assert store.get("openai_api_key") is None
    assert store.set("openai_api_key", "sk-abc") is True
    assert store.get("openai_api_key") == "sk-abc"


def test_credential_store_delete() -> None:
    store = CredentialStore(backend=FakeKeyring())
    store.set("openai_api_key", "sk-abc")
    assert store.delete("openai_api_key") is True
    assert store.get("openai_api_key") is None


def test_credential_store_returns_none_for_empty_value() -> None:
    backend = FakeKeyring()
    backend.store[("jarvis-desktop-ai", "openai_api_key")] = "   "
    store = CredentialStore(backend=backend)
    assert store.get("openai_api_key") is None


def test_credential_store_handles_backend_errors() -> None:
    store = CredentialStore(backend=FailingKeyring())
    assert store.get("openai_api_key") is None
    assert store.set("openai_api_key", "sk-abc") is False
    assert store.delete("openai_api_key") is False
