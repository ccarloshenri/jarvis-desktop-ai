from __future__ import annotations

from jarvis.enums.llm_provider import LLMProvider
from jarvis.interfaces.illm import ILLM
from jarvis.models.app_settings import AppSettings


class LLMFactory:
    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings

    def create(self, provider: LLMProvider | None = None) -> ILLM:
        selected_provider = provider or self._settings.llm_provider
        if selected_provider == LLMProvider.GPT:
            if not self._settings.openai_api_key:
                raise ValueError("OPENAI_API_KEY is required when LLM_PROVIDER=gpt.")
            return self._create_gpt()
        if selected_provider == LLMProvider.GEMINI:
            if not self._settings.gemini_api_key:
                raise ValueError("GEMINI_API_KEY is required when LLM_PROVIDER=gemini.")
            return self._create_gemini()
        if selected_provider == LLMProvider.CLAUDE:
            if not self._settings.anthropic_api_key:
                raise ValueError("ANTHROPIC_API_KEY is required when LLM_PROVIDER=claude.")
            return self._create_claude()
        if selected_provider == LLMProvider.NONE:
            return self._create_fallback()
        raise ValueError(f"Unsupported LLM provider '{selected_provider.value}'.")

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

        return FallbackLLM()
