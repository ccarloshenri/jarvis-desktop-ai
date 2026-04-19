"""Thin wrapper around openWakeWord — int16 PCM in, "did the wake word fire?" out.

Why a wrapper instead of using openWakeWord directly:
- The score smoothing + cooldown + reset bookkeeping is the same every
  time and easy to get wrong inline in the audio loop.
- Lazy import keeps openWakeWord (and its onnxruntime dep) optional: a
  user without the package falls back to the legacy AudioCapture flow.
- The only externally-visible API is `process(chunk)` returning a bool,
  which makes the audio capture loop trivial to read.

The detector is *not* thread-safe. openWakeWord's Model carries internal
streaming state, so a single instance must be driven by exactly one audio
loop. Capture is single-threaded today; if that ever changes, give each
thread its own detector.
"""

from __future__ import annotations

import logging
import time

LOGGER = logging.getLogger(__name__)


class WakeWordUnavailableError(RuntimeError):
    """openWakeWord is not installed or the model failed to load."""


class WakeWordDetector:
    def __init__(
        self,
        model_name: str = "hey_jarvis",
        threshold: float = 0.2,
        cooldown_s: float = 1.5,
        inference_framework: str = "onnx",
        debug_scores: bool = False,
    ) -> None:
        self._model_name = model_name
        self._threshold = threshold
        self._cooldown_s = cooldown_s
        self._inference_framework = inference_framework
        self._debug_scores = debug_scores
        self._model = None  # type: ignore[var-annotated]
        self._last_fire_ts: float = 0.0
        # Track the running peak score in a window so we can periodically
        # surface what the user's voice is *actually* scoring — critical
        # for tuning the threshold against unfamiliar voices/accents.
        self._window_peak_score: float = 0.0
        self._window_start_ts: float = time.monotonic()

    @property
    def model_name(self) -> str:
        return self._model_name

    def warmup(self) -> None:
        """Eagerly construct the model so the first audio chunk doesn't pay
        the load cost. Raises WakeWordUnavailableError on import or model
        load failures so the factory can fall back cleanly."""
        self._ensure_model()

    def _ensure_model(self) -> None:
        if self._model is not None:
            return
        try:
            from openwakeword.model import Model
            from openwakeword.utils import download_models
        except ImportError as exc:
            raise WakeWordUnavailableError(
                f"openwakeword not installed: {exc}"
            ) from exc
        # openwakeword ships *without* the actual ONNX models — they're
        # downloaded to the package's resources/ dir on first use. Calling
        # download_models() is idempotent (skips files already present),
        # so it's safe to invoke on every cold start. The first call needs
        # network access; subsequent ones are no-ops.
        try:
            download_models([self._model_name])
        except Exception as exc:
            raise WakeWordUnavailableError(
                f"failed to download wake model {self._model_name!r}: {exc}"
            ) from exc
        try:
            self._model = Model(
                wakeword_models=[self._model_name],
                inference_framework=self._inference_framework,
            )
        except Exception as exc:
            raise WakeWordUnavailableError(
                f"failed to load wake model {self._model_name!r}: {exc}"
            ) from exc

    def process(self, chunk: "object") -> bool:
        """Feed one 80ms PCM chunk (1280 int16 samples @ 16kHz, as a numpy
        array). Returns True exactly once when the wake word fires; the
        cooldown swallows repeated detections from the trailing tail of the
        same utterance so the caller doesn't double-trigger."""
        self._ensure_model()
        scores = self._model.predict(chunk)  # type: ignore[union-attr]
        # openWakeWord returns scores keyed by the *full* model name (e.g.
        # "hey_jarvis_v0.1"). Match by prefix so callers can pass a short
        # name without knowing the version suffix.
        score = 0.0
        for key, value in scores.items():
            if key == self._model_name or key.startswith(self._model_name):
                score = float(value)
                break
        # Diagnostics: report the highest score seen in the current window
        # so the user can dial the threshold against their own voice. We
        # only log peaks that look like a *try* (>0.05) — this filters out
        # the constant ~0.0 floor while still catching weak detections.
        self._track_peak(score)
        if score < self._threshold:
            return False
        now = time.monotonic()
        if now - self._last_fire_ts < self._cooldown_s:
            return False
        self._last_fire_ts = now
        # Drop the model's streaming buffers so the next detection starts
        # from a clean state — without this, the score stays high for ~1s
        # after the wake word and the cooldown alone wouldn't be enough.
        try:
            self._model.reset()  # type: ignore[union-attr]
        except Exception:
            LOGGER.debug("wake_word_reset_failed", exc_info=True)
        LOGGER.info(
            "wake_word_detected",
            extra={"event_data": {"model": self._model_name, "score": round(score, 3)}},
        )
        return True

    def _track_peak(self, score: float) -> None:
        if score > self._window_peak_score:
            self._window_peak_score = score
        # In debug mode, dump every above-floor score immediately so the
        # user can correlate "I just said Jarvis" with a number.
        if self._debug_scores and score > 0.05:
            LOGGER.info(
                "wake_word_score",
                extra={
                    "event_data": {
                        "model": self._model_name,
                        "score": round(score, 3),
                        "threshold": self._threshold,
                    }
                },
            )
        # Otherwise periodically flush the windowed peak so the regular
        # log shows what kind of scores the room is producing without
        # spamming a line per chunk (12.5 chunks/second).
        now = time.monotonic()
        if now - self._window_start_ts >= 5.0:
            if self._window_peak_score > 0.05:
                LOGGER.info(
                    "wake_word_peak_5s",
                    extra={
                        "event_data": {
                            "model": self._model_name,
                            "peak": round(self._window_peak_score, 3),
                            "threshold": self._threshold,
                        }
                    },
                )
            self._window_peak_score = 0.0
            self._window_start_ts = now
