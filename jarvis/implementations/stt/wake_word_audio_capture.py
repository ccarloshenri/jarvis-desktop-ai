"""Always-on wake-word capture: detect "hey jarvis", then record the command.

Replaces the energy-VAD `AudioCapture` for the wake-word path. The win is
twofold:
- Non-Jarvis speech in the room never reaches Whisper, so we burn ~0 CPU
  on it (no decode, no LLM round-trip). The legacy gate paid full STT
  cost for every utterance just to throw most of them away.
- The user can speak immediately after the wake word — there is no
  per-turn `listen_timeout` waiting for speech to start, because the
  detector only fires when the user is mid-utterance.

Audio plumbing notes:
- We use PyAudio directly (not `speech_recognition.Microphone`). The
  wake detector wants a continuous fixed-size chunk stream and SR's
  Microphone is built around start/end-of-phrase semantics; mixing the
  two is fragile and adds latency.
- The pre-roll buffer (~960ms) preserves the wake word itself in the
  audio handed to Whisper. That way Whisper's transcript still contains
  "Jarvis" and the assistant's wake-word gate (a defence-in-depth check)
  keeps working without special-casing.
- End-of-command is detected with a simple RMS silence heuristic. Going
  more sophisticated (Silero VAD, webrtcvad) trades accuracy for an
  extra dependency; the heuristic is good enough at 16kHz mono and the
  worst-case false-end is "Jarvis re-asks one extra second of input".
"""

from __future__ import annotations

import collections
import logging
import math
import time
import wave
from pathlib import Path

from jarvis.implementations.stt.vad_silero import SileroVAD, SileroVadUnavailableError
from jarvis.implementations.stt.wake_word_detector import (
    WakeWordDetector,
    WakeWordUnavailableError,
)
from jarvis.interfaces.iaudio_capture import IAudioCapture
from jarvis.interfaces.ispeech_to_text import SpeechTimeoutError
from jarvis.interfaces.istt_provider import CapturedAudio
from jarvis.utils.performance import Category, log, perf_log

LOGGER = logging.getLogger(__name__)


_SAMPLE_RATE = 16000
_SAMPLE_WIDTH = 2  # bytes (int16)
_CHUNK_SAMPLES = 1280  # openWakeWord expects 80ms @ 16kHz
_CHUNK_DURATION_S = _CHUNK_SAMPLES / _SAMPLE_RATE  # 0.08s

# Pre-roll: how much audio to keep before the wake fires. We keep just
# 80ms — enough to bridge into a command word the user started saying
# during the detector's ~200ms decision delay, but NOT enough to include
# the wake word itself. Including the wake word ("Jarvis") in the audio
# was biasing Whisper toward English decoding ("Hey Jarvis, Open Spotify"
# instead of "abre o Spotify") because the model has strong English
# associations for the name. We inject the wake-word marker into the
# transcript downstream (see STTService) so the assistant's gate still
# works without seeing it in the audio.
_PREROLL_CHUNKS = 1

# Command capture bounds. Max protects against runaway recordings if VAD
# never closes (open mic in noisy room); silence end is what closes a
# normal turn.
_MAX_COMMAND_SECONDS = 8.0

# RMS-path tuning (used only when Silero VAD isn't available). These are
# deliberately conservative because the RMS heuristic can't tell real
# speech from noise reliably — the 0.8s silence window protects against
# false closes mid-pause, at the cost of slower turn endings.
_RMS_SILENCE_END_SECONDS = 0.8
_RMS_MIN_COMMAND_SECONDS = 1.5
_RMS_SILENCE_THRESHOLD = 250.0

# Silero-path tuning. 1.0s silence was still clipping long English
# commands with natural thinking pauses ("search… the latest… Nolan
# movie"). 1.5s is comfortable for deliberate speech — inter-word
# gaps in careful dictation can hit 800-1200ms — while still closing
# short commands (~1-2s speech) within 2s total. 1.5s minimum also
# protects the opening beat when the user takes a breath after the
# wake word before starting the actual command.
_VAD_SILENCE_END_SECONDS = 1.5
_VAD_MIN_COMMAND_SECONDS = 1.5

# Silero operates on 512-sample windows at 16kHz (32ms). We read in
# _CHUNK_SAMPLES-sized bursts from PyAudio (matches openWakeWord),
# then buffer and drain to the VAD at 512-sample granularity.
_VAD_WINDOW_SAMPLES = 512
_VAD_WINDOW_BYTES = _VAD_WINDOW_SAMPLES * _SAMPLE_WIDTH
_VAD_WINDOW_DURATION_S = _VAD_WINDOW_SAMPLES / _SAMPLE_RATE  # 0.032s


class WakeWordAudioCapture(IAudioCapture):
    """Mic capture gated by an always-on wake-word detector.

    capture() blocks until the wake word fires, then records command audio
    until silence (or `_MAX_COMMAND_SECONDS`). Returns the pre-roll +
    command audio as a single PCM blob for downstream STT.
    """

    def __init__(
        self,
        detector: WakeWordDetector | None = None,
        max_command_seconds: float = _MAX_COMMAND_SECONDS,
        vad: SileroVAD | None = None,
        dump_dir: Path | None = None,
        level_callback: "object | None" = None,
        wake_callback: "object | None" = None,
    ) -> None:
        self._detector = detector or WakeWordDetector()
        self._max_command_seconds = max_command_seconds
        # When VAD is present we use neural endpointing (shorter silence,
        # shorter minimum) — without it we fall back to the RMS heuristic
        # tuned conservatively enough not to clip.
        self._vad = vad
        if vad is not None:
            self._silence_end_seconds = _VAD_SILENCE_END_SECONDS
            self._min_command_seconds = _VAD_MIN_COMMAND_SECONDS
        else:
            self._silence_end_seconds = _RMS_SILENCE_END_SECONDS
            self._min_command_seconds = _RMS_MIN_COMMAND_SECONDS
        self._silence_rms_threshold = _RMS_SILENCE_THRESHOLD
        # When set, every captured utterance is also written to disk as a
        # WAV file. Pure debug aid: lets the user verify what Whisper is
        # actually seeing when transcripts come back garbled.
        self._dump_dir = dump_dir
        # Optional callback fired for each 80ms chunk with an RMS level
        # normalized to [0, 1]. Drives the UI's live VU meter without the
        # capture class needing to know about Qt / event bus.
        self._level_callback = level_callback
        # Optional callback fired once each time the wake word detector
        # confirms a hit. Used by the HUD to increment the wake-fires
        # counter without adding another signal plumbed through STT.
        self._wake_callback = wake_callback
        if self._dump_dir is not None:
            try:
                self._dump_dir.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                LOGGER.warning(
                    "audio_dump_dir_create_failed",
                    extra={"event_data": {"dir": str(self._dump_dir), "error": str(exc)}},
                )
                self._dump_dir = None
        self._pyaudio = None  # type: ignore[var-annotated]

    def recalibrate(self) -> None:
        # No ambient calibration needed: the wake-word model handles
        # robustness, and the silence threshold is a fixed constant.
        return

    def capture(self) -> CapturedAudio:
        # Lazy: deferring PyAudio init means a test process that never
        # records audio doesn't fail on missing audio devices.
        import numpy as np
        import pyaudio

        if self._pyaudio is None:
            self._pyaudio = pyaudio.PyAudio()
        try:
            self._detector.warmup()
        except WakeWordUnavailableError as exc:
            # The factory should have caught this at boot; if we get here
            # the install state changed mid-session. Fail loud so the user
            # sees what happened instead of silently never hearing them.
            raise SpeechTimeoutError(f"wake-word detector unavailable: {exc}") from exc

        stream = self._pyaudio.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=_SAMPLE_RATE,
            input=True,
            frames_per_buffer=_CHUNK_SAMPLES,
        )
        try:
            log(Category.VOICE, "waiting for wake word...")
            preroll = self._wait_for_wake(stream, np)
            log(Category.VOICE, "wake word fired — capturing command")
            command_chunks = self._capture_until_silence(stream, np)
        finally:
            try:
                stream.stop_stream()
                stream.close()
            except Exception:
                LOGGER.debug("pyaudio_close_failed", exc_info=True)

        full_audio = b"".join(preroll) + b"".join(command_chunks)
        perf_log(
            Category.VOICE,
            "wake capture complete",
            int(len(full_audio) / (_SAMPLE_RATE * _SAMPLE_WIDTH) * 1000),
            preroll_chunks=len(preroll),
            command_chunks=len(command_chunks),
            audio_bytes=len(full_audio),
        )
        if self._dump_dir is not None:
            self._dump_wav(full_audio)
        return CapturedAudio(
            pcm_bytes=full_audio,
            sample_rate=_SAMPLE_RATE,
            sample_width=_SAMPLE_WIDTH,
            channels=1,
        )

    def _dump_wav(self, pcm: bytes) -> None:
        # Filename format prioritises being usefully sortable in a dir
        # listing; the millisecond suffix prevents collisions when two
        # captures land in the same second after a quick re-listen.
        ts = time.strftime("%Y%m%d_%H%M%S")
        ms = int((time.time() % 1) * 1000)
        path = self._dump_dir / f"wake_capture_{ts}_{ms:03d}.wav"  # type: ignore[union-attr]
        try:
            with wave.open(str(path), "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(_SAMPLE_WIDTH)
                wav.setframerate(_SAMPLE_RATE)
                wav.writeframes(pcm)
            LOGGER.info(
                "audio_dump_written",
                extra={"event_data": {"path": str(path), "bytes": len(pcm)}},
            )
        except OSError as exc:
            LOGGER.warning(
                "audio_dump_write_failed",
                extra={"event_data": {"path": str(path), "error": str(exc)}},
            )

    def _wait_for_wake(self, stream, np) -> list[bytes]:
        preroll: collections.deque[bytes] = collections.deque(maxlen=_PREROLL_CHUNKS)
        wait_start = time.perf_counter()
        while True:
            chunk_bytes = stream.read(_CHUNK_SAMPLES, exception_on_overflow=False)
            preroll.append(chunk_bytes)
            samples = np.frombuffer(chunk_bytes, dtype=np.int16)
            self._emit_level(chunk_bytes, np)
            if self._detector.process(samples):
                wait_ms = int((time.perf_counter() - wait_start) * 1000)
                log(Category.VOICE, "wake fired", wait_ms=wait_ms)
                if self._wake_callback is not None:
                    try:
                        self._wake_callback()
                    except Exception:
                        LOGGER.debug("wake_callback_failed", exc_info=True)
                return list(preroll)

    def _emit_level(self, chunk_bytes: bytes, np) -> None:
        if self._level_callback is None:
            return
        rms = _rms_int16(chunk_bytes, np)
        # int16 full-scale is 32768; a typical speech peak sits around
        # 2000-4000 RMS. Normalize to 0..1 by dividing by 8000 so quiet
        # speech still lights up the meter visibly without the loud end
        # being clipped by a too-tight scale.
        level = min(1.0, rms / 8000.0)
        try:
            self._level_callback(level)
        except Exception:
            LOGGER.debug("mic_level_callback_failed", exc_info=True)

    def _capture_until_silence(self, stream, np) -> list[bytes]:
        if self._vad is not None:
            try:
                return self._capture_until_silence_vad(stream)
            except SileroVadUnavailableError as exc:
                LOGGER.warning(
                    "silero_vad_failed_falling_back_to_rms",
                    extra={"event_data": {"error": str(exc)}},
                )
                self._vad = None
                self._silence_end_seconds = _RMS_SILENCE_END_SECONDS
                self._min_command_seconds = _RMS_MIN_COMMAND_SECONDS
        return self._capture_until_silence_rms(stream, np)

    def _capture_until_silence_vad(self, stream) -> list[bytes]:
        """End-of-speech via Silero VAD on the captured chunks.

        We read at PyAudio's native 80ms frame size (matches openWakeWord)
        and buffer bytes to drain into the VAD at exactly 512-sample
        (32ms) windows — Silero's input contract. The last partial VAD
        window is dropped each iteration; it rolls into the next read.
        """
        assert self._vad is not None
        self._vad.reset()
        chunks: list[bytes] = []
        vad_buffer = bytearray()
        silent_windows = 0
        silent_windows_to_end = max(
            1, int(self._silence_end_seconds / _VAD_WINDOW_DURATION_S)
        )
        min_samples = int(self._min_command_seconds * _SAMPLE_RATE)
        max_chunks = max(1, int(self._max_command_seconds / _CHUNK_DURATION_S))
        total_samples = 0
        record_start = time.perf_counter()
        ended_on_silence = False
        import numpy as _np_local  # local alias to avoid shadowing
        for _ in range(max_chunks):
            chunk_bytes = stream.read(_CHUNK_SAMPLES, exception_on_overflow=False)
            chunks.append(chunk_bytes)
            total_samples += _CHUNK_SAMPLES
            self._emit_level(chunk_bytes, _np_local)
            vad_buffer.extend(chunk_bytes)
            while len(vad_buffer) >= _VAD_WINDOW_BYTES:
                window = bytes(vad_buffer[:_VAD_WINDOW_BYTES])
                del vad_buffer[:_VAD_WINDOW_BYTES]
                if self._vad.is_speech(window):
                    silent_windows = 0
                else:
                    silent_windows += 1
            if total_samples < min_samples:
                continue
            if silent_windows >= silent_windows_to_end:
                ended_on_silence = True
                break
        record_ms = int((time.perf_counter() - record_start) * 1000)
        perf_log(
            Category.VOICE,
            "command capture",
            record_ms,
            chunks=len(chunks),
            endpointer="silero",
            ended_on_silence=ended_on_silence,
        )
        return chunks

    def _capture_until_silence_rms(self, stream, np) -> list[bytes]:
        chunks: list[bytes] = []
        silent_chunks = 0
        silent_chunks_to_end = max(1, int(self._silence_end_seconds / _CHUNK_DURATION_S))
        min_chunks = max(1, int(self._min_command_seconds / _CHUNK_DURATION_S))
        max_chunks = max(min_chunks + 1, int(self._max_command_seconds / _CHUNK_DURATION_S))
        record_start = time.perf_counter()
        for i in range(max_chunks):
            chunk_bytes = stream.read(_CHUNK_SAMPLES, exception_on_overflow=False)
            chunks.append(chunk_bytes)
            self._emit_level(chunk_bytes, np)
            rms = _rms_int16(chunk_bytes, np)
            if rms < self._silence_rms_threshold:
                silent_chunks += 1
            else:
                silent_chunks = 0
            # Don't end on silence inside the minimum window. The user is
            # likely still talking through a natural pause between the
            # wake word and the command itself, or between command words.
            # Once we're past the floor, trailing silence is the real end
            # of the utterance.
            if i + 1 >= min_chunks and silent_chunks >= silent_chunks_to_end:
                break
        record_ms = int((time.perf_counter() - record_start) * 1000)
        perf_log(
            Category.VOICE,
            "command capture",
            record_ms,
            chunks=len(chunks),
            endpointer="rms",
            ended_on_silence=silent_chunks >= silent_chunks_to_end,
        )
        return chunks


def _rms_int16(chunk_bytes: bytes, np) -> float:
    """RMS amplitude of an int16 PCM chunk. Returns 0.0 for empty input.

    Computed in float64 to avoid int16 overflow when squaring large
    samples — int16**2 can reach ~1e9, comfortably outside int16 range.
    """
    if not chunk_bytes:
        return 0.0
    samples = np.frombuffer(chunk_bytes, dtype=np.int16).astype(np.float64)
    if samples.size == 0:
        return 0.0
    mean_square = float(np.mean(samples * samples))
    return math.sqrt(mean_square)
