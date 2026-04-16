from __future__ import annotations

from jarvis.apps.discord.discord_context import DiscordContext
from jarvis.apps.discord.interfaces import IDiscordKeyboardController


class DiscordNavigationService:
    """Open DMs, servers and channels using Discord's quick switcher."""

    def __init__(self, controller: IDiscordKeyboardController, context: DiscordContext) -> None:
        self._controller = controller
        self._context = context

    def open_app(self) -> bool:
        return self._controller.launch()

    def close_app(self) -> bool:
        return self._controller.close()

    def focus(self) -> bool:
        return self._controller.focus_window()

    def open_dm(self, user_name: str) -> bool:
        if not user_name.strip():
            return False
        if not self._ensure_focused():
            return False
        if not self._controller.quick_switcher(user_name.strip()):
            return False
        self._context.remember_dm(user_name)
        return True

    def open_server(self, server_name: str) -> bool:
        if not server_name.strip():
            return False
        if not self._ensure_focused():
            return False
        if not self._controller.quick_switcher(server_name.strip()):
            return False
        self._context.remember_server(server_name)
        return True

    def open_channel(self, channel_name: str, server_name: str | None = None) -> bool:
        if not channel_name.strip():
            return False
        if not self._ensure_focused():
            return False
        # Quick switcher accepts "#channel" syntax to scope channels.
        query = f"#{channel_name.strip()}"
        if not self._controller.quick_switcher(query):
            return False
        self._context.remember_channel(server=server_name, channel=channel_name)
        return True

    def previous(self) -> bool:
        if not self._ensure_focused():
            return False
        self._controller.hotkey_previous_channel()
        return True

    def _ensure_focused(self) -> bool:
        if not self._controller.is_running():
            if not self._controller.launch():
                return False
        return self._controller.focus_window()
