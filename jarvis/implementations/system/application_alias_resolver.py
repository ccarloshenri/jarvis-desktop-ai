from __future__ import annotations


class ApplicationAliasResolver:
    def __init__(self) -> None:
        self._aliases = {
            "vscode": "visual studio code",
            "vs code": "visual studio code",
            "visual studio": "visual studio code",
            "ms word": "microsoft word",
            "word": "microsoft word",
            "excel": "microsoft excel",
            "powerpoint": "microsoft powerpoint",
        }

    def normalize(self, raw_name: str) -> str:
        collapsed = " ".join(raw_name.strip().lower().replace("_", " ").replace("-", " ").split())
        return self._aliases.get(collapsed, collapsed)
