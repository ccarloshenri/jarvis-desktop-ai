"""ElevenLabs TTS — most natural voice option available on the free
tier (~10k chars/mo). Produces raw PCM so the existing audio pipeline
doesn't need an MP3 decoder added just for this engine.

Uses the `eleven_multilingual_v2` model by default, which handles
Portuguese, English, Spanish and ~27 other languages from the same
voice. The default voice_id is `Daniel` (deep British male) — closest
match to the cinematic Jarvis feel without going through voice
cloning.
"""

from __future__ import annotations

import logging
import time

import requests

from jarvis.services.tts_engine import PcmAudio, TtsEngineError

LOGGER = logging.getLogger(__name__)


_ENDPOINT_TEMPLATE = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
# Daniel — deep British male, calm delivery. Closest to movie Jarvis
# in the default ElevenLabs voice library.
_DEFAULT_VOICE_ID = "onwK4e9ZLuTAKqWW03F9"
_DEFAULT_MODEL = "eleven_multilingual_v2"
_DEFAULT_TIMEOUT = 20.0
# PCM 22050 Hz signed 16-bit mono — matches what PiperEngine produces,
# so VoiceService + AudioPlayer consume it with zero adjustments.
_PCM_SAMPLE_RATE = 22050


class ElevenLabsTTSEngine:
    """Duck-typed to match PiperEngine — VoiceService only needs
    `synthesize(text) -> PcmAudio` and a `sample_rate` property.

    Voice settings are kept close to ElevenLabs defaults; we only nudge
    stability down and similarity up to favour the natural / human end
    of the delivery over the "announcer read" end. Stability too high
    produces the mono-tone robot vibe the user complained about on
    Groq playai.
    """

    def __init__(
        self,
        api_key: str,
        voice_id: str = _DEFAULT_VOICE_ID,
        model: str = _DEFAULT_MODEL,
        timeout_s: float = _DEFAULT_TIMEOUT,
        stability: float = 0.35,
        similarity_boost: float = 0.85,
        style: float = 0.15,
    ) -> None:
        if not api_key:
            raise TtsEngineError("elevenlabs requires an api key")
        self._api_key = api_key
        self._voice_id = voice_id
        self._model = model
        self._timeout_s = timeout_s
        self._stability = stability
        self._similarity_boost = similarity_boost
        self._style = style
        self._sample_rate = _PCM_SAMPLE_RATE

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    def synthesize(self, text: str) -> PcmAudio:
        if not text.strip():
            raise TtsEngineError("synthesize called with empty text")

        url = _ENDPOINT_TEMPLATE.format(voice_id=self._voice_id)
        headers = {
            "xi-api-key": self._api_key,
            "Accept": "audio/pcm",
            "Content-Type": "application/json",
        }
        # `output_format=pcm_22050` returns raw 16-bit signed LE PCM at
        # 22050 Hz, no container. Drops directly into PcmAudio without
        # wave parsing or ffmpeg decoding.
        params = {"output_format": f"pcm_{_PCM_SAMPLE_RATE}"}
        body = {
            "text": text,
            "model_id": self._model,
            "voice_settings": {
                "stability": self._stability,
                "similarity_boost": self._similarity_boost,
                "style": self._style,
                "use_speaker_boost": True,
            },
        }

        # Single retry on transient network failure — ElevenLabs is
        # usually reliable but a dropped TLS connection mid-session
        # shouldn't force the whole utterance through the SAPI
        # fallback. Non-5xx HTTP errors (e.g. 401 bad key, 429 quota)
        # are NOT retried because the second attempt would fail the
        # same way.
        t0 = time.perf_counter()
        response = None
        last_exc: Exception | None = None
        for attempt in range(2):
            try:
                response = requests.post(
                    url,
                    headers=headers,
                    params=params,
                    json=body,
                    timeout=self._timeout_s,
                )
                break
            except (requests.ConnectionError, requests.Timeout) as exc:
                last_exc = exc
                if attempt == 0:
                    time.sleep(0.25)
                    continue
            except requests.RequestException as exc:
                raise TtsEngineError(str(exc)) from exc
        if response is None:
            raise TtsEngineError(
                f"elevenlabs unreachable after retry: {last_exc}"
            ) from last_exc

        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        if not response.ok:
            body_text = response.text[:300]
            raise TtsEngineError(
                f"elevenlabs HTTP {response.status_code} after {elapsed_ms}ms: {body_text[:200]}"
            )

        pcm = response.content
        if not pcm:
            raise TtsEngineError("elevenlabs returned empty audio")

        LOGGER.debug(
            "elevenlabs_synthesized",
            extra={
                "event_data": {
                    "elapsed_ms": elapsed_ms,
                    "chars": len(text),
                    "bytes": len(pcm),
                    "voice_id": self._voice_id,
                }
            },
        )
        return PcmAudio(
            pcm_bytes=pcm,
            sample_rate=self._sample_rate,
            sample_width=2,
            channels=1,
        )
