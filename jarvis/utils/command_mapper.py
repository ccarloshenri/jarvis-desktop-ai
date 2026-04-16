from __future__ import annotations

from typing import Any

from jarvis.enums.action_type import ActionType
from jarvis.models.command import Command


class CommandMapper:
    """Maps a raw payload (from rule-based or LLM) into a typed Command.

    For backward compatibility the simple `action` + `target` shape still works.
    Richer commands (e.g. Discord) carry extra fields under `parameters`.
    """

    def from_payload(self, payload: dict[str, Any]) -> Command:
        action_value = str(payload.get("action") or "").strip()
        if not action_value:
            raise ValueError("Command payload must contain a non-empty 'action'.")

        action = ActionType(action_value)
        parameters = dict(payload.get("parameters") or {})

        target = str(payload.get("target") or parameters.get("target") or "").strip()

        if not target and not parameters and action not in _TARGETLESS_ACTIONS:
            raise ValueError(f"Command '{action_value}' requires a target or parameters.")

        return Command(action=action, target=target, parameters=parameters)


_TARGETLESS_ACTIONS = {
    ActionType.DISCORD_OPEN,
    ActionType.DISCORD_CLOSE,
    ActionType.DISCORD_FOCUS,
    ActionType.DISCORD_TOGGLE_MUTE,
    ActionType.DISCORD_TOGGLE_DEAFEN,
    ActionType.DISCORD_LEAVE_VOICE,
    ActionType.DISCORD_PREVIOUS,
    ActionType.DISCORD_REPLY_CURRENT,
    ActionType.BROWSER_OPEN,
    ActionType.BROWSER_CLOSE,
    ActionType.BROWSER_FOCUS,
    ActionType.BROWSER_NEW_TAB,
    ActionType.BROWSER_CLOSE_TAB,
    ActionType.BROWSER_NEXT_TAB,
    ActionType.BROWSER_PREV_TAB,
    ActionType.BROWSER_BACK,
    ActionType.BROWSER_FORWARD,
    ActionType.BROWSER_RELOAD,
    ActionType.BROWSER_OPEN_EMAIL,
    ActionType.BROWSER_CHECK_UNREAD,
}
