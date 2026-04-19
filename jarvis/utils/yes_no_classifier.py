"""Lightweight pt-BR yes/no classifier for confirmation turns.

Why not ask the LLM: the confirmation turn's only job is a binary read,
and the LLM already costs ~2.5s per call. Running a second LLM request
just to classify "sim" vs "não" would double the confirmation latency
with zero accuracy gain over a handful of regex patterns that cover
99% of how Portuguese speakers confirm or deny something out loud.

Returns:
- YES when the utterance clearly affirms ("sim", "isso mesmo", "pode")
- NO when it clearly denies ("não", "errado", "cancela")
- UNKNOWN when neither — caller should treat it as a brand-new command
"""

from __future__ import annotations

import re
import unicodedata
from enum import Enum


class YesNoAnswer(str, Enum):
    YES = "yes"
    NO = "no"
    UNKNOWN = "unknown"


# Word-boundary patterns so "não" matches but "nao ser" also matches; the
# leading wake-word ("Jarvis, ...") is trimmed by the assistant before
# this classifier runs, so a stray "Jarvis" shouldn't reach us.
# "não" comes first in the NO list so "não sim" (rare, contradictory)
# resolves to NO rather than YES.
# Patterns chosen conservatively: we'd rather classify an ambiguous reply
# as UNKNOWN (→ drop the pending confirmation, let the user start fresh)
# than guess wrong and execute the wrong command. Short filler words like
# "é", "ok", "foi" are deliberately excluded because they double as
# sentence connectors in unrelated utterances.
_NO_WORDS = (
    r"\bnao\b",
    r"\bnegativo\b",
    r"\berrado\b",
    r"\bcancela(r)?\b",
    r"\berrei\b",
    r"\bnao e\b",
    r"\bnao eh\b",
    r"\bnao foi\b",
    r"\bnao e isso\b",
    r"\boutra\b",  # "toca outra" in reply usually signals "no, different one"
)
_YES_WORDS = (
    r"\bsim\b",
    r"\bisso\b",
    r"\bisso mesmo\b",
    r"\bexato\b",
    r"\bexatamente\b",
    r"\bconfirma(r)?\b",
    r"\bcorreto\b",
    r"\buhum\b",
    r"\bpositivo\b",
    r"\bpode ser\b",
)

_NO_RE = re.compile("|".join(_NO_WORDS), re.IGNORECASE)
_YES_RE = re.compile("|".join(_YES_WORDS), re.IGNORECASE)


def classify(utterance: str) -> YesNoAnswer:
    normalized = _strip_accents((utterance or "").strip().lower())
    if not normalized:
        return YesNoAnswer.UNKNOWN
    # Check NO first: "não, toca outra coisa" contains "toca" which could
    # look like an affirmation, but the explicit "não" dominates.
    if _NO_RE.search(normalized):
        return YesNoAnswer.NO
    if _YES_RE.search(normalized):
        return YesNoAnswer.YES
    return YesNoAnswer.UNKNOWN


def _strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))
