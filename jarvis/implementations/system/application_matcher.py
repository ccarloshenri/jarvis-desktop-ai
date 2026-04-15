from __future__ import annotations

import difflib
import re
from pathlib import Path

from jarvis.models.application_candidate import ApplicationCandidate


class ApplicationMatcher:
    def score(self, query: str, candidate: ApplicationCandidate) -> float:
        normalized_query = self._normalize(query)
        candidate_name = self._normalize(candidate.name)
        candidate_stem = self._normalize(candidate.path.stem)

        if normalized_query in {candidate_name, candidate_stem}:
            return 10_000.0

        score = 0.0
        if self._regex_match(normalized_query, candidate_name) or self._regex_match(normalized_query, candidate_stem):
            score += 700.0
        if normalized_query in candidate_name or normalized_query in candidate_stem:
            score += 550.0
        if candidate_name in normalized_query or candidate_stem in normalized_query:
            score += 350.0

        score += difflib.SequenceMatcher(None, normalized_query, candidate_name).ratio() * 250.0
        score += difflib.SequenceMatcher(None, normalized_query, candidate_stem).ratio() * 200.0

        query_tokens = set(normalized_query.split())
        name_tokens = set(candidate_name.split())
        shared_tokens = query_tokens & name_tokens
        score += len(shared_tokens) * 45.0

        if candidate.path.suffix.lower() == ".exe":
            score += 10.0
        return score

    def _regex_match(self, query: str, candidate_name: str) -> bool:
        pattern = re.escape(query).replace(r"\ ", r".*")
        return re.search(pattern, candidate_name, re.IGNORECASE) is not None

    def _normalize(self, value: str) -> str:
        return " ".join(Path(value).stem.lower().replace("_", " ").replace("-", " ").split())
