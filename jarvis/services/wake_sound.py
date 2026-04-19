"""Short wake acknowledgement chime — two-note sine pulse with a
decaying envelope. Gives the user immediate feedback that Jarvis
heard them, without the harsh square-wave beep winsound.Beep
produces.

The chime is synthesised once at import time and cached as WAV
bytes, then dispatched via winsound.PlaySound(SND_MEMORY | SND_ASYNC)
so firing it takes essentially zero time on the capture hot path.
"""

from __future__ import annotations

import io
import logging
import math
import struct
import sys
import threading
import wave

LOGGER = logging.getLogger(__name__)


# Tuning notes:
# - E5 (659 Hz) → A5 (880 Hz) is a rising minor third, reads as
#   "acknowledge / ready" rather than "alert". Sci-fi beep cue.
# - 70ms per note + 30ms gap keeps the whole chime under 180ms, so
#   the chime is finished before the user finishes any follow-up
#   word.
# - 0.25 amplitude scale (out of 1.0 full scale) keeps it well below
#   speaking volume so it doesn't startle in a quiet room.
_SAMPLE_RATE = 22050
_NOTE_FREQUENCIES_HZ = (659, 880)
_NOTE_DURATION_S = 0.07
_GAP_DURATION_S = 0.03
_AMPLITUDE = 0.25


def _synthesise_chime() -> bytes:
    """Build the chime PCM once and wrap it in a minimal WAV header."""
    samples: list[int] = []
    sample_rate = _SAMPLE_RATE
    note_samples = int(_NOTE_DURATION_S * sample_rate)
    gap_samples = int(_GAP_DURATION_S * sample_rate)

    for freq in _NOTE_FREQUENCIES_HZ:
        for i in range(note_samples):
            progress = i / note_samples
            # Fast attack (first 5% ramps up from 0 to 1) + exponential
            # decay. Prevents the "click" at the start and gives the
            # chime a natural tail.
            attack = min(1.0, progress * 20.0)
            decay = math.exp(-3.0 * progress)
            envelope = attack * decay
            # Soft sine — a touch of second harmonic adds the
            # "robotic" timbre without the grating of a square wave.
            t = i / sample_rate
            value = (
                math.sin(2 * math.pi * freq * t) * 0.85
                + math.sin(4 * math.pi * freq * t) * 0.15
            )
            samples.append(int(value * envelope * _AMPLITUDE * 32767))
        samples.extend([0] * gap_samples)

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)  # int16
        wav.setframerate(sample_rate)
        wav.writeframes(struct.pack(f"<{len(samples)}h", *samples))
    return buffer.getvalue()


_CHIME_WAV: bytes = _synthesise_chime()


def play_wake_chime() -> None:
    """Fire the chime on a background thread and return immediately."""
    if sys.platform != "win32":
        return
    threading.Thread(
        target=_play_impl, name="jarvis-wake-chime", daemon=True
    ).start()


def _play_impl() -> None:
    try:
        import winsound

        # SND_MEMORY reads straight from the in-memory WAV buffer
        # (no file I/O); SND_ASYNC returns immediately without blocking
        # the caller; SND_NOSTOP lets a still-playing chime finish if
        # the user triggers two wake words back to back.
        flags = winsound.SND_MEMORY | winsound.SND_ASYNC
        winsound.PlaySound(_CHIME_WAV, flags)
    except Exception:
        LOGGER.debug("wake_chime_failed", exc_info=True)
