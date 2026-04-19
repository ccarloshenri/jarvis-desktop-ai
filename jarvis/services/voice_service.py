"""Async TTS orchestrator — formats text, chunks it, synthesizes per chunk,
streams PCM to an AudioPlayer worker. speak() returns immediately.

Pipelining is what makes this fast in practice:

    text -> [format] -> [chunks] -> synth(chunk_1) -> player <<< chunk_1
                                     synth(chunk_2) ---|         chunk_2
                                     synth(chunk_3) ---|         chunk_3

The player plays chunk 1 *while* Piper is producing chunk 2. For a
3-sentence response, the user hears the first sentence within one
synth's worth of latency (~200-400ms) instead of waiting for the whole
response (~1-1.5s).

Two sources of "instant" output:
- Cache hits (short acks like "Certo.") skip Piper entirely.
- Pipelining (first chunk plays before later chunks are synthesized).

Fallback: on synth failure *before any audio has played*, we hand the
formatted text to the SAPI fallback so the user still gets a response.
Once we're mid-utterance the fallback stays idle to avoid voice-switching
mid-sentence.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass

from jarvis.interfaces.ispeech_events import ISpeechEvents
from jarvis.interfaces.itext_to_speech import ITextToSpeech
from jarvis.services.audio_player import AudioPlayer, PlaybackJob
from jarvis.services.tts_cache import TtsCache
from jarvis.services.tts_engine import PcmAudio, PiperEngine, TtsEngineError
from jarvis.utils.performance import Category, log, perf_log
from jarvis.utils.speech_formatter import chunk_for_speech, format_for_speech

LOGGER = logging.getLogger(__name__)


# Opportunistic cache threshold: only cache short chunks. Long chunks are
# unlikely to repeat verbatim (they contain interpolated targets), and
# unbounded caching would grow forever.
_CACHE_MAX_CHUNK_CHARS = 40


class VoiceServiceError(Exception):
    pass


_SHUTDOWN = object()


@dataclass(frozen=True, slots=True)
class _StandaloneText:
    text: str


@dataclass(frozen=True, slots=True)
class _StreamChunk:
    text: str


class _StreamEnd:
    """Sentinel type — sent through the queue to close the current stream."""


_STREAM_END = _StreamEnd()


class VoiceService(ITextToSpeech):
    def __init__(
        self,
        engine: PiperEngine,
        player: AudioPlayer,
        cache: TtsCache,
        speech_events: ISpeechEvents | None = None,
        fallback: ITextToSpeech | None = None,
    ) -> None:
        self._engine = engine
        self._player = player
        self._cache = cache
        self._speech_events = speech_events
        self._fallback = fallback
        self._queue: queue.Queue[object] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._running = False

    def start(self) -> None:
        if self._running:
            return
        self._player.start()
        self._running = True
        self._thread = threading.Thread(
            target=self._run, name="jarvis-tts-synth", daemon=True
        )
        self._thread.start()

    def speak(self, text: str) -> None:
        """Non-blocking. Returns as soon as the text is enqueued for synthesis.

        Multiple speak() calls stack in order — the synth worker drains them
        one utterance at a time. There is no "talk over ourselves" risk even
        under rapid calls.
        """
        if not text or not text.strip():
            return
        if not self._running:
            # Lazy-start so tests that don't call start() still work.
            self.start()
        self._queue.put(_StandaloneText(text))

    def speak_stream_chunk(self, text: str) -> None:
        """Add a chunk to an in-progress streaming utterance.

        The first chunk opens a streaming utterance — subsequent chunks
        extend it until `speak_stream_end()` closes it. Callers MUST NOT
        interleave `speak()` calls with `speak_stream_chunk` for the same
        utterance; the synth worker drops standalone speak() items that
        arrive mid-stream.
        """
        if not text or not text.strip():
            return
        if not self._running:
            self.start()
        self._queue.put(_StreamChunk(text))

    def speak_stream_end(self) -> None:
        """Close the current streaming utterance. Safe to call even when
        no chunks were submitted (the worker treats it as a no-op)."""
        if not self._running:
            return
        self._queue.put(_STREAM_END)

    def wait_idle(self, timeout: float | None = None) -> bool:
        """Block until the synth queue is drained and the player is silent."""
        start = time.perf_counter()
        while True:
            if self._queue.empty() and self._player.is_idle():
                return True
            if timeout is not None and (time.perf_counter() - start) >= timeout:
                return False
            # Cheap poll. We don't need tight timing here — this is only
            # used at shutdown and in tests.
            time.sleep(0.02)

    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        self._queue.put(_SHUTDOWN)
        thread = self._thread
        if thread is not None:
            thread.join(timeout=2.0)
        self._thread = None
        self._player.stop()

    def _run(self) -> None:
        while True:
            item = self._queue.get()
            if item is _SHUTDOWN:
                return
            try:
                if isinstance(item, _StandaloneText):
                    self._speak_one(item.text)
                elif isinstance(item, _StreamChunk):
                    self._speak_stream(first_chunk=item.text)
                elif isinstance(item, _StreamEnd):
                    # Stray end with no open stream — nothing to close.
                    log(Category.TTS, "stream_end received without open stream")
                else:
                    LOGGER.warning(
                        "voice_unknown_queue_item",
                        extra={"event_data": {"type": type(item).__name__}},
                    )
            except Exception:
                # A bug in the pipeline must not kill the worker — one bad
                # utterance shouldn't silence Jarvis for the rest of the
                # session. Log and continue.
                LOGGER.exception("voice_speak_failed")

    def _speak_one(self, text: str) -> None:
        formatted = format_for_speech(text)
        if not formatted:
            return
        chunks = chunk_for_speech(formatted)
        if not chunks:
            return

        log(Category.TTS, f"speaking: {formatted!r}", chunks=len(chunks))
        if self._speech_events is not None:
            try:
                self._speech_events.emit_speaking_started(formatted)
            except Exception:
                LOGGER.exception("voice_speaking_started_emit_failed")

        t0 = time.perf_counter()
        first_audio_ms: int | None = None
        cache_hits = 0
        synth_ms_total = 0
        any_enqueued = False
        try:
            for chunk in chunks:
                resolved = self._resolve_audio_timed(chunk)
                if resolved is None:
                    if not any_enqueued:
                        # Nothing played yet — hand the whole utterance to
                        # the SAPI fallback so the user still hears something.
                        self._fallback_speak(formatted)
                        return
                    # Mid-utterance failure: skip the chunk rather than
                    # switching voice models halfway through a sentence.
                    continue
                audio, synth_ms, cached = resolved
                if cached:
                    cache_hits += 1
                else:
                    synth_ms_total += synth_ms
                if first_audio_ms is None:
                    first_audio_ms = int((time.perf_counter() - t0) * 1000)
                    log(
                        Category.TTS,
                        "playback starting",
                        first_chunk=chunk[:80],
                        first_audio_ms=first_audio_ms,
                        cached=cached,
                    )
                self._player.enqueue(PlaybackJob(audio=audio, marker=chunk))
                any_enqueued = True

            if not any_enqueued:
                return

            self._player.wait_idle()
        finally:
            total_ms = int((time.perf_counter() - t0) * 1000)
            perf_log(
                Category.TTS,
                "utterance complete",
                total_ms,
                chars=len(formatted),
                chunks=len(chunks),
                cache_hits=cache_hits,
                synth_ms=synth_ms_total,
                first_audio_ms=first_audio_ms,
            )
            if self._speech_events is not None:
                try:
                    self._speech_events.emit_speaking_finished(formatted)
                except Exception:
                    LOGGER.exception("voice_speaking_finished_emit_failed")

    def _speak_stream(self, first_chunk: str) -> None:
        """Drain streaming chunks from the queue until _StreamEnd, synthesizing
        and enqueuing audio as each one arrives.

        The utterance boundary is a single streaming run: one speaking_started
        at first audio, one speaking_finished after the last chunk plays out.
        Individual chunk synth failures are skipped (log + continue) rather
        than aborting the whole stream — it's better to speak 80% of a
        sentence than nothing.
        """
        t0 = time.perf_counter()
        first_audio_ms: int | None = None
        started_emitted = False
        any_enqueued = False
        full_text_parts: list[str] = []
        chunks_seen = 0
        cache_hits = 0
        synth_ms_total = 0

        def process(raw: str) -> None:
            nonlocal first_audio_ms, started_emitted, any_enqueued
            nonlocal chunks_seen, cache_hits, synth_ms_total
            formatted = format_for_speech(raw)
            if not formatted:
                return
            pieces = chunk_for_speech(formatted)
            if not pieces:
                return
            full_text_parts.append(formatted)
            chunks_seen += len(pieces)
            for piece in pieces:
                resolved = self._resolve_audio_timed(piece)
                if resolved is None:
                    # Skip this piece — keep the stream alive rather than
                    # aborting mid-utterance. The synth error is already
                    # logged inside _resolve_audio_timed.
                    continue
                audio, synth_ms, cached = resolved
                if cached:
                    cache_hits += 1
                else:
                    synth_ms_total += synth_ms
                if not started_emitted:
                    started_emitted = True
                    if self._speech_events is not None:
                        try:
                            self._speech_events.emit_speaking_started(formatted)
                        except Exception:
                            LOGGER.exception("voice_speaking_started_emit_failed")
                if first_audio_ms is None:
                    first_audio_ms = int((time.perf_counter() - t0) * 1000)
                    log(
                        Category.TTS,
                        "stream playback starting",
                        first_chunk=piece[:80],
                        first_audio_ms=first_audio_ms,
                        cached=cached,
                    )
                self._player.enqueue(PlaybackJob(audio=audio, marker=piece))
                any_enqueued = True

        try:
            process(first_chunk)
            while True:
                item = self._queue.get()
                if item is _SHUTDOWN:
                    # Treat shutdown mid-stream like a forced end. The outer
                    # run loop will exit on the next iteration.
                    self._queue.put(_SHUTDOWN)
                    break
                if isinstance(item, _StreamEnd):
                    break
                if isinstance(item, _StreamChunk):
                    process(item.text)
                    continue
                if isinstance(item, _StandaloneText):
                    # Contract violation: can't reorder a standalone speak
                    # into a streaming utterance without either interleaving
                    # audio or blocking. Log and drop.
                    LOGGER.warning(
                        "voice_standalone_during_stream_dropped",
                        extra={"event_data": {"chars": len(item.text)}},
                    )
                    continue
        finally:
            if any_enqueued:
                self._player.wait_idle()
            total_ms = int((time.perf_counter() - t0) * 1000)
            full_text = " ".join(full_text_parts).strip()
            perf_log(
                Category.TTS,
                "stream utterance complete",
                total_ms,
                chars=len(full_text),
                chunks=chunks_seen,
                cache_hits=cache_hits,
                synth_ms=synth_ms_total,
                first_audio_ms=first_audio_ms,
            )
            if started_emitted and self._speech_events is not None:
                try:
                    self._speech_events.emit_speaking_finished(full_text)
                except Exception:
                    LOGGER.exception("voice_speaking_finished_emit_failed")

    def _resolve_audio_timed(
        self, chunk: str
    ) -> tuple[PcmAudio, int, bool] | None:
        cached = self._cache.get(chunk)
        if cached is not None:
            return cached, 0, True
        t0 = time.perf_counter()
        try:
            audio = self._engine.synthesize(chunk)
        except TtsEngineError as exc:
            LOGGER.warning(
                "voice_synth_failed",
                extra={
                    "category": Category.TTS,
                    "event_data": {"error": str(exc), "chunk": chunk[:80]},
                },
            )
            return None
        synth_ms = int((time.perf_counter() - t0) * 1000)
        if len(chunk) <= _CACHE_MAX_CHUNK_CHARS:
            self._cache.put(chunk, audio)
        return audio, synth_ms, False

    def _fallback_speak(self, text: str) -> None:
        if self._fallback is None:
            LOGGER.warning(
                "voice_no_fallback",
                extra={"event_data": {"text": text[:120]}},
            )
            return
        LOGGER.info(
            "voice_fallback_used",
            extra={"event_data": {"chars": len(text)}},
        )
        try:
            self._fallback.speak(text)
        except Exception:
            LOGGER.exception("voice_fallback_failed")
