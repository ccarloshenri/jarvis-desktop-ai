from __future__ import annotations

from jarvis.ui.events import JarvisEventBus


def test_event_bus_keeps_speaking_state_true_until_all_sources_finish() -> None:
    bus = JarvisEventBus()
    states: list[bool] = []
    bus.speaking_state_changed.connect(states.append)
    bus.emit_speaking_started("good_morning.mp3")
    bus.emit_speaking_started("Understood, sir.")
    bus.emit_speaking_finished("good_morning.mp3")
    bus.emit_speaking_finished("Understood, sir.")
    assert states == [True, False]
