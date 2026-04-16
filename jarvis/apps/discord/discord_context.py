from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

DiscordTargetType = Literal["dm", "channel", "server", "voice"]


@dataclass
class DiscordContext:
    """Mutable conversational state about the user's current Discord activity.

    Lives for the duration of the process. Lets the user say "manda outra
    pra ele" or "responde nessa conversa" without re-specifying who/where.
    """

    current_dm: str | None = None
    current_server: str | None = None
    current_channel: str | None = None
    current_voice_channel: str | None = None
    last_user_mentioned: str | None = None
    last_action: str | None = None
    history: list[str] = field(default_factory=list)

    def remember_dm(self, name: str) -> None:
        cleaned = name.strip()
        if not cleaned:
            return
        self.current_dm = cleaned
        self.last_user_mentioned = cleaned
        self._record(f"open_dm:{cleaned}")

    def remember_server(self, name: str) -> None:
        cleaned = name.strip()
        if not cleaned:
            return
        self.current_server = cleaned
        self._record(f"open_server:{cleaned}")

    def remember_channel(self, server: str | None, channel: str) -> None:
        cleaned_channel = channel.strip()
        if not cleaned_channel:
            return
        if server:
            self.current_server = server.strip()
        self.current_channel = cleaned_channel
        self.current_dm = None
        self._record(f"open_channel:{cleaned_channel}")

    def remember_voice(self, name: str) -> None:
        cleaned = name.strip()
        if not cleaned:
            return
        self.current_voice_channel = cleaned
        self._record(f"join_voice:{cleaned}")

    def forget_voice(self) -> None:
        self.current_voice_channel = None
        self._record("leave_voice")

    def remember_user(self, name: str) -> None:
        cleaned = name.strip()
        if cleaned:
            self.last_user_mentioned = cleaned

    def current_target_label(self) -> str | None:
        if self.current_dm:
            return self.current_dm
        if self.current_channel:
            return self.current_channel
        return None

    def _record(self, action: str) -> None:
        self.last_action = action
        self.history.append(action)
        if len(self.history) > 20:
            self.history.pop(0)
