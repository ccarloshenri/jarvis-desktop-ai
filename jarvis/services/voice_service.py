"""Local Jarvis-style TTS using the Piper standalone binary (offline).

Why the binary instead of `pip install piper-tts`: on Windows, `piper-tts`
depends on `piper-phonemize`, which has no Windows wheel on PyPI and fails
to build from source on most machines. The standalone binary from the
Piper Github releases ships prebuilt for Windows and Just Works.

Pipeline:
1. `format_for_speech(text)` — normalize punctuation, add pauses, fix
   proper-noun casing, so the synthesizer reads the phrase naturally
   instead of flat.
2. `speak(text)` — format → spawn `piper.exe --model <onnx>` with text on
   stdin and WAV on stdout → play through winsound on Windows.

Voice tuning (for the calm, confident Jarvis feel):
- `--length-scale > 1.0` slightly slows speech.
- `--sentence-silence` adds a natural pause between sentences.
- Proper-noun casing ("Spotify", "Jarvis") avoids flat word-by-word reading.

Setup:
1. Download piper_windows_amd64.zip from
   https://github.com/rhasspy/piper/releases and extract `piper.exe` to
   `<project_root>/tools/piper/piper.exe`.
2. Download a voice model to `<project_root>/models/piper/`:
   https://huggingface.co/rhasspy/piper-voices/tree/main/pt/pt_BR/faber/medium
   (both `.onnx` and `.onnx.json`).
3. Or override paths via env vars `JARVIS_PIPER_EXE` and `JARVIS_VOICE_MODEL`.
"""

from __future__ import annotations

import logging
import re
import subprocess
import sys
import time
from pathlib import Path

from jarvis.interfaces.ispeech_events import ISpeechEvents
from jarvis.interfaces.itext_to_speech import ITextToSpeech

LOGGER = logging.getLogger(__name__)

_LENGTH_SCALE = "1.05"
_SENTENCE_SILENCE_S = "0.25"
_PROPER_NOUNS = {
    "spotify": "Spotify",
    "jarvis": "Jarvis",
    "discord": "Discord",
    "youtube": "YouTube",
    "chrome": "Chrome",
    "firefox": "Firefox",
    "windows": "Windows",
}
_PAUSE_BEFORE_WORDS = r"(agora|j[aá]|certo|pronto|senhor|senhorita)"


class VoiceServiceError(Exception):
    pass


class VoiceService(ITextToSpeech):
    def __init__(
        self,
        piper_exe: Path,
        model_path: Path,
        speech_events: ISpeechEvents | None = None,
        language: str = "pt-BR",
    ) -> None:
        self._piper_exe = Path(piper_exe)
        self._model_path = Path(model_path)
        if not self._piper_exe.exists():
            raise VoiceServiceError(f"Piper executable not found at {self._piper_exe}")
        if not self._model_path.exists():
            raise VoiceServiceError(f"Piper model not found at {self._model_path}")
        self._speech_events = speech_events
        self._language = language

    def speak(self, text: str) -> None:
        formatted = self.format_for_speech(text)
        if not formatted:
            return
        if self._speech_events is not None:
            self._speech_events.emit_speaking_started(formatted)
        t0 = time.perf_counter()
        try:
            wav_bytes = self._synthesize(formatted)
            self._play(wav_bytes)
        except Exception as exc:
            LOGGER.warning("voice_speak_failed", extra={"event_data": {"error": str(exc)}})
        finally:
            LOGGER.debug(
                "voice_speak_done",
                extra={
                    "event_data": {
                        "speak_ms": int((time.perf_counter() - t0) * 1000),
                        "chars": len(formatted),
                    }
                },
            )
            if self._speech_events is not None:
                self._speech_events.emit_speaking_finished(formatted)

    def format_for_speech(self, text: str) -> str:
        t = text.strip()
        if not t:
            return ""
        for lower, proper in _PROPER_NOUNS.items():
            t = re.sub(rf"\b{lower}\b", proper, t, flags=re.IGNORECASE)
        t = re.sub(rf"\s+{_PAUSE_BEFORE_WORDS}\b", r"... \1", t, flags=re.IGNORECASE)
        t = re.sub(r"\s+", " ", t).strip()
        t = t[0].upper() + t[1:]
        if t[-1] not in ".!?…":
            t += "."
        return t

    def _synthesize(self, text: str) -> bytes:
        cmd = [
            str(self._piper_exe),
            "--model",
            str(self._model_path),
            "--length-scale",
            _LENGTH_SCALE,
            "--sentence-silence",
            _SENTENCE_SILENCE_S,
            "--output-raw",
        ]
        try:
            result = subprocess.run(
                cmd,
                input=text.encode("utf-8"),
                capture_output=True,
                check=True,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
        except subprocess.CalledProcessError as exc:
            raise VoiceServiceError(
                f"piper exited with {exc.returncode}: {exc.stderr.decode('utf-8', errors='replace')}"
            ) from exc
        return self._wrap_pcm_as_wav(result.stdout)

    def _wrap_pcm_as_wav(self, pcm_bytes: bytes) -> bytes:
        """Piper --output-raw emits signed 16-bit mono PCM at the model's
        sample rate. We wrap it in a minimal WAV header so winsound can
        play it directly. Reading the model's sample rate from the
        companion .onnx.json keeps this robust across voices."""
        sample_rate = self._read_sample_rate()
        import io
        import wave

        buf = io.BytesIO()
        with wave.open(buf, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            wav.writeframes(pcm_bytes)
        return buf.getvalue()

    def _read_sample_rate(self) -> int:
        config_path = self._model_path.with_suffix(self._model_path.suffix + ".json")
        if not config_path.exists():
            return 22050
        try:
            import json

            payload = json.loads(config_path.read_text(encoding="utf-8"))
            return int(payload.get("audio", {}).get("sample_rate", 22050))
        except Exception:
            return 22050

    def _play(self, wav_bytes: bytes) -> None:
        if sys.platform == "win32":
            import winsound

            winsound.PlaySound(wav_bytes, winsound.SND_MEMORY)
            return
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(wav_bytes)
            tmp_path = tmp.name
        try:
            subprocess.run(["aplay", tmp_path], check=False)
        finally:
            Path(tmp_path).unlink(missing_ok=True)
