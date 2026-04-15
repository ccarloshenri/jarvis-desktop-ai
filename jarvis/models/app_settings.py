from __future__ import annotations

from dataclasses import dataclass

from jarvis.enums.llm_provider import LLMProvider


@dataclass(frozen=True, slots=True)
class AppSettings:
    llm_provider: LLMProvider
    language: str
    debug: bool
    openai_api_key: str
    gemini_api_key: str
    anthropic_api_key: str
    ollama_host: str
    ollama_model: str
