from __future__ import annotations

import os
import re
from pathlib import Path

_REDACTED = "[REDACTED]"

_KV_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(
            r'(?i)(api[_-]?key|secret|token|password|authorization|bearer)(\s*[:=]\s*)([^\s"\',;]+)'
        ),
        rf"\1\2{_REDACTED}",
    ),
    (re.compile(r"sk-[A-Za-z0-9_\-]{10,}"), _REDACTED),
    (re.compile(r"ghp_[A-Za-z0-9]{20,}"), _REDACTED),
    (re.compile(r"github_pat_[A-Za-z0-9_]{20,}"), _REDACTED),
    (re.compile(r"AIza[0-9A-Za-z_\-]{30,}"), _REDACTED),
    (re.compile(r"xox[baprs]-[A-Za-z0-9\-]{10,}"), _REDACTED),
]


class Sanitizer:
    """Removes personal paths and common secret shapes before text leaves the app."""

    def __init__(self) -> None:
        self._home = str(Path.home())
        username = os.environ.get("USERNAME") or os.environ.get("USER") or ""
        self._username_pattern = (
            re.compile(rf"(?i)\b{re.escape(username)}\b") if username else None
        )

    def sanitize(self, text: str) -> str:
        if not text:
            return text
        cleaned = text.replace(self._home, "~")
        if self._username_pattern is not None:
            cleaned = self._username_pattern.sub("[USER]", cleaned)
        for pattern, replacement in _KV_PATTERNS:
            cleaned = pattern.sub(replacement, cleaned)
        return cleaned

    def sanitize_lines(self, lines: list[str]) -> list[str]:
        return [self.sanitize(line) for line in lines]
