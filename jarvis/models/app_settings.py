from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from jarvis.enums.llm_provider import LLMProvider


@dataclass(frozen=True, slots=True)
class AppSettings:
    llm_provider: LLMProvider
    language: str
    openai_api_key: str
    gemini_api_key: str
    anthropic_api_key: str
    startup_audio_path: Path
    success_audio_path: Path
