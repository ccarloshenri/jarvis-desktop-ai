from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

from jarvis.config.strings import DEFAULT_LANGUAGE
from jarvis.models.app_settings import AppSettings
from jarvis.services.credential_store import (
    CredentialStore,
    ANTHROPIC_API_KEY_USERNAME,
    ELEVENLABS_API_KEY_USERNAME,
    ELEVENLABS_VOICE_ID_USERNAME,
    GEMINI_API_KEY_USERNAME,
    GROQ_API_KEY_USERNAME,
    OPENAI_API_KEY_USERNAME,
    SPOTIFY_CLIENT_ID_USERNAME,
)


def _parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on", "debug"}


def _parse_float(value: str, *, default: float) -> float:
    cleaned = (value or "").strip()
    if not cleaned:
        return default
    try:
        return float(cleaned)
    except ValueError:
        return default


def _parse_int(value: str, *, default: int) -> int:
    cleaned = (value or "").strip()
    if not cleaned:
        return default
    try:
        return int(cleaned)
    except ValueError:
        return default


class SettingsLoader:
    def __init__(self, project_root: Path) -> None:
        self._project_root = project_root

    def load(self) -> AppSettings:
        load_dotenv()
        language = os.getenv("JARVIS_LANGUAGE", DEFAULT_LANGUAGE).strip() or DEFAULT_LANGUAGE
        debug = _parse_bool(os.getenv("JARVIS_DEBUG", ""))
        llm_provider = (
            os.getenv("JARVIS_LLM_PROVIDER", "lm_studio").strip().lower()
            or "lm_studio"
        )
        lm_studio_url = (
            os.getenv("JARVIS_LM_STUDIO_URL", "http://localhost:1234/v1").strip()
            or "http://localhost:1234/v1"
        )
        lm_studio_model = (
            os.getenv("JARVIS_LM_STUDIO_MODEL", "qwen2.5-3b-instruct").strip()
            or "qwen2.5-3b-instruct"
        )
        groq_llm_model = (
            os.getenv("JARVIS_GROQ_LLM_MODEL", "llama-3.3-70b-versatile").strip()
            or "llama-3.3-70b-versatile"
        )
        # OpenAI / Anthropic / Gemini — same pattern as the other
        # credentials: env wins, keyring fills in what the settings
        # dialog saved. Never reads raw strings from source control.
        store = CredentialStore()
        openai_api_key = (
            os.getenv("OPENAI_API_KEY", "").strip()
            or os.getenv("JARVIS_OPENAI_API_KEY", "").strip()
            or store.get(OPENAI_API_KEY_USERNAME)
            or ""
        )
        openai_model = (
            os.getenv("JARVIS_OPENAI_MODEL", "gpt-4o-mini").strip()
            or "gpt-4o-mini"
        )
        anthropic_api_key = (
            os.getenv("ANTHROPIC_API_KEY", "").strip()
            or os.getenv("JARVIS_ANTHROPIC_API_KEY", "").strip()
            or store.get(ANTHROPIC_API_KEY_USERNAME)
            or ""
        )
        anthropic_model = (
            os.getenv("JARVIS_ANTHROPIC_MODEL", "claude-3-5-haiku-latest").strip()
            or "claude-3-5-haiku-latest"
        )
        gemini_api_key = (
            os.getenv("GEMINI_API_KEY", "").strip()
            or os.getenv("JARVIS_GEMINI_API_KEY", "").strip()
            or store.get(GEMINI_API_KEY_USERNAME)
            or ""
        )
        gemini_model = (
            os.getenv("JARVIS_GEMINI_MODEL", "gemini-2.0-flash").strip()
            or "gemini-2.0-flash"
        )
        stt_provider = (os.getenv("JARVIS_STT_PROVIDER", "whisper").strip().lower() or "whisper")
        # GROQ_API_KEY is the convention used across Groq's own SDKs;
        # accept JARVIS_GROQ_API_KEY too so it can live alongside other
        # JARVIS_* vars in .env without awkward naming. Falls back to
        # keyring so the settings dialog can persist the key without
        # touching .env.
        groq_api_key = (
            os.getenv("GROQ_API_KEY", "").strip()
            or os.getenv("JARVIS_GROQ_API_KEY", "").strip()
        )
        if not groq_api_key:
            groq_api_key = CredentialStore().get(GROQ_API_KEY_USERNAME) or ""
        groq_stt_model = (
            os.getenv("JARVIS_GROQ_STT_MODEL", "whisper-large-v3-turbo").strip()
            or "whisper-large-v3-turbo"
        )
        whisper_model = os.getenv("JARVIS_WHISPER_MODEL", "small").strip() or "small"
        whisper_device = os.getenv("JARVIS_WHISPER_DEVICE", "auto").strip() or "auto"
        whisper_compute = os.getenv("JARVIS_WHISPER_COMPUTE", "int8").strip() or "int8"
        whisper_beam_size = _parse_int(os.getenv("JARVIS_WHISPER_BEAM_SIZE", ""), default=3)
        wake_word_enabled = _parse_bool(os.getenv("JARVIS_WAKE_WORD", "true"))
        wake_word_model = (
            os.getenv("JARVIS_WAKE_WORD_MODEL", "hey_jarvis").strip() or "hey_jarvis"
        )
        wake_word_threshold = _parse_float(
            os.getenv("JARVIS_WAKE_WORD_THRESHOLD", ""), default=0.15
        )
        wake_word_debug = _parse_bool(os.getenv("JARVIS_WAKE_WORD_DEBUG", ""))
        llm_streaming = _parse_bool(os.getenv("JARVIS_LLM_STREAMING", "true"))
        piper_persistent = _parse_bool(os.getenv("JARVIS_PIPER_PERSISTENT", "true"))
        tts_provider = (
            os.getenv("JARVIS_TTS_PROVIDER", "piper").strip().lower() or "piper"
        )
        groq_tts_model = (
            os.getenv("JARVIS_GROQ_TTS_MODEL", "playai-tts").strip() or "playai-tts"
        )
        groq_tts_voice = (
            os.getenv("JARVIS_GROQ_TTS_VOICE", "Atlas-PlayAI").strip() or "Atlas-PlayAI"
        )
        # ElevenLabs key: env wins, then keyring (set via Settings dialog),
        # so the UI can persist the key without the user editing .env.
        elevenlabs_api_key = os.getenv("ELEVENLABS_API_KEY", "").strip() or os.getenv(
            "JARVIS_ELEVENLABS_API_KEY", ""
        ).strip()
        if not elevenlabs_api_key:
            elevenlabs_api_key = (
                CredentialStore().get(ELEVENLABS_API_KEY_USERNAME) or ""
            )
        # Voice ID follows the same pattern: env overrides, keyring
        # persists dialog edits, default is Daniel (British deep male).
        elevenlabs_voice_id = os.getenv("JARVIS_ELEVENLABS_VOICE_ID", "").strip()
        if not elevenlabs_voice_id:
            elevenlabs_voice_id = (
                CredentialStore().get(ELEVENLABS_VOICE_ID_USERNAME)
                or "onwK4e9ZLuTAKqWW03F9"
            )
        elevenlabs_model = (
            os.getenv("JARVIS_ELEVENLABS_MODEL", "eleven_multilingual_v2").strip()
            or "eleven_multilingual_v2"
        )
        vad_backend = (os.getenv("JARVIS_VAD_BACKEND", "silero").strip().lower() or "silero")
        vad_threshold = _parse_float(os.getenv("JARVIS_VAD_THRESHOLD", ""), default=0.35)
        # Spotify client_id: env var takes priority; fall back to keyring
        # so the settings dialog can persist the value without editing .env.
        spotify_client_id = os.getenv("SPOTIFY_CLIENT_ID", "").strip()
        if not spotify_client_id:
            spotify_client_id = CredentialStore().get(SPOTIFY_CLIENT_ID_USERNAME) or ""
        music_provider = (
            os.getenv("JARVIS_MUSIC_PROVIDER", "spotify").strip().lower() or "spotify"
        )
        return AppSettings(
            language=language,
            debug=debug,
            spotify_client_id=spotify_client_id,
            music_provider=music_provider,
            llm_provider=llm_provider,
            lm_studio_url=lm_studio_url,
            lm_studio_model=lm_studio_model,
            groq_llm_model=groq_llm_model,
            openai_api_key=openai_api_key,
            openai_model=openai_model,
            anthropic_api_key=anthropic_api_key,
            anthropic_model=anthropic_model,
            gemini_api_key=gemini_api_key,
            gemini_model=gemini_model,
            stt_provider=stt_provider,
            groq_api_key=groq_api_key,
            groq_stt_model=groq_stt_model,
            whisper_model=whisper_model,
            whisper_device=whisper_device,
            whisper_compute_type=whisper_compute,
            whisper_beam_size=whisper_beam_size,
            wake_word_enabled=wake_word_enabled,
            wake_word_model=wake_word_model,
            wake_word_threshold=wake_word_threshold,
            wake_word_debug=wake_word_debug,
            llm_streaming=llm_streaming,
            piper_persistent=piper_persistent,
            tts_provider=tts_provider,
            groq_tts_model=groq_tts_model,
            groq_tts_voice=groq_tts_voice,
            elevenlabs_api_key=elevenlabs_api_key,
            elevenlabs_voice_id=elevenlabs_voice_id,
            elevenlabs_model=elevenlabs_model,
            vad_backend=vad_backend,
            vad_threshold=vad_threshold,
        )
