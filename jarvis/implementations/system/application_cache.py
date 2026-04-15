from __future__ import annotations

from jarvis.models.application_candidate import ApplicationCandidate


class ApplicationCache:
    def __init__(self) -> None:
        self._candidates: list[ApplicationCandidate] | None = None
        self._resolved_paths: dict[str, str | None] = {}

    def get_candidates(self) -> list[ApplicationCandidate] | None:
        return self._candidates

    def store_candidates(self, candidates: list[ApplicationCandidate]) -> None:
        self._candidates = candidates

    def get_path(self, normalized_name: str) -> str | None | object:
        return self._resolved_paths.get(normalized_name, _MISSING)

    def store_path(self, normalized_name: str, path: str | None) -> None:
        self._resolved_paths[normalized_name] = path


_MISSING = object()
