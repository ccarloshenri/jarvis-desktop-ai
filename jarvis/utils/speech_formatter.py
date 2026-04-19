"""Text normalization and sentence-level chunking for the TTS pipeline.

Two reasons this lives outside VoiceService:

1. Chunking is what lets the orchestrator start playback before the whole
   phrase is synthesized. Keeping it pure makes it trivial to test, and
   keeps the Piper-specific code focused on subprocess + PCM handling.

2. format_for_speech is reused for cache keys: two semantically identical
   inputs ("abrindo spotify" / "Abrindo o Spotify.") should resolve to
   the same cached audio, so the cache lookup calls format_for_speech too.
"""

from __future__ import annotations

import re

_PROPER_NOUNS = {
    "spotify": "Spotify",
    "jarvis": "Jarvis",
    "discord": "Discord",
    "youtube": "YouTube",
    "chrome": "Chrome",
    "firefox": "Firefox",
    "windows": "Windows",
    "github": "GitHub",
    "google": "Google",
    "gmail": "Gmail",
}

# Words that read better with a brief pause before them ("abrindo... agora").
# The lookbehind `(?<=\w)` is deliberate: we only insert a pause between two
# word characters — not between punctuation and the next word — so
# "agora. Já" doesn't become "agora.... Já" with four dots.
_PAUSE_BEFORE_WORDS_RE = re.compile(
    r"(?<=\w)\s+(agora|j[aá]|certo|pronto|senhor|senhorita)\b",
    flags=re.IGNORECASE,
)

# Split on sentence enders while keeping the punctuation attached. The
# negative lookbehind `(?<!\.\.)` prevents breaking on "..." — our pause
# marker — which would otherwise fragment "Abrindo o Spotify... agora."
# into two chunks.
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?…])(?<!\.\.)\s+")

# Soft chunk target: long single sentences without punctuation get split by
# commas, semicolons or conjunctions once they exceed the word cap. Going too
# small (3-word chunks) fragments prosody; too large (20+) defeats the
# streaming win. 5-12 is the sweet spot on Piper for pt_BR.
_CHUNK_MIN_WORDS = 5
_CHUNK_MAX_WORDS = 12
_SOFT_BREAK_RE = re.compile(r",|;| e | mas | porque | então ", re.IGNORECASE)


def format_for_speech(text: str) -> str:
    """Normalize casing, add natural pauses, and ensure terminal punctuation.

    Idempotent: running format twice on the same text returns the same
    thing, which matters because the cache uses the formatted string as
    its key.
    """
    t = text.strip()
    if not t:
        return ""
    for lower, proper in _PROPER_NOUNS.items():
        t = re.sub(rf"\b{lower}\b", proper, t, flags=re.IGNORECASE)
    t = _PAUSE_BEFORE_WORDS_RE.sub(r"... \1", t)
    t = re.sub(r"\s+", " ", t).strip()
    if not t:
        return ""
    t = t[0].upper() + t[1:]
    if t[-1] not in ".!?…":
        t += "."
    return t


def chunk_for_speech(text: str) -> list[str]:
    """Split formatted text into synthesizer-sized chunks.

    Strategy:
    - First, split on sentence boundaries (. ! ? …).
    - Any sentence longer than _CHUNK_MAX_WORDS is broken further on soft
      boundaries (commas, conjunctions) into 5-12 word pieces.
    - Trailing punctuation is preserved so Piper doesn't read chunks flat.

    Returns [] for empty input so the caller can skip the synthesis step
    entirely.
    """
    formatted = format_for_speech(text)
    if not formatted:
        return []
    sentences = [s.strip() for s in _SENTENCE_SPLIT_RE.split(formatted) if s.strip()]
    chunks: list[str] = []
    for sentence in sentences:
        words = sentence.split()
        if len(words) <= _CHUNK_MAX_WORDS:
            chunks.append(sentence)
            continue
        chunks.extend(_split_long_sentence(sentence))
    return chunks


def _split_long_sentence(sentence: str) -> list[str]:
    # We split while preserving the separators so "... e ..." stays "e"
    # rather than vanishing. Then we regroup into 5-12 word windows.
    parts = _SOFT_BREAK_RE.split(sentence)
    if len(parts) == 1:
        return _window_by_words(sentence)

    result: list[str] = []
    buffer: list[str] = []
    buffer_words = 0
    for part in parts:
        part = part.strip()
        if not part:
            continue
        word_count = len(part.split())
        if buffer_words + word_count > _CHUNK_MAX_WORDS and buffer_words >= _CHUNK_MIN_WORDS:
            result.append(_join_chunk(buffer))
            buffer, buffer_words = [], 0
        buffer.append(part)
        buffer_words += word_count
    if buffer:
        result.append(_join_chunk(buffer))
    return result


def _window_by_words(sentence: str) -> list[str]:
    # Last-resort splitter when no soft breaks exist: slice on word count.
    # Final chunk keeps the sentence's original terminal punctuation; earlier
    # ones get a comma so the synthesizer doesn't read a hard stop mid-phrase.
    words = sentence.split()
    chunks: list[str] = []
    i = 0
    while i < len(words):
        end = min(i + _CHUNK_MAX_WORDS, len(words))
        window = " ".join(words[i:end])
        if end < len(words):
            window = window.rstrip(".!?…,") + ","
        chunks.append(window)
        i = end
    return chunks


def _join_chunk(parts: list[str]) -> str:
    joined = ", ".join(p.strip().rstrip(",") for p in parts if p.strip())
    if joined and joined[-1] not in ".!?…,":
        joined += ","
    return joined
