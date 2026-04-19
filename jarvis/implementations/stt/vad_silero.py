"""Silero VAD wrapper — neural voice activity detection on raw int16 PCM.

Silero VAD (https://github.com/snakers4/silero-vad) is a 1MB ONNX model
that detects speech presence on a per-frame basis. Used here to replace
the RMS silence heuristic in WakeWordAudioCapture.

Why the swap matters:
- RMS cuts speech off in quiet rooms (noise floor rises above threshold)
  and holds the capture open for 800ms of silence so real pauses don't
  kill captures mid-sentence. VAD is sharper: <100ms to detect true end
  of speech, so the capture closes ~500ms earlier on average.
- VAD doesn't confuse ambient noise (fan, keyboard, distant speech) with
  the user's own voice, so the command capture doesn't stretch while
  we wait for the room to go quiet.

Graceful degradation: if the ONNX model file is missing or `onnxruntime`
fails to open it, the wake-word capture falls back to the legacy RMS
heuristic. The VAD is an opt-in accelerator, not a hard dependency.
"""

from __future__ import annotations

import logging
from pathlib import Path

LOGGER = logging.getLogger(__name__)


class SileroVadUnavailableError(Exception):
    """Silero VAD model or runtime isn't available — caller should fall
    back to the legacy RMS silence heuristic."""


# Silero v5 uses fixed 512-sample windows at 16kHz (32ms). Other lengths
# are rejected by the ONNX graph.
_CHUNK_SAMPLES_16K = 512
_SAMPLE_RATE = 16000


class SileroVAD:
    """Frame-by-frame speech/silence detector. Stateful across calls —
    the internal LSTM state is threaded through successive `is_speech`
    calls so the decision considers short-term history."""

    def __init__(
        self,
        model_path: Path,
        threshold: float = 0.5,
    ) -> None:
        self._model_path = Path(model_path)
        self._threshold = threshold
        self._session = None  # lazy-loaded
        self._state = None  # lazy-loaded

    @property
    def expected_chunk_samples(self) -> int:
        return _CHUNK_SAMPLES_16K

    @property
    def sample_rate(self) -> int:
        return _SAMPLE_RATE

    def warmup(self) -> None:
        """Load the ONNX session eagerly. Raises SileroVadUnavailableError
        if the model file is missing or the runtime can't open it — the
        caller logs and falls back. Cheap to call: <200ms on first open,
        <1ms if already warm."""
        self._ensure_session()

    def reset(self) -> None:
        """Clear the internal LSTM state. Call this between captures so
        the next utterance's decisions don't leak signal from the previous
        one. The wake-word flow calls reset() at the top of every capture."""
        if self._state is not None:
            import numpy as np

            self._state = np.zeros((2, 1, 128), dtype=np.float32)

    def is_speech(self, pcm_chunk: bytes) -> bool:
        """Return True if the chunk contains speech at our threshold.

        `pcm_chunk` MUST be exactly `expected_chunk_samples` int16 samples
        (1024 bytes at 16kHz). Any other size raises ValueError — we
        could resample but it would hide upstream shape bugs that are
        cheaper to catch here.
        """
        import numpy as np

        self._ensure_session()
        expected_bytes = _CHUNK_SAMPLES_16K * 2
        if len(pcm_chunk) != expected_bytes:
            raise ValueError(
                f"silero vad expects {expected_bytes} bytes ({_CHUNK_SAMPLES_16K} samples @16k), "
                f"got {len(pcm_chunk)}"
            )
        # Silero expects float32 in [-1, 1]. int16 -> float32 divide by 32768.
        samples = np.frombuffer(pcm_chunk, dtype=np.int16).astype(np.float32) / 32768.0
        input_tensor = samples.reshape(1, _CHUNK_SAMPLES_16K)
        sr_tensor = np.array(_SAMPLE_RATE, dtype=np.int64)
        outputs = self._session.run(  # type: ignore[union-attr]
            None,
            {"input": input_tensor, "state": self._state, "sr": sr_tensor},
        )
        prob = float(outputs[0][0][0])
        self._state = outputs[1]
        return prob >= self._threshold

    def _ensure_session(self) -> None:
        if self._session is not None:
            return
        if not self._model_path.exists():
            raise SileroVadUnavailableError(
                f"silero vad model not found at {self._model_path}"
            )
        try:
            import onnxruntime as ort
            import numpy as np
        except ImportError as exc:
            raise SileroVadUnavailableError(
                f"onnxruntime or numpy not installed: {exc}"
            ) from exc
        try:
            # CPUExecutionProvider only — VAD is tiny (<1ms per chunk) and
            # shuttling GPU state between frames costs more than CPU inference.
            self._session = ort.InferenceSession(
                str(self._model_path),
                providers=["CPUExecutionProvider"],
            )
        except Exception as exc:
            raise SileroVadUnavailableError(
                f"failed to load silero vad: {exc}"
            ) from exc
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        LOGGER.info(
            "silero_vad_loaded",
            extra={"event_data": {"path": str(self._model_path)}},
        )
