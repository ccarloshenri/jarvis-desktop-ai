from __future__ import annotations

from jarvis.apps.discord.discord_context import DiscordContext
from jarvis.apps.discord.interfaces import IDiscordKeyboardController
from jarvis.apps.discord.services.discord_navigation_service import DiscordNavigationService


class DiscordVoiceService:
    """Voice channel + mic/deafen controls (UI hotkey driven)."""

    def __init__(
        self,
        controller: IDiscordKeyboardController,
        navigation: DiscordNavigationService,
        context: DiscordContext,
    ) -> None:
        self._controller = controller
        self._navigation = navigation
        self._context = context

    def toggle_mute(self) -> bool:
        if not self._controller.focus_window():
            return False
        self._controller.hotkey_toggle_mute()
        return True

    def toggle_deafen(self) -> bool:
        if not self._controller.focus_window():
            return False
        self._controller.hotkey_toggle_deafen()
        return True

    def join_voice(self, channel_name: str) -> bool:
        # We open the voice channel via quick switcher; Discord auto-joins
        # text channels on click but requires Enter on a voice channel result.
        if not self._navigation.open_channel(channel_name):
            return False
        self._context.remember_voice(channel_name)
        return True

    def leave_voice(self) -> bool:
        # No global hotkey to leave a voice channel. As a best-effort UI move
        # we use Ctrl+Alt+Up to navigate away; the user can also click hangup.
        if not self._controller.focus_window():
            return False
        self._controller.hotkey_previous_channel()
        self._context.forget_voice()
        return True
