from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from jarvis.enums.llm_provider import LLMProvider


@dataclass(frozen=True, slots=True)
class AppSettings:
    llm_provider: LLMProvider
    openai_api_key: str
    gemini_api_key: str
    anthropic_api_key: str
    asset_path: Path
    startup_audio_path: Path
    success_audio_path: Path
