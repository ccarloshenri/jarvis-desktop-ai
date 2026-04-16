from __future__ import annotations

from jarvis.apps.discord.interfaces import IDiscordKeyboardController


class DiscordPresenceService:
    """Status and custom-text changes.

    Discord exposes no global hotkey for the status menu, so this is a
    placeholder implementation. The user gets a clear "not implemented"
    so the LLM/UI surfaces the limitation honestly instead of pretending
    to have done something. A future RPC backend will replace this.
    """

    def __init__(self, controller: IDiscordKeyboardController) -> None:
        self._controller = controller

    def set_status(self, status: str, custom_text: str | None = None) -> bool:
        # Intentionally returns False — see class docstring.
        return False
