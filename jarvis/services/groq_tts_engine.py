"""Groq playai-tts synthesizer — OpenAI-compatible /v1/audio/speech.

Drop-in replacement for PiperEngine's `synthesize(text) -> PcmAudio`.
Returns WAV bytes from Groq, parses the header to extract PCM so the
rest of the audio pipeline (AudioPlayer, VoiceService chunking) works
unchanged.

Language caveat — as of 2026-04 playai-tts is English only. If you want
Jarvis to speak Portuguese, keep PiperEngine. If you switch to Groq,
flip JARVIS_LANGUAGE=en-US so the ack phrases and system prompts match
the voice; otherwise the British voice reads Portuguese phonemes and
sounds absurd.
"""

from __future__ import annotations

import io
import logging
import time
import wave

import requests

from jarvis.services.tts_engine import PcmAudio, TtsEngineError

LOGGER = logging.getLogger(__name__)


_ENDPOINT = "https://api.groq.com/openai/v1/audio/speech"
_DEFAULT_MODEL = "playai-tts"
_DEFAULT_VOICE = "Fritz-PlayAI"  # deep male, closest to movie Jarvis
_DEFAULT_TIMEOUT = 20.0


class GroqTTSEngine:
    """Thin HTTP client for Groq's TTS. Duck-typed to match PiperEngine
    — VoiceService only needs `synthesize(text) -> PcmAudio` and a
    `sample_rate` property, both of which we honour.
    """

    def __init__(
        self,
        api_key: str,
        model: str = _DEFAULT_MODEL,
        voice: str = _DEFAULT_VOICE,
        timeout_s: float = _DEFAULT_TIMEOUT,
    ) -> None:
        if not api_key:
            raise TtsEngineError("groq tts requires an api key")
        self._api_key = api_key
        self._model = model
        self._voice = voice
        self._timeout_s = timeout_s
        # Groq returns 48kHz mono by default. We don't need to query it;
        # it's fixed for playai-tts and the AudioPlayer handles arbitrary
        # sample rates via the WAV header anyway.
        self._sample_rate = 48000

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    def synthesize(self, text: str) -> PcmAudio:
        if not text.strip():
            raise TtsEngineError("synthesize called with empty text")
        payload = {
            "model": self._model,
            "voice": self._voice,
            "input": text,
            "response_format": "wav",
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        t0 = time.perf_counter()
        try:
            response = requests.post(
                _ENDPOINT, json=payload, headers=headers, timeout=self._timeout_s
            )
        except requests.ConnectionError as exc:
            raise TtsEngineError(f"groq tts unreachable: {exc}") from exc
        except requests.Timeout as exc:
            raise TtsEngineError(f"groq tts timeout after {self._timeout_s}s") from exc
        except requests.RequestException as exc:
            raise TtsEngineError(str(exc)) from exc

        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        if not response.ok:
            body = response.text[:400]
            raise TtsEngineError(
                f"groq tts HTTP {response.status_code} after {elapsed_ms}ms: {body[:200]}"
            )

        # Groq returns a full WAV file. We strip the header and keep the
        # raw PCM so downstream code (AudioPlayer, PcmAudio contract)
        # stays identical across Piper / Groq.
        try:
            pcm_bytes, sample_rate, sample_width, channels = _unpack_wav(response.content)
        except Exception as exc:
            raise TtsEngineError(f"groq tts returned unreadable wav: {exc}") from exc

        if not pcm_bytes:
            raise TtsEngineError("groq tts returned empty audio")

        self._sample_rate = sample_rate
        LOGGER.debug(
            "groq_tts_synthesized",
            extra={
                "event_data": {
                    "elapsed_ms": elapsed_ms,
                    "chars": len(text),
                    "bytes": len(pcm_bytes),
                    "sample_rate": sample_rate,
                }
            },
        )
        return PcmAudio(
            pcm_bytes=pcm_bytes,
            sample_rate=sample_rate,
            sample_width=sample_width,
            channels=channels,
        )


def _unpack_wav(data: bytes) -> tuple[bytes, int, int, int]:
    """Read `data` as a WAV file, return (pcm_bytes, sample_rate,
    sample_width, channels). Keeps the parsing honest rather than
    blindly slicing past a 44-byte header (some WAVs carry LIST/INFO
    chunks that push the data chunk further in)."""
    with wave.open(io.BytesIO(data), "rb") as wav:
        channels = wav.getnchannels()
        sample_width = wav.getsampwidth()
        sample_rate = wav.getframerate()
        frames = wav.readframes(wav.getnframes())
    return frames, sample_rate, sample_width, channels
