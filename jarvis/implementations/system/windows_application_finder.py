from __future__ import annotations

import os
from pathlib import Path

from jarvis.implementations.system.application_alias_resolver import ApplicationAliasResolver
from jarvis.implementations.system.application_cache import ApplicationCache, _MISSING
from jarvis.implementations.system.application_matcher import ApplicationMatcher
from jarvis.interfaces.iapplication_finder import IApplicationFinder
from jarvis.models.application_candidate import ApplicationCandidate


class WindowsApplicationFinder(IApplicationFinder):
    def __init__(
        self,
        cache: ApplicationCache | None = None,
        alias_resolver: ApplicationAliasResolver | None = None,
        matcher: ApplicationMatcher | None = None,
        program_files: Path | None = None,
        program_files_x86: Path | None = None,
        local_app_data: Path | None = None,
        roaming_app_data: Path | None = None,
        common_start_menu: Path | None = None,
        user_start_menu: Path | None = None,
    ) -> None:
        self._cache = cache or ApplicationCache()
        self._alias_resolver = alias_resolver or ApplicationAliasResolver()
        self._matcher = matcher or ApplicationMatcher()
        app_data = Path(os.getenv("APPDATA", str(Path.home() / "AppData" / "Roaming")))
        local_data = Path(os.getenv("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
        self._search_roots = [
            program_files or Path(os.getenv("ProgramFiles", r"C:\Program Files")),
            program_files_x86 or Path(os.getenv("ProgramFiles(x86)", r"C:\Program Files (x86)")),
            local_app_data or local_data,
            roaming_app_data or app_data,
            common_start_menu or Path(r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs"),
            user_start_menu or app_data / "Microsoft" / "Windows" / "Start Menu" / "Programs",
        ]

    def find(self, name: str) -> str | None:
        normalized_name = self._alias_resolver.normalize(name)
        cached_path = self._cache.get_path(normalized_name)
        if cached_path is not _MISSING:
            return cached_path

        candidates = self._get_or_scan_candidates()
        best_candidate = self._select_best_match(normalized_name, candidates)
        resolved_path = str(best_candidate.path) if best_candidate is not None else None
        self._cache.store_path(normalized_name, resolved_path)
        return resolved_path

    def _get_or_scan_candidates(self) -> list[ApplicationCandidate]:
        cached_candidates = self._cache.get_candidates()
        if cached_candidates is not None:
            return cached_candidates

        discovered: dict[str, ApplicationCandidate] = {}
        for root in self._search_roots:
            for candidate in self._scan_root(root):
                key = str(candidate.path).lower()
                discovered[key] = candidate

        candidates = list(discovered.values())
        self._cache.store_candidates(candidates)
        return candidates

    def _scan_root(self, root: Path) -> list[ApplicationCandidate]:
        if not root.exists():
            return []
        discovered: list[ApplicationCandidate] = []
        for pattern in ("*.exe", "*.lnk"):
            for path in root.rglob(pattern):
                if path.is_file():
                    discovered.append(ApplicationCandidate(name=path.stem, path=path))
        return discovered

    def _select_best_match(self, query: str, candidates: list[ApplicationCandidate]) -> ApplicationCandidate | None:
        scored_candidates: list[tuple[float, ApplicationCandidate]] = []
        for candidate in candidates:
            score = self._matcher.score(query, candidate)
            if score > 200.0:
                scored_candidates.append((score, candidate))
        if not scored_candidates:
            return None
        scored_candidates.sort(key=lambda item: item[0], reverse=True)
        return scored_candidates[0][1]
