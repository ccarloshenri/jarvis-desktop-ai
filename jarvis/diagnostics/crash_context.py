from __future__ import annotations

from dataclasses import dataclass, field
from threading import RLock


@dataclass
class CrashContextState:
    provider: str = "unknown"
    current_action: str = ""
    extra: dict[str, str] = field(default_factory=dict)


class CrashContext:
    """Thread-safe mutable context that CrashReporter reads when a crash happens.

    Services update this as they run (selected provider, current command, …) so
    the crash payload reflects what the app was actually doing."""

    def __init__(self) -> None:
        self._state = CrashContextState()
        self._lock = RLock()

    def set_provider(self, provider: str) -> None:
        with self._lock:
            self._state.provider = provider

    def set_current_action(self, action: str) -> None:
        with self._lock:
            self._state.current_action = action

    def update(self, **kwargs: str) -> None:
        with self._lock:
            self._state.extra.update(kwargs)

    def snapshot(self) -> CrashContextState:
        with self._lock:
            return CrashContextState(
                provider=self._state.provider,
                current_action=self._state.current_action,
                extra=dict(self._state.extra),
            )
