from __future__ import annotations

import time
from pathlib import Path

import pytest

from jarvis.services.tts_engine import PrewarmedPiperEngine, TtsEngineError


class _FakeProcess:
    """Stand-in for subprocess.Popen — captures the text written through
    communicate() and returns configurable stdout bytes."""

    def __init__(self, stdout: bytes = b"PCMDATA", returncode: int = 0) -> None:
        self._stdout = stdout
        self.returncode = returncode
        self.received: bytes | None = None
        self.killed = False

    def communicate(self, input: bytes) -> tuple[bytes, bytes]:
        self.received = input
        return self._stdout, b""

    def kill(self) -> None:
        self.killed = True


class _StubEngine(PrewarmedPiperEngine):
    """PrewarmedPiperEngine that never actually invokes Piper.

    Counts spawn calls so tests can assert on pool behaviour, and skips
    the on-disk `piper_exe`/`model_path` existence checks that the real
    constructor performs.
    """

    def __init__(self, pool_size: int = 2) -> None:
        # Skip PiperEngine.__init__ entirely — its existence checks aren't
        # relevant to the pool behaviour under test.
        self._piper_exe = Path("fake_piper.exe")
        self._model_path = Path("fake_model.onnx")
        self._length_scale = 1.1
        self._sentence_silence_s = 0.3
        self._noise_scale = 0.5
        self._noise_w = 0.7
        self._sample_rate = 22050
        # Pool plumbing — mirror the real __init__ for this part only.
        import queue

        self._pool_size = max(1, pool_size)
        self._pool = queue.Queue(maxsize=self._pool_size)
        self._closed = False
        self.spawn_count = 0
        for _ in range(self._pool_size):
            self._start_refill()

    def _spawn(self):  # type: ignore[override]
        self.spawn_count += 1
        return _FakeProcess()


def _wait_until(predicate, timeout: float = 1.0) -> bool:
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def test_pool_prewarms_at_construction() -> None:
    engine = _StubEngine(pool_size=2)
    # Refill threads are daemonized; wait briefly for them to populate.
    assert _wait_until(lambda: engine._pool.qsize() == 2)
    assert engine.spawn_count == 2


def test_synthesize_uses_prewarmed_then_refills() -> None:
    engine = _StubEngine(pool_size=1)
    assert _wait_until(lambda: engine._pool.qsize() == 1)
    before = engine.spawn_count

    audio = engine.synthesize("Oi")
    assert audio.pcm_bytes == b"PCMDATA"
    assert audio.sample_rate == 22050
    # One process was consumed, and the refill thread should repopulate.
    assert _wait_until(lambda: engine.spawn_count == before + 1)
    assert _wait_until(lambda: engine._pool.qsize() == 1)


def test_synthesize_rejects_empty_text() -> None:
    engine = _StubEngine(pool_size=1)
    with pytest.raises(TtsEngineError):
        engine.synthesize("   ")


def test_close_terminates_prewarmed_processes() -> None:
    engine = _StubEngine(pool_size=2)
    assert _wait_until(lambda: engine._pool.qsize() == 2)
    # Snapshot the processes the queue holds before close so we can assert
    # kill() was called on each.
    processes = list(engine._pool.queue)
    engine.close()
    assert engine._pool.qsize() == 0
    assert all(p.killed for p in processes)
    # Further synthesize() calls fail loudly rather than silently spawning.
    with pytest.raises(TtsEngineError):
        engine.synthesize("oi")


def test_nonzero_returncode_raises() -> None:
    class _FailingEngine(_StubEngine):
        def _spawn(self):  # type: ignore[override]
            self.spawn_count += 1
            return _FakeProcess(stdout=b"", returncode=1)

    engine = _FailingEngine(pool_size=1)
    assert _wait_until(lambda: engine._pool.qsize() == 1)
    with pytest.raises(TtsEngineError):
        engine.synthesize("oi")
