"""Piper synthesizer wrapper — text in, raw PCM out. No threading here.

Kept deliberately dumb: the class knows how to spawn piper.exe with the
right flags and decode its sample rate from the companion JSON. Queueing,
chunking, playback, and cache integration live in VoiceService and the
audio player — each piece is independently testable.

Voice tuning for the calm, slightly-grave Jarvis feel is done with
length_scale (slower = more deliberate) and sentence_silence (pauses
between sentences). Both are configurable via env vars, documented in
ApplicationFactory.
"""

from __future__ import annotations

import json
import logging
import queue
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

LOGGER = logging.getLogger(__name__)


class TtsEngineError(Exception):
    """Raised when the Piper subprocess fails or produces no audio."""


@dataclass(frozen=True, slots=True)
class PcmAudio:
    pcm_bytes: bytes
    sample_rate: int
    sample_width: int = 2
    channels: int = 1


class PiperEngine:
    def __init__(
        self,
        piper_exe: Path,
        model_path: Path,
        length_scale: float = 1.1,
        sentence_silence_s: float = 0.3,
        noise_scale: float = 0.5,
        noise_w: float = 0.7,
    ) -> None:
        self._piper_exe = Path(piper_exe)
        self._model_path = Path(model_path)
        if not self._piper_exe.exists():
            raise TtsEngineError(f"Piper executable not found at {self._piper_exe}")
        if not self._model_path.exists():
            raise TtsEngineError(f"Piper model not found at {self._model_path}")
        self._length_scale = length_scale
        self._sentence_silence_s = sentence_silence_s
        self._noise_scale = noise_scale
        self._noise_w = noise_w
        self._sample_rate = self._read_sample_rate()

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    def synthesize(self, text: str) -> PcmAudio:
        if not text.strip():
            raise TtsEngineError("synthesize called with empty text")
        try:
            result = subprocess.run(
                self._build_cmd(),
                input=text.encode("utf-8"),
                capture_output=True,
                check=True,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr.decode("utf-8", errors="replace") if exc.stderr else ""
            raise TtsEngineError(f"piper exited with {exc.returncode}: {stderr}") from exc
        except FileNotFoundError as exc:
            raise TtsEngineError(f"piper executable disappeared: {exc}") from exc

        if not result.stdout:
            raise TtsEngineError("piper produced no audio")
        return PcmAudio(pcm_bytes=result.stdout, sample_rate=self._sample_rate)

    def _read_sample_rate(self) -> int:
        # Piper's voice configs sit next to the .onnx file as <name>.onnx.json.
        # Default to 22050 only if the file is missing or malformed so the
        # engine keeps working against older model drops.
        config_path = self._model_path.with_suffix(self._model_path.suffix + ".json")
        if not config_path.exists():
            return 22050
        try:
            payload = json.loads(config_path.read_text(encoding="utf-8"))
            return int(payload.get("audio", {}).get("sample_rate", 22050))
        except (OSError, ValueError, TypeError) as exc:
            LOGGER.warning(
                "piper_sample_rate_read_failed",
                extra={"event_data": {"error": str(exc), "config": str(config_path)}},
            )
            return 22050

    def _build_cmd(self) -> list[str]:
        # Kept as a helper so PrewarmedPiperEngine can spawn with the same
        # flag set without duplicating the argument layout.
        return [
            str(self._piper_exe),
            "--model",
            str(self._model_path),
            "--length-scale",
            f"{self._length_scale:.3f}",
            "--sentence-silence",
            f"{self._sentence_silence_s:.3f}",
            "--noise-scale",
            f"{self._noise_scale:.3f}",
            "--noise-w",
            f"{self._noise_w:.3f}",
            "--output-raw",
        ]


class PrewarmedPiperEngine(PiperEngine):
    """PiperEngine variant that keeps a pool of pre-started piper.exe
    processes warm so synthesize() doesn't pay model-load time per call.

    Piper's CLI loads the ONNX voice model at startup before reading stdin
    — that's ~150–300ms on first open, ~80–150ms once the OS cache is
    hot. Spawning per chunk (the parent class) pays that cost every call,
    which dominates the synth path for short acknowledgements like
    "Abrindo." where the raw TTS is only ~20ms of actual inference.

    The pool holds up to `pool_size` processes in `STDIN-open, model-loaded`
    state. synthesize() pulls one, writes text, reads the raw PCM output,
    and triggers a background refill. Failure path degrades gracefully:
    if the pool is empty (first call, refill lagging, or refill errored)
    we spawn a fresh process inline — same behaviour as the base class.
    """

    def __init__(
        self,
        piper_exe: Path,
        model_path: Path,
        length_scale: float = 1.1,
        sentence_silence_s: float = 0.3,
        noise_scale: float = 0.5,
        noise_w: float = 0.7,
        pool_size: int = 2,
    ) -> None:
        super().__init__(
            piper_exe=piper_exe,
            model_path=model_path,
            length_scale=length_scale,
            sentence_silence_s=sentence_silence_s,
            noise_scale=noise_scale,
            noise_w=noise_w,
        )
        self._pool_size = max(1, pool_size)
        self._pool: queue.Queue[subprocess.Popen[bytes]] = queue.Queue(
            maxsize=self._pool_size
        )
        self._closed = False
        for _ in range(self._pool_size):
            self._start_refill()

    def synthesize(self, text: str) -> PcmAudio:
        if not text.strip():
            raise TtsEngineError("synthesize called with empty text")
        if self._closed:
            raise TtsEngineError("engine closed")

        proc = self._acquire()
        t0 = time.perf_counter()
        try:
            stdout, stderr = proc.communicate(input=text.encode("utf-8"))
        except subprocess.TimeoutExpired as exc:
            try:
                proc.kill()
            except OSError:
                pass
            raise TtsEngineError(f"piper timed out: {exc}") from exc
        finally:
            # A process that has run communicate() can't be reused (stdin
            # was closed, the subprocess exited). Always trigger a refill
            # so the next call still hits a warm one.
            self._start_refill()

        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        if proc.returncode != 0:
            err = stderr.decode("utf-8", errors="replace") if stderr else ""
            raise TtsEngineError(
                f"piper exited with {proc.returncode} after {elapsed_ms}ms: {err}"
            )
        if not stdout:
            raise TtsEngineError("piper produced no audio")
        return PcmAudio(pcm_bytes=stdout, sample_rate=self._sample_rate)

    def close(self) -> None:
        """Terminate any prewarmed processes. Idempotent."""
        self._closed = True
        while True:
            try:
                proc = self._pool.get_nowait()
            except queue.Empty:
                return
            try:
                proc.kill()
            except OSError:
                pass

    def _acquire(self) -> subprocess.Popen[bytes]:
        try:
            return self._pool.get_nowait()
        except queue.Empty:
            LOGGER.debug("piper_pool_miss")
            return self._spawn()

    def _start_refill(self) -> None:
        if self._closed:
            return
        threading.Thread(
            target=self._refill_worker,
            name="jarvis-piper-prewarm",
            daemon=True,
        ).start()

    def _refill_worker(self) -> None:
        if self._closed:
            return
        try:
            proc = self._spawn()
        except TtsEngineError:
            LOGGER.exception("piper_prewarm_spawn_failed")
            return
        try:
            self._pool.put_nowait(proc)
        except queue.Full:
            # Another refill thread beat us to it — kill the extra process
            # so we don't leak handles.
            try:
                proc.kill()
            except OSError:
                pass

    def _spawn(self) -> subprocess.Popen[bytes]:
        try:
            return subprocess.Popen(
                self._build_cmd(),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
        except (OSError, FileNotFoundError) as exc:
            raise TtsEngineError(f"failed to spawn piper: {exc}") from exc
