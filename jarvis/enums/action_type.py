from __future__ import annotations

from enum import Enum


class ActionType(Enum):
    OPEN_APP = "open_app"
    CLOSE_APP = "close_app"
    PLAY_SPOTIFY = "play_spotify"
    SEARCH_WEB = "search_web"
