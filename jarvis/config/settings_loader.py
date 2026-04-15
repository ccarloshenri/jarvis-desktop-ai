from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

from jarvis.config.strings import DEFAULT_LANGUAGE
from jarvis.enums.llm_provider import LLMProvider
from jarvis.models.app_settings import AppSettings
from jarvis.utils.path_resolver import PathResolver


class SettingsLoader:
    def __init__(self, project_root: Path) -> None:
        self._project_root = project_root
        self._resolver = PathResolver(project_root)

    def load(self) -> AppSettings:
        load_dotenv()
        provider_value = os.getenv("LLM_PROVIDER", LLMProvider.NONE.value).strip().lower()
        language = os.getenv("JARVIS_LANGUAGE", DEFAULT_LANGUAGE).strip() or DEFAULT_LANGUAGE
        return AppSettings(
            llm_provider=LLMProvider(provider_value),
            language=language,
            openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
            gemini_api_key=os.getenv("GEMINI_API_KEY", "").strip(),
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", "").strip(),
            startup_audio_path=self._resolver.resolve_speech(
                preferred="good_morning.mp3",
                fallbacks=("bom_dia_em_que_posso_ajudar.mp3",),
            ),
            success_audio_path=self._resolver.resolve_speech(
                preferred="understood.mp3",
                fallbacks=("tudo_pronto_senhor.mp3",),
            ),
        )
