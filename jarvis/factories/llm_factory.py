from __future__ import annotations

import logging

from jarvis.config.strings import Strings
from jarvis.enums.llm_provider import LLMProvider
from jarvis.interfaces.illm import ILLM
from jarvis.models.app_settings import AppSettings

LOGGER = logging.getLogger(__name__)


class LLMFactory:
    def __init__(self, settings: AppSettings, strings: Strings) -> None:
        self._settings = settings
        self._strings = strings

    def create(self, provider: LLMProvider | None = None) -> ILLM:
        selected_provider = provider or self._settings.llm_provider
        key_present = self._has_key(selected_provider)
        LOGGER.info(
            "llm_factory_create",
            extra={
                "event_data": {
                    "provider": selected_provider.value,
                    "key_present": key_present,
                }
            },
        )

        try:
            llm = self._instantiate(selected_provider)
        except Exception as exc:
            LOGGER.warning(
                "llm_factory_instantiation_failed",
                extra={
                    "event_data": {
                        "provider": selected_provider.value,
                        "error": str(exc),
                    }
                },
            )
            llm = self._create_fallback()

        LOGGER.info(
            "llm_factory_selected",
            extra={
                "event_data": {
                    "provider": selected_provider.value,
                    "class": type(llm).__name__,
                    "is_fallback": llm.is_fallback,
                }
            },
        )
        return llm

    def _instantiate(self, provider: LLMProvider) -> ILLM:
        if provider == LLMProvider.GPT:
            if not self._settings.openai_api_key:
                return self._create_fallback()
            return self._create_gpt()
        if provider == LLMProvider.GEMINI:
            if not self._settings.gemini_api_key:
                return self._create_fallback()
            return self._create_gemini()
        if provider == LLMProvider.CLAUDE:
            if not self._settings.anthropic_api_key:
                return self._create_fallback()
            return self._create_claude()
        if provider == LLMProvider.NONE:
            return self._create_fallback()
        raise ValueError(f"Unsupported LLM provider '{provider.value}'.")

    def _has_key(self, provider: LLMProvider) -> bool:
        if provider == LLMProvider.GPT:
            return bool(self._settings.openai_api_key)
        if provider == LLMProvider.GEMINI:
            return bool(self._settings.gemini_api_key)
        if provider == LLMProvider.CLAUDE:
            return bool(self._settings.anthropic_api_key)
        return False

    def _create_gpt(self) -> ILLM:
        from jarvis.implementations.llm.gpt_llm import GPTLLM

        return GPTLLM(api_key=self._settings.openai_api_key)

    def _create_gemini(self) -> ILLM:
        from jarvis.implementations.llm.gemini_llm import GeminiLLM

        return GeminiLLM(api_key=self._settings.gemini_api_key)

    def _create_claude(self) -> ILLM:
        from jarvis.implementations.llm.claude_llm import ClaudeLLM

        return ClaudeLLM(api_key=self._settings.anthropic_api_key)

    def _create_fallback(self) -> ILLM:
        from jarvis.implementations.llm.fallback_llm import FallbackLLM

        return FallbackLLM(strings=self._strings)
