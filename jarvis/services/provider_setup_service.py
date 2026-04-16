from __future__ import annotations

import logging
from dataclasses import replace

from PySide6.QtWidgets import QDialog, QWidget

from jarvis.enums.llm_provider import LLMProvider
from jarvis.models.app_settings import AppSettings
from jarvis.services.credential_store import (
    ANTHROPIC_KEY_USERNAME,
    CredentialStore,
    GEMINI_KEY_USERNAME,
    OPENAI_KEY_USERNAME,
)
from jarvis.services.provider_config import ProviderConfig

LOGGER = logging.getLogger(__name__)


_KEY_USERNAMES: dict[LLMProvider, str] = {
    LLMProvider.GPT: OPENAI_KEY_USERNAME,
    LLMProvider.GEMINI: GEMINI_KEY_USERNAME,
    LLMProvider.CLAUDE: ANTHROPIC_KEY_USERNAME,
}


class ProviderSetupService:
    def __init__(
        self,
        credential_store: CredentialStore | None = None,
        provider_config: ProviderConfig | None = None,
    ) -> None:
        self._credential_store = credential_store or CredentialStore()
        self._provider_config = provider_config or ProviderConfig()

    @property
    def credential_store(self) -> CredentialStore:
        return self._credential_store

    @property
    def provider_config(self) -> ProviderConfig:
        return self._provider_config

    def resolve_active_provider(self, env_settings: AppSettings) -> LLMProvider:
        persisted = self._provider_config.load_active_provider()
        if persisted is not None:
            return persisted
        return env_settings.llm_provider

    def load_stored_key(self, provider: LLMProvider) -> str:
        username = _KEY_USERNAMES.get(provider)
        if username is None:
            return ""
        return self._credential_store.get(username) or ""

    def bootstrap_settings(self, env_settings: AppSettings, parent: QWidget | None = None) -> AppSettings:
        provider = self.resolve_active_provider(env_settings)
        settings = replace(env_settings, llm_provider=provider)
        settings = self._apply_stored_key(settings, provider)
        LOGGER.info(
            "provider_bootstrap",
            extra={
                "event_data": {
                    "resolved_provider": provider.value,
                    "key_loaded": bool(self._key_for(settings, provider)),
                    "needs_dialog": self._needs_dialog(settings, provider),
                }
            },
        )

        if not self._needs_dialog(settings, provider):
            return settings

        choice = self.open_dialog(current_provider=provider, parent=parent)
        if choice is None:
            LOGGER.warning("provider_setup_cancelled")
            return settings
        return self.apply_choice(env_settings, choice)

    def open_dialog(
        self,
        current_provider: LLMProvider | None = None,
        parent: QWidget | None = None,
    ) -> "ProviderChoice | None":
        from jarvis.ui.provider_setup_dialog import ProviderSetupDialog

        existing = {p: self.load_stored_key(p) for p in _KEY_USERNAMES if self.load_stored_key(p)}
        dialog = ProviderSetupDialog(
            parent=parent,
            initial_provider=current_provider,
            existing_keys=existing,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            return dialog.choice
        return None

    def apply_choice(self, env_settings: AppSettings, choice: "ProviderChoice") -> AppSettings:
        self._provider_config.save_active_provider(choice.provider)
        username = _KEY_USERNAMES.get(choice.provider)
        stored = False
        if username is not None and choice.api_key:
            stored = self._credential_store.set(username, choice.api_key)
        settings = replace(env_settings, llm_provider=choice.provider)
        settings = self._apply_stored_key(settings, choice.provider, fallback_key=choice.api_key)
        LOGGER.info(
            "provider_apply_choice",
            extra={
                "event_data": {
                    "provider": choice.provider.value,
                    "key_stored_in_keyring": stored,
                    "key_loaded_into_settings": bool(self._key_for(settings, choice.provider)),
                }
            },
        )
        return settings

    def clear_current_provider(self) -> None:
        current = self._provider_config.load_active_provider()
        if current is None:
            return
        username = _KEY_USERNAMES.get(current)
        if username is not None:
            self._credential_store.delete(username)
        self._provider_config.clear()

    def _needs_dialog(self, settings: AppSettings, provider: LLMProvider) -> bool:
        if provider not in _KEY_USERNAMES:
            return False
        return not self._key_for(settings, provider)

    def _apply_stored_key(
        self,
        settings: AppSettings,
        provider: LLMProvider,
        fallback_key: str = "",
    ) -> AppSettings:
        if provider == LLMProvider.GPT:
            key = self.load_stored_key(provider) or settings.openai_api_key or fallback_key
            return replace(settings, openai_api_key=key)
        if provider == LLMProvider.GEMINI:
            key = self.load_stored_key(provider) or settings.gemini_api_key or fallback_key
            return replace(settings, gemini_api_key=key)
        if provider == LLMProvider.CLAUDE:
            key = self.load_stored_key(provider) or settings.anthropic_api_key or fallback_key
            return replace(settings, anthropic_api_key=key)
        return settings

    def _key_for(self, settings: AppSettings, provider: LLMProvider) -> str:
        if provider == LLMProvider.GPT:
            return settings.openai_api_key
        if provider == LLMProvider.GEMINI:
            return settings.gemini_api_key
        if provider == LLMProvider.CLAUDE:
            return settings.anthropic_api_key
        return ""


# Re-export for callers
from jarvis.ui.provider_setup_dialog import ProviderChoice  # noqa: E402
