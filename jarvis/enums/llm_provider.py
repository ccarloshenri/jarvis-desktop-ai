from __future__ import annotations

from enum import Enum


class LLMProvider(Enum):
    GPT = "gpt"
    GEMINI = "gemini"
    CLAUDE = "claude"
    NONE = "none"
