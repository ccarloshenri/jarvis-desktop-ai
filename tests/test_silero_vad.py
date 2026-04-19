from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.implementations.stt.vad_silero import (
    SileroVAD,
    SileroVadUnavailableError,
)

_MODEL_PATH = Path("models/vad/silero_vad.onnx")
_HAS_MODEL = _MODEL_PATH.exists()


pytestmark = pytest.mark.skipif(
    not _HAS_MODEL,
    reason="silero vad model not downloaded — run scripts/fetch_silero_vad.ps1",
)


def test_warmup_with_missing_model_raises() -> None:
    vad = SileroVAD(model_path=Path("does/not/exist.onnx"))
    with pytest.raises(SileroVadUnavailableError):
        vad.warmup()


def test_silence_is_not_speech() -> None:
    import numpy as np

    vad = SileroVAD(model_path=_MODEL_PATH, threshold=0.5)
    vad.warmup()
    silence = np.zeros(vad.expected_chunk_samples, dtype=np.int16).tobytes()
    # Feed a few windows so the VAD sees consistent silence (the LSTM
    # state initialises near zero, so a single window is already fine).
    assert not any(vad.is_speech(silence) for _ in range(5))


def test_wrong_chunk_size_raises_value_error() -> None:
    import numpy as np

    vad = SileroVAD(model_path=_MODEL_PATH)
    vad.warmup()
    # 256 samples — half of what the model expects at 16kHz.
    bad = np.zeros(256, dtype=np.int16).tobytes()
    with pytest.raises(ValueError):
        vad.is_speech(bad)


def test_reset_reinitialises_state_without_error() -> None:
    import numpy as np

    vad = SileroVAD(model_path=_MODEL_PATH)
    vad.warmup()
    chunk = np.zeros(vad.expected_chunk_samples, dtype=np.int16).tobytes()
    vad.is_speech(chunk)
    vad.reset()
    # After reset, the next call should still run cleanly.
    assert vad.is_speech(chunk) is False
