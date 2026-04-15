from __future__ import annotations

from jarvis.ui.orb_animation_state import OrbAnimationState


def test_orb_state_idle_sample_is_low_intensity() -> None:
    state = OrbAnimationState(base_radius=80.0)
    state.advance(0.2)
    frame = state.sample(1.5)
    assert state.transition == 0.0
    assert 70.0 <= frame.radius <= 90.0
    assert frame.glow_radius > frame.radius


def test_orb_state_speaking_increases_transition_and_energy() -> None:
    state = OrbAnimationState(base_radius=80.0)
    state.set_speaking(True)
    for _ in range(8):
        state.advance(0.12)
    idle_frame = OrbAnimationState(base_radius=80.0).sample(1.5)
    speaking_frame = state.sample(1.5)
    assert state.transition > 0.8
    assert speaking_frame.glow_radius > idle_frame.glow_radius
    assert speaking_frame.arc_rotation > idle_frame.arc_rotation
