from __future__ import annotations

import math

from jarvis.models.orb_frame import OrbFrame


class OrbAnimationState:
    def __init__(self, base_radius: float = 82.0) -> None:
        self._base_radius = base_radius
        self._speaking = False
        self._transition = 0.0

    @property
    def transition(self) -> float:
        return self._transition

    def set_speaking(self, speaking: bool) -> None:
        self._speaking = speaking

    def advance(self, dt: float) -> None:
        target = 1.0 if self._speaking else 0.0
        smoothing = 1.0 - math.exp(-dt * 5.5)
        self._transition += (target - self._transition) * smoothing

    def sample(self, elapsed: float) -> OrbFrame:
        intensity = self._transition
        idle_wave = math.sin(elapsed * 1.6) * 0.7 + math.sin(elapsed * 0.9) * 0.3
        speaking_wave = math.sin(elapsed * 6.2) * 0.6 + math.sin(elapsed * 3.1) * 0.4
        blended_wave = idle_wave * (1.0 - intensity) + speaking_wave * intensity
        amplitude = 6.0 + 16.0 * intensity
        radius = self._base_radius + blended_wave * amplitude
        glow_radius = radius + 22.0 + intensity * 26.0
        ring_offset = 18.0 + math.sin(elapsed * (1.2 + intensity * 1.4)) * (6.0 + intensity * 10.0)
        arc_rotation = elapsed * (16.0 + intensity * 96.0)
        core_opacity = 0.45 + intensity * 0.35
        return OrbFrame(radius, glow_radius, ring_offset, arc_rotation, core_opacity)
