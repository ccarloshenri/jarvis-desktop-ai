from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

from jarvis.config.strings import DEFAULT_LANGUAGE
from jarvis.enums.llm_provider import LLMProvider
from jarvis.models.app_settings import AppSettings


def _parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on", "debug"}


class SettingsLoader:
    def __init__(self, project_root: Path) -> None:
        self._project_root = project_root

    def load(self) -> AppSettings:
        load_dotenv()
        provider_value = os.getenv("LLM_PROVIDER", LLMProvider.NONE.value).strip().lower()
        language = os.getenv("JARVIS_LANGUAGE", DEFAULT_LANGUAGE).strip() or DEFAULT_LANGUAGE
        debug = _parse_bool(os.getenv("JARVIS_DEBUG", ""))
        return AppSettings(
            llm_provider=LLMProvider(provider_value),
            language=language,
            debug=debug,
            openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
            gemini_api_key=os.getenv("GEMINI_API_KEY", "").strip(),
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", "").strip(),
        )
