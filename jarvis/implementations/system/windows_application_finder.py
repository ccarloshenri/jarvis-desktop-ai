from __future__ import annotations

import logging
import os
import time
from pathlib import Path

from jarvis.implementations.system.application_alias_resolver import ApplicationAliasResolver
from jarvis.implementations.system.application_cache import ApplicationCache, _MISSING
from jarvis.implementations.system.application_matcher import ApplicationMatcher
from jarvis.interfaces.iapplication_finder import IApplicationFinder
from jarvis.models.application_candidate import ApplicationCandidate

LOGGER = logging.getLogger(__name__)


class WindowsApplicationFinder(IApplicationFinder):
    def __init__(
        self,
        cache: ApplicationCache | None = None,
        alias_resolver: ApplicationAliasResolver | None = None,
        matcher: ApplicationMatcher | None = None,
        common_start_menu: Path | None = None,
        user_start_menu: Path | None = None,
    ) -> None:
        self._cache = cache or ApplicationCache()
        self._alias_resolver = alias_resolver or ApplicationAliasResolver()
        self._matcher = matcher or ApplicationMatcher()
        app_data = Path(os.getenv("APPDATA", str(Path.home() / "AppData" / "Roaming")))
        self._search_roots = [
            common_start_menu or Path(r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs"),
            user_start_menu or app_data / "Microsoft" / "Windows" / "Start Menu" / "Programs",
        ]

    def prefetch(self) -> None:
        t0 = time.perf_counter()
        self._get_or_scan_candidates()
        LOGGER.debug(
            "finder_prefetch_done",
            extra={"event_data": {"prefetch_ms": int((time.perf_counter() - t0) * 1000)}},
        )

    def find(self, name: str) -> str | None:
        t0 = time.perf_counter()
        normalized_name = self._alias_resolver.normalize(name)
        cached_path = self._cache.get_path(normalized_name)
        if cached_path is not _MISSING:
            LOGGER.debug(
                "finder_cache_hit",
                extra={"event_data": {"name": name, "normalized": normalized_name, "find_ms": int((time.perf_counter() - t0) * 1000)}},
            )
            return cached_path

        candidates = self._get_or_scan_candidates()
        match_start = time.perf_counter()
        best_candidate = self._select_best_match(normalized_name, candidates)
        resolved_path = str(best_candidate.path) if best_candidate is not None else None
        self._cache.store_path(normalized_name, resolved_path)
        LOGGER.debug(
            "finder_match_done",
            extra={
                "event_data": {
                    "name": name,
                    "normalized": normalized_name,
                    "match_ms": int((time.perf_counter() - match_start) * 1000),
                    "total_ms": int((time.perf_counter() - t0) * 1000),
                    "candidates": len(candidates),
                    "matched": resolved_path,
                }
            },
        )
        return resolved_path

    def _get_or_scan_candidates(self) -> list[ApplicationCandidate]:
        cached_candidates = self._cache.get_candidates()
        if cached_candidates is not None:
            return cached_candidates

        scan_start = time.perf_counter()
        discovered: dict[str, ApplicationCandidate] = {}
        per_root: list[dict[str, int]] = []
        for root in self._search_roots:
            root_start = time.perf_counter()
            found = self._scan_root(root)
            for candidate in found:
                key = str(candidate.path).lower()
                discovered[key] = candidate
            per_root.append(
                {
                    "root": str(root),
                    "count": len(found),
                    "ms": int((time.perf_counter() - root_start) * 1000),
                }
            )

        candidates = list(discovered.values())
        self._cache.store_candidates(candidates)
        LOGGER.debug(
            "finder_scan_done",
            extra={
                "event_data": {
                    "total_scan_ms": int((time.perf_counter() - scan_start) * 1000),
                    "total_candidates": len(candidates),
                    "per_root": per_root,
                }
            },
        )
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
