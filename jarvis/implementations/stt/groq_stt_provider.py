"""Transcription via Groq's hosted Whisper endpoint.

Groq runs `whisper-large-v3-turbo` on their custom LPU hardware with
~100-200ms round-trip latency at the free tier (14400 req/day, 20 RPM
as of 2026-04). For our use case — one request per voice turn, short
audio (1-3s) — that fits comfortably and the accuracy jump over local
`small` int8 CPU Whisper is dramatic in PT-BR with English proper nouns.

This provider is opt-in: set `GROQ_API_KEY` (or `JARVIS_GROQ_API_KEY`)
AND `JARVIS_STT_PROVIDER=groq`. When the key is missing or a request
fails, the factory falls back to the local Whisper provider — this class
never retries or auto-fails-over internally, keeping the failure mode
predictable.
"""

from __future__ import annotations

import io
import logging
import time
import wave

import requests

from jarvis.interfaces.ispeech_to_text import UnintelligibleSpeechError
from jarvis.interfaces.istt_provider import CapturedAudio, ISTTProvider
from jarvis.utils.performance import Category, perf_log

LOGGER = logging.getLogger(__name__)


_LANGUAGE_TO_GROQ = {
    "pt-BR": "pt",
    "pt-br": "pt",
    "pt": "pt",
    "en-US": "en",
    "en-us": "en",
    "en": "en",
}

_GROQ_ENDPOINT = "https://api.groq.com/openai/v1/audio/transcriptions"

# Short prompt to bias toward PT-BR command style with English proper
# nouns. Same shape as the local WhisperSTTProvider prompt — Groq's API
# accepts a `prompt` field that plays the same role.
_BASE_PROMPT_PT = (
    "Comandos em portugues brasileiro, com nomes proprios em ingles. "
    "Toca Lana Del Rey. Toca Coldplay no Spotify. Toca uma musica do Queen. "
    "Pausa a musica. Abre o Spotify. Fecha o Discord. "
    "Pesquisa video do Neymar no YouTube. Manda mensagem para o Renan."
)
_BASE_PROMPT_EN = (
    "Voice commands. "
    "Play Lana Del Rey. Play Coldplay on Spotify. Play a Queen song. "
    "Pause the music. Open Spotify. Close Discord. "
    "Search a Neymar video on YouTube. Send a message to Renan."
)
_BASE_PROMPT_BY_LANG = {"pt": _BASE_PROMPT_PT, "en": _BASE_PROMPT_EN}

_DEFAULT_MODEL = "whisper-large-v3-turbo"
_REQUEST_TIMEOUT_S = 10.0


class GroqSTTError(Exception):
    """Raised on transport/HTTP errors — distinct from unintelligible
    speech so the caller can decide between retry, fallback, or speaking
    a generic error."""


class GroqSTTProvider(ISTTProvider):
    def __init__(
        self,
        api_key: str,
        model: str = _DEFAULT_MODEL,
        timeout_s: float = _REQUEST_TIMEOUT_S,
    ) -> None:
        if not api_key:
            raise ValueError("groq api key required")
        self._api_key = api_key
        self._model = model
        self._timeout_s = timeout_s

    @property
    def name(self) -> str:
        return "groq"

    def transcribe(self, audio: CapturedAudio, language: str) -> str:
        groq_lang = _LANGUAGE_TO_GROQ.get(language, "pt")
        wav_bytes = _pcm_to_wav(audio)
        prompt = _BASE_PROMPT_BY_LANG.get(groq_lang)
        files = {
            # Groq expects `file` as a multipart field; extension doesn't
            # matter for the server but `.wav` documents intent and keeps
            # server-side logs readable.
            "file": ("utterance.wav", wav_bytes, "audio/wav"),
        }
        data = {
            "model": self._model,
            "language": groq_lang,
            # Greedy — these are short commands, the temperature-fallback
            # chain from openai-whisper doesn't buy much here.
            "temperature": "0",
            # `text` is the smallest response shape Groq returns; we only
            # need the transcript so verbose JSON is wasted bytes.
            "response_format": "text",
        }
        if prompt:
            data["prompt"] = prompt
        headers = {"Authorization": f"Bearer {self._api_key}"}

        t0 = time.perf_counter()
        try:
            response = requests.post(
                _GROQ_ENDPOINT,
                headers=headers,
                files=files,
                data=data,
                timeout=self._timeout_s,
            )
        except requests.ConnectionError as exc:
            raise GroqSTTError(f"groq unreachable: {exc}") from exc
        except requests.Timeout as exc:
            raise GroqSTTError(f"groq timeout after {self._timeout_s}s") from exc
        except requests.RequestException as exc:
            raise GroqSTTError(str(exc)) from exc

        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        if not response.ok:
            body = response.text[:300]
            LOGGER.warning(
                "groq_http_error",
                extra={
                    "event_data": {
                        "status": response.status_code,
                        "body": body,
                        "elapsed_ms": elapsed_ms,
                    }
                },
            )
            raise GroqSTTError(f"HTTP {response.status_code}: {body[:200]}")

        text = response.text.strip()
        perf_log(
            Category.STT,
            "groq transcribe",
            elapsed_ms,
            chars=len(text),
            language=groq_lang,
            audio_ms=int(len(audio.pcm_bytes) / (audio.sample_rate * audio.sample_width) * 1000),
        )
        if not text:
            raise UnintelligibleSpeechError("groq returned empty transcript")
        return text


def _pcm_to_wav(audio: CapturedAudio) -> bytes:
    """Wrap raw PCM in a WAV container. Matches the local Whisper helper
    exactly — Groq accepts any ffmpeg-readable format and WAV is the
    cheapest to produce in pure Python."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(audio.channels)
        wav.setsampwidth(audio.sample_width)
        wav.setframerate(audio.sample_rate)
        wav.writeframes(audio.pcm_bytes)
    return buf.getvalue()
