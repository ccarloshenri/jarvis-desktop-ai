"""Rolling telemetry for the HUD stats panel.

Connects to the event bus's turn/latency signals and keeps lightweight
aggregates that the UI reads on every repaint. Intentionally stateless
across restarts — the panel shows "since Jarvis started", not lifetime.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Sequence


@dataclass(frozen=True, slots=True)
class StatsSnapshot:
    """Read-only view the UI renders each paint cycle."""

    turns_total: int
    turns_success: int
    wake_fires: int
    errors: int
    responses: int
    uptime_seconds: int
    last_total_ms: int
    last_stt_ms: int
    last_llm_ms: int
    last_tts_ms: int
    avg_total_ms: int
    avg_stt_ms: int
    avg_llm_ms: int
    recent_total_ms: tuple[int, ...] = field(default_factory=tuple)
    # Per-turn stacked latencies — index-aligned with recent_total_ms.
    # The UI renders these as stacked bars (STT bottom, LLM middle,
    # TTS top) so the operator can see where each turn's budget went.
    recent_stt_ms: tuple[int, ...] = field(default_factory=tuple)
    recent_llm_ms: tuple[int, ...] = field(default_factory=tuple)
    recent_tts_ms: tuple[int, ...] = field(default_factory=tuple)


_MAX_SAMPLES = 20


class StatsCollector:
    """Rolling averages over the last N turns. N=20 matches the visual
    smoothness of the HUD — older turns fall off the window so the
    display keeps up with the user's current conditions (network jitter,
    model reloads) rather than dragging in a week of old averages."""

    def __init__(self) -> None:
        self._started_monotonic = time.monotonic()
        self._turns_total = 0
        self._turns_success = 0
        self._wake_fires = 0
        self._errors = 0
        self._responses = 0
        self._last: dict[str, int] = {"stt": 0, "llm": 0, "tts": 0, "total": 0}
        self._samples: dict[str, deque[int]] = {
            "stt": deque(maxlen=_MAX_SAMPLES),
            "llm": deque(maxlen=_MAX_SAMPLES),
            "total": deque(maxlen=_MAX_SAMPLES),
        }

    def record_latency(self, component: str, ms: int) -> None:
        self._last[component] = int(ms)
        if component in self._samples:
            self._samples[component].append(int(ms))

    def record_turn(self, success: bool) -> None:
        self._turns_total += 1
        if success:
            self._turns_success += 1
        else:
            self._errors += 1

    def record_wake(self) -> None:
        self._wake_fires += 1

    def record_response(self) -> None:
        self._responses += 1

    def snapshot(self) -> StatsSnapshot:
        return StatsSnapshot(
            turns_total=self._turns_total,
            turns_success=self._turns_success,
            wake_fires=self._wake_fires,
            errors=self._errors,
            responses=self._responses,
            uptime_seconds=int(time.monotonic() - self._started_monotonic),
            last_total_ms=self._last.get("total", 0),
            last_stt_ms=self._last.get("stt", 0),
            last_llm_ms=self._last.get("llm", 0),
            last_tts_ms=self._last.get("tts", 0),
            avg_total_ms=_avg(self._samples["total"]),
            avg_stt_ms=_avg(self._samples["stt"]),
            avg_llm_ms=_avg(self._samples["llm"]),
            recent_total_ms=tuple(self._samples["total"]),
            recent_stt_ms=tuple(self._samples["stt"]),
            recent_llm_ms=tuple(self._samples["llm"]),
            # TTS timing isn't tracked per-turn (TTS runs async after the
            # worker's process call returns) — surface an empty tuple so
            # the stacked-bar widget just renders STT + LLM bands and
            # leaves the TTS band out when it would be all zeros.
            recent_tts_ms=(),
        )


def _avg(samples: "deque[int]") -> int:
    if not samples:
        return 0
    return int(sum(samples) / len(samples))
