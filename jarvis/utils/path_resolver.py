from __future__ import annotations

import sys
from pathlib import Path


class PathResolver:
    def __init__(self, project_root: Path) -> None:
        self._project_root = project_root

    def bundled_root(self) -> Path:
        return Path(getattr(sys, "_MEIPASS", self._project_root))

    def resolve_asset(self, relative_path: str) -> Path:
        bundled_path = self.bundled_root() / relative_path
        if bundled_path.exists():
            return bundled_path
        return self._project_root / relative_path

    def resolve_speech(self, preferred: str, fallbacks: tuple[str, ...]) -> Path:
        candidates = (preferred, *fallbacks)
        search_roots = [self.bundled_root() / "speechs", self._project_root / "speechs"]

        for search_root in search_roots:
            for candidate in candidates:
                direct_path = search_root / candidate
                if direct_path.exists():
                    return direct_path
            if search_root.exists():
                for candidate in candidates:
                    recursive_match = next(search_root.rglob(candidate), None)
                    if recursive_match is not None:
                        return recursive_match
        return search_roots[0] / preferred
