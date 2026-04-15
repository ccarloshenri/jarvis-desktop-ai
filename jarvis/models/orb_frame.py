from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OrbFrame:
    radius: float
    glow_radius: float
    ring_offset: float
    arc_rotation: float
    core_opacity: float
