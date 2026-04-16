from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ChatRole = Literal["user", "assistant"]


@dataclass(frozen=True, slots=True)
class ChatTurn:
    role: ChatRole
    content: str
