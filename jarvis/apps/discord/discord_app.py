from __future__ import annotations

import logging

from jarvis.apps.base_app import BaseApp
from jarvis.apps.discord.context_resolver import ContextResolver
from jarvis.apps.discord.discord_context import DiscordContext
from jarvis.apps.discord.interfaces import IDiscordKeyboardController
from jarvis.apps.discord.services.discord_message_service import DiscordMessageService
from jarvis.apps.discord.services.discord_navigation_service import DiscordNavigationService
from jarvis.apps.discord.services.discord_presence_service import DiscordPresenceService
from jarvis.apps.discord.services.discord_voice_service import DiscordVoiceService
from jarvis.enums.action_type import ActionType
from jarvis.models.action_result import ActionResult
from jarvis.models.command import Command

LOGGER = logging.getLogger(__name__)

_DISCORD_ACTIONS = {
    ActionType.DISCORD_OPEN,
    ActionType.DISCORD_CLOSE,
    ActionType.DISCORD_FOCUS,
    ActionType.DISCORD_OPEN_DM,
    ActionType.DISCORD_OPEN_SERVER,
    ActionType.DISCORD_OPEN_CHANNEL,
    ActionType.DISCORD_SEND_MESSAGE,
    ActionType.DISCORD_REPLY_CURRENT,
    ActionType.DISCORD_TOGGLE_MUTE,
    ActionType.DISCORD_TOGGLE_DEAFEN,
    ActionType.DISCORD_JOIN_VOICE,
    ActionType.DISCORD_LEAVE_VOICE,
    ActionType.DISCORD_SET_STATUS,
    ActionType.DISCORD_PREVIOUS,
}


class DiscordApp(BaseApp):
    """Facade aggregating Discord context + services behind a single execute()."""

    def __init__(
        self,
        controller: IDiscordKeyboardController,
        context: DiscordContext | None = None,
        resolver: ContextResolver | None = None,
    ) -> None:
        self._controller = controller
        self._context = context or DiscordContext()
        self._resolver = resolver or ContextResolver()
        self._navigation = DiscordNavigationService(controller, self._context)
        self._messages = DiscordMessageService(controller, self._navigation, self._context)
        self._voice = DiscordVoiceService(controller, self._navigation, self._context)
        self._presence = DiscordPresenceService(controller)

    @property
    def name(self) -> str:
        return "discord"

    @property
    def context(self) -> DiscordContext:
        return self._context

    def can_handle(self, command: Command) -> bool:
        return command.action in _DISCORD_ACTIONS

    def execute(self, command: Command) -> ActionResult:
        action = command.action
        params = command.parameters or {}
        try:
            if action == ActionType.DISCORD_OPEN:
                ok = self._navigation.open_app()
                return self._result(ok, command, "Opened Discord." if ok else "Could not open Discord.")
            if action == ActionType.DISCORD_CLOSE:
                ok = self._navigation.close_app()
                return self._result(ok, command, "Closed Discord." if ok else "Discord was not running.")
            if action == ActionType.DISCORD_FOCUS:
                ok = self._navigation.focus()
                return self._result(ok, command, "Focused Discord." if ok else "Could not focus Discord.")
            if action == ActionType.DISCORD_OPEN_DM:
                target = self._resolve_user(command, params)
                if not target:
                    return self._result(False, command, "Missing user name for DM.")
                ok = self._navigation.open_dm(target)
                return self._result(ok, command, f"Opened DM with {target}.")
            if action == ActionType.DISCORD_OPEN_SERVER:
                server = (params.get("server_name") or command.target or "").strip()
                if not server:
                    return self._result(False, command, "Missing server name.")
                ok = self._navigation.open_server(server)
                return self._result(ok, command, f"Opened server {server}.")
            if action == ActionType.DISCORD_OPEN_CHANNEL:
                channel = (params.get("channel_name") or command.target or "").strip()
                server = (params.get("server_name") or "").strip() or None
                if not channel:
                    return self._result(False, command, "Missing channel name.")
                ok = self._navigation.open_channel(channel, server_name=server)
                return self._result(ok, command, f"Opened channel {channel}.")
            if action == ActionType.DISCORD_SEND_MESSAGE:
                return self._handle_send_message(command, params)
            if action == ActionType.DISCORD_REPLY_CURRENT:
                message = (params.get("message") or command.target or "").strip()
                if not message:
                    return self._result(False, command, "Empty message.")
                ok = self._messages.reply_current(message)
                return self._result(ok, command, "Replied in current conversation.")
            if action == ActionType.DISCORD_TOGGLE_MUTE:
                ok = self._voice.toggle_mute()
                return self._result(ok, command, "Toggled mic.")
            if action == ActionType.DISCORD_TOGGLE_DEAFEN:
                ok = self._voice.toggle_deafen()
                return self._result(ok, command, "Toggled deafen.")
            if action == ActionType.DISCORD_JOIN_VOICE:
                channel = (params.get("channel_name") or command.target or "").strip()
                if not channel:
                    return self._result(False, command, "Missing voice channel name.")
                ok = self._voice.join_voice(channel)
                return self._result(ok, command, f"Joined voice channel {channel}.")
            if action == ActionType.DISCORD_LEAVE_VOICE:
                ok = self._voice.leave_voice()
                return self._result(ok, command, "Left voice channel.")
            if action == ActionType.DISCORD_SET_STATUS:
                ok = self._presence.set_status(
                    str(params.get("status") or ""),
                    custom_text=params.get("custom_text"),
                )
                return self._result(
                    ok,
                    command,
                    "Status updated." if ok else "Status change is not yet implemented in keyboard mode.",
                )
            if action == ActionType.DISCORD_PREVIOUS:
                ok = self._navigation.previous()
                return self._result(ok, command, "Switched to previous channel.")
        except Exception as exc:  # last-resort guard so the assistant never crashes mid-command
            LOGGER.warning("discord_action_failed", extra={"event_data": {"action": action.value, "error": str(exc)}})
            return self._result(False, command, f"Discord action failed: {exc}")

        return self._result(False, command, f"Unhandled Discord action '{action.value}'.")

    def _handle_send_message(self, command: Command, params: dict) -> ActionResult:
        message = (params.get("message") or "").strip()
        if not message:
            return self._result(False, command, "Empty message.")
        target_type = (params.get("target_type") or "").strip().lower()
        target_name = (params.get("target_name") or command.target or "").strip()

        if target_type == "channel" or (not target_type and params.get("channel_name")):
            channel = (params.get("channel_name") or target_name).strip()
            server = (params.get("server_name") or "").strip() or None
            if not channel:
                return self._result(False, command, "Missing channel for message.")
            ok = self._messages.send_to_channel(channel, message, server_name=server)
            return self._result(ok, command, f"Sent message in #{channel}.")

        if not target_name:
            # Try to resolve from context: "manda mensagem pra ele"
            fallback = self._context.last_user_mentioned or self._context.current_dm
            if fallback:
                target_name = fallback
        if not target_name:
            return self._result(False, command, "Missing recipient for DM.")

        ok = self._messages.send_to_dm(target_name, message)
        return self._result(ok, command, f"Sent DM to {target_name}.")

    def _resolve_user(self, command: Command, params: dict) -> str | None:
        explicit = (params.get("target_name") or params.get("user_name") or command.target or "").strip()
        if explicit:
            self._context.remember_user(explicit)
            return explicit
        return self._context.last_user_mentioned or self._context.current_dm

    def _result(self, success: bool, command: Command, message: str) -> ActionResult:
        return ActionResult(success=success, message=message, action=command.action, target=command.target)
