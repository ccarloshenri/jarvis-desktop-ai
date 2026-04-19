from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AppSettings:
    language: str
    debug: bool
    spotify_client_id: str = ""
    music_provider: str = "spotify"  # "spotify" or "soundcloud" (SC coming soon)
    # Supported values: "lm_studio" (local), "groq", "openai",
    # "anthropic", "gemini". Settings dialog exposes all of them;
    # missing-credential fallback handled in the factory.
    llm_provider: str = "lm_studio"
    lm_studio_url: str = "http://localhost:1234/v1"
    lm_studio_model: str = "qwen2.5-3b-instruct"
    groq_llm_model: str = "llama-3.3-70b-versatile"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-3-5-haiku-latest"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"
    stt_provider: str = "whisper"
    groq_api_key: str = ""
    groq_stt_model: str = "whisper-large-v3-turbo"
    whisper_model: str = "small"
    whisper_device: str = "auto"
    whisper_compute_type: str = "int8"
    whisper_beam_size: int = 3
    wake_word_enabled: bool = True
    wake_word_model: str = "hey_jarvis"
    wake_word_threshold: float = 0.15
    wake_word_debug: bool = False
    llm_streaming: bool = True
    piper_persistent: bool = True
    tts_provider: str = "piper"  # "piper", "groq", "elevenlabs"
    groq_tts_model: str = "playai-tts"
    groq_tts_voice: str = "Atlas-PlayAI"
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = "onwK4e9ZLuTAKqWW03F9"  # Daniel, British deep male
    elevenlabs_model: str = "eleven_multilingual_v2"
    vad_backend: str = "silero"  # "silero" or "rms"
    # Lowered from 0.5 — the default was flagging unvoiced consonants
    # (/p/, /t/, /k/, /s/) as silence mid-sentence, which combined
    # with short silence windows cut off long commands. 0.35 keeps
    # the VAD firmly pegged to "speech" across natural phonetics.
    vad_threshold: float = 0.35
