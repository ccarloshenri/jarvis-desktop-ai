from __future__ import annotations

from typing import Protocol


class IDiscordKeyboardController(Protocol):
    """Low-level driver: focus the Discord window and inject keystrokes/text.

    A Protocol (not ABC) so tests can pass a plain dataclass spy without
    inheriting anything.
    """

    def is_running(self) -> bool: ...

    def launch(self) -> bool: ...

    def close(self) -> bool: ...

    def focus_window(self) -> bool: ...

    def quick_switcher(self, query: str) -> bool:
        """Open Ctrl+K, type the query, press Enter."""

    def type_text(self, text: str) -> None: ...

    def press_enter(self) -> None: ...

    def hotkey_toggle_mute(self) -> None: ...

    def hotkey_toggle_deafen(self) -> None: ...

    def hotkey_previous_channel(self) -> None: ...
