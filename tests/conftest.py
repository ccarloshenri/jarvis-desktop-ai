"""Test-wide setup. Preloads native libraries whose DLL search paths
conflict on Windows — same pattern as `app/main.py` for the runtime.

ctranslate2 (pulled in by faster-whisper) and onnxruntime (pulled in by
Silero VAD) both bundle their own MSVC runtime DLLs on Windows. Whichever
loads first wins, and the other fails with "DLL initialization routine
failed" when it's imported later in the same process. Pytest collects
all tests up front, so imports happen in unpredictable order across the
suite. Forcing both to load here, before any test module is collected,
locks in a deterministic resolution order.
"""

from __future__ import annotations

# Keep the try/except blocks silent — in CI envs without these packages
# installed, the relevant tests are already skipped via their own guards.
try:
    import faster_whisper  # noqa: F401
except ImportError:
    pass

try:
    import onnxruntime  # noqa: F401
except ImportError:
    pass
