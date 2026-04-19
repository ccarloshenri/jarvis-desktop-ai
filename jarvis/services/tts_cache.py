"""In-memory cache of pre-synthesized PCM for frequently-spoken phrases.

Rationale: each Piper invocation pays ~100-300ms of subprocess startup on
Windows plus the synthesis cost itself. For 1-2 word acknowledgements
("Certo.", "Pronto.") that startup *is* the latency — synthesis finishes
in under 50ms once Piper is running. Pre-warming those at boot turns a
~400ms latency into a memcpy + winsound call.

Keys are the output of format_for_speech — so "certo" and "Certo." hit
the same cache entry. Values are the already-synthesized PcmAudio.
"""

from __future__ import annotations

import logging
import threading
from typing import Iterable

from jarvis.services.tts_engine import PcmAudio, PiperEngine, TtsEngineError
from jarvis.utils.speech_formatter import chunk_for_speech, format_for_speech

LOGGER = logging.getLogger(__name__)


# Short acknowledgements Jarvis emits dozens of times per session. The list
# mirrors the canonical action acks the LLM is instructed to emit (see
# DECISION_SYSTEM_PROMPT in local_llm.py) so action turns hit the cache and
# play back with zero synthesis latency. Long, target-interpolated phrases
# ("Abrindo o Spotify, senhor.") aren't included because they vary per call
# and would balloon the cache without enough hit rate to justify it.
DEFAULT_WARM_PHRASES: tuple[str, ...] = (
    # Generic acks
    "Certo.",
    "Ok.",
    "Pronto.",
    "Claro.",
    "Entendido.",
    "Feito.",
    "Já estou fazendo isso.",
    "Um momento, senhor.",
    "Não consegui entender isso, senhor.",
    "Não consegui processar isso agora, senhor.",
    # Canonical action acks (must match DECISION_SYSTEM_PROMPT exactly)
    "Abrindo.",
    "Fechando.",
    "Tocando.",
    "Pesquisando.",
    "Buscando no YouTube.",
    "Buscando imagens.",
    "Buscando notícias.",
    "Abrindo o site.",
    "Abrindo o link.",
    # Common greetings / chat openers
    "Bom dia, senhor.",
    "Boa tarde, senhor.",
    "Boa noite, senhor.",
    "Olá, senhor.",
    "Olá, senhor. Em que posso ajudar?",
    "Sistema online. Em que posso ajudar, senhor?",
    "Às ordens, senhor.",
)


class TtsCache:
    def __init__(self) -> None:
        self._entries: dict[str, PcmAudio] = {}
        self._lock = threading.Lock()

    def get(self, text: str) -> PcmAudio | None:
        key = format_for_speech(text)
        if not key:
            return None
        with self._lock:
            return self._entries.get(key)

    def put(self, text: str, audio: PcmAudio) -> None:
        key = format_for_speech(text)
        if not key:
            return
        with self._lock:
            self._entries[key] = audio

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)

    def warm(
        self,
        engine: PiperEngine,
        phrases: Iterable[str] = DEFAULT_WARM_PHRASES,
    ) -> int:
        """Synthesize and store the given phrases. Returns success count.

        Each phrase is chunked the same way VoiceService chunks at speak
        time, then cached per chunk. Caching by full phrase would never
        hit when the speak path looks up chunk-by-chunk (e.g. a 2-sentence
        warm becomes 2 separate lookups).

        Safe to call from any thread; synthesis failures are logged but
        don't raise — a missed cache entry just means that chunk will be
        synthesized on demand the first time it's spoken.
        """
        stored = 0
        for raw in phrases:
            for chunk in chunk_for_speech(raw):
                key = format_for_speech(chunk)
                if not key:
                    continue
                with self._lock:
                    if key in self._entries:
                        continue
                try:
                    audio = engine.synthesize(key)
                except TtsEngineError as exc:
                    LOGGER.warning(
                        "tts_cache_warm_failed",
                        extra={"event_data": {"phrase": key, "error": str(exc)}},
                    )
                    continue
                with self._lock:
                    self._entries[key] = audio
                stored += 1
        LOGGER.info(
            "tts_cache_warmed",
            extra={"event_data": {"stored": stored, "total": len(self._entries)}},
        )
        return stored
