"""Background worker that plays PCM audio sequentially from a queue.

Why a dedicated player (instead of inlining winsound calls in the synth
worker):

- Decouples synthesis from playback. Piper for chunk N+1 can run while
  chunk N is still playing on the audio device, so the user hears a
  continuous phrase even though each chunk is produced on demand.
- Gives a single, well-defined "am I speaking right now?" state that
  VoiceService can query / wait on without racing multiple threads.
- Centralizes the winsound (Windows) vs aplay (Linux) split so the rest
  of the pipeline stays platform-agnostic.
"""

from __future__ import annotations

import io
import logging
import queue
import subprocess
import sys
import tempfile
import threading
import time
import wave
from dataclasses import dataclass
from pathlib import Path

from jarvis.services.tts_engine import PcmAudio

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PlaybackJob:
    audio: PcmAudio
    # Marker text is kept only so logs are useful when debugging which
    # chunk caused trouble. Not used by playback itself.
    marker: str = ""


# Sentinel pushed onto the queue by stop() so the worker unblocks cleanly
# instead of waiting forever on queue.get().
_SHUTDOWN = object()


class AudioPlayer:
    def __init__(self) -> None:
        self._queue: queue.Queue[object] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._running = False
        # An Event that is set whenever the queue is empty AND no job is
        # currently playing. wait_idle() blocks on this instead of polling.
        self._idle = threading.Event()
        self._idle.set()
        self._on_playback_started: "callable | None" = None
        self._on_playback_drained: "callable | None" = None
        self._active_jobs = 0
        self._active_lock = threading.Lock()

    def set_callbacks(
        self,
        on_playback_started: "callable | None" = None,
        on_playback_drained: "callable | None" = None,
    ) -> None:
        """Hook for VoiceService to emit speaking_started / speaking_finished.

        on_playback_started fires on the *first* job after an idle period;
        on_playback_drained fires when the queue empties and no job is playing.
        Keeps the event contract (one start, one finish per utterance) aligned
        with what the UI orb expects.
        """
        self._on_playback_started = on_playback_started
        self._on_playback_drained = on_playback_drained

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._run, name="jarvis-audio-player", daemon=True
        )
        self._thread.start()

    def enqueue(self, job: PlaybackJob) -> None:
        with self._active_lock:
            self._active_jobs += 1
            self._idle.clear()
        self._queue.put(job)

    def wait_idle(self, timeout: float | None = None) -> bool:
        return self._idle.wait(timeout=timeout)

    def is_idle(self) -> bool:
        return self._idle.is_set()

    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        self._queue.put(_SHUTDOWN)
        thread = self._thread
        if thread is not None:
            thread.join(timeout=2.0)
        self._thread = None

    def _run(self) -> None:
        was_idle = True
        while True:
            item = self._queue.get()
            if item is _SHUTDOWN:
                return
            job = item  # type: ignore[assignment]
            assert isinstance(job, PlaybackJob)

            # Fire "speaking_started" only on the transition idle -> busy.
            # Subsequent chunks in the same utterance don't re-trigger it.
            if was_idle and self._on_playback_started is not None:
                try:
                    self._on_playback_started(job.marker)
                except Exception:
                    LOGGER.exception("audio_player_started_callback_failed")
            was_idle = False

            t0 = time.perf_counter()
            try:
                self._play(job.audio)
            except Exception as exc:
                LOGGER.warning(
                    "audio_player_play_failed",
                    extra={"event_data": {"error": str(exc), "marker": job.marker[:80]}},
                )
            else:
                LOGGER.debug(
                    "audio_player_played",
                    extra={
                        "event_data": {
                            "play_ms": int((time.perf_counter() - t0) * 1000),
                            "bytes": len(job.audio.pcm_bytes),
                            "marker": job.marker[:80],
                        }
                    },
                )

            with self._active_lock:
                self._active_jobs -= 1
                drained = self._active_jobs == 0 and self._queue.empty()
            if drained:
                was_idle = True
                self._idle.set()
                if self._on_playback_drained is not None:
                    try:
                        self._on_playback_drained()
                    except Exception:
                        LOGGER.exception("audio_player_drained_callback_failed")

    def _play(self, audio: PcmAudio) -> None:
        wav_bytes = _pcm_to_wav(audio)
        if sys.platform == "win32":
            import winsound

            # SND_MEMORY plays from bytes (no temp file). SND_NODEFAULT
            # avoids the system "ding" when playback is interrupted.
            winsound.PlaySound(
                wav_bytes,
                winsound.SND_MEMORY | winsound.SND_NODEFAULT,
            )
            return

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(wav_bytes)
            tmp_path = tmp.name
        try:
            subprocess.run(["aplay", "-q", tmp_path], check=False)
        finally:
            Path(tmp_path).unlink(missing_ok=True)


def _pcm_to_wav(audio: PcmAudio) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(audio.channels)
        wav.setsampwidth(audio.sample_width)
        wav.setframerate(audio.sample_rate)
        wav.writeframes(audio.pcm_bytes)
    return buf.getvalue()
