from __future__ import annotations

from jarvis.apps.discord.discord_context import DiscordContext
from jarvis.apps.discord.interfaces import IDiscordKeyboardController
from jarvis.apps.discord.services.discord_navigation_service import DiscordNavigationService


class DiscordMessageService:
    """Sends text messages to a DM, a channel, or the current conversation."""

    def __init__(
        self,
        controller: IDiscordKeyboardController,
        navigation: DiscordNavigationService,
        context: DiscordContext,
    ) -> None:
        self._controller = controller
        self._navigation = navigation
        self._context = context

    def send_to_dm(self, user_name: str, message: str) -> bool:
        if not message.strip():
            return False
        if not self._navigation.open_dm(user_name):
            return False
        return self._type_and_send(message)

    def send_to_channel(self, channel_name: str, message: str, server_name: str | None = None) -> bool:
        if not message.strip():
            return False
        if not self._navigation.open_channel(channel_name, server_name=server_name):
            return False
        return self._type_and_send(message)

    def reply_current(self, message: str) -> bool:
        """Send a message in whatever conversation Discord currently has open.

        Used for "responde ele/essa conversa". Falls back to the last
        remembered target if Discord is not currently focused.
        """
        if not message.strip():
            return False
        if not self._controller.focus_window():
            return False
        if self._context.current_target_label() is None:
            return False
        return self._type_and_send(message)

    def _type_and_send(self, message: str) -> bool:
        self._controller.type_text(message.strip())
        self._controller.press_enter()
        return True
