from __future__ import annotations

import logging
import time

from jarvis.interfaces.ispeech_events import ISpeechEvents
from jarvis.interfaces.itext_to_speech import ITextToSpeech

LOGGER = logging.getLogger(__name__)

SVSFDefault = 0
SVSFlagsAsync = 1


class OfflineTTS(ITextToSpeech):
    def __init__(
        self,
        speech_events: ISpeechEvents | None = None,
        language: str = "pt-BR",
    ) -> None:
        self._language = language
        self._speech_events = speech_events
        self._voice = self._create_voice()
        self._select_voice()

    def speak(self, text: str) -> None:
        if self._speech_events is not None:
            self._speech_events.emit_speaking_started(text)
        t0 = time.perf_counter()
        try:
            self._voice.Speak(text, SVSFDefault)
        finally:
            LOGGER.debug(
                "tts_speak_done",
                extra={"event_data": {"speak_ms": int((time.perf_counter() - t0) * 1000), "chars": len(text)}},
            )
            if self._speech_events is not None:
                self._speech_events.emit_speaking_finished(text)

    def _create_voice(self):
        import comtypes.client

        voice = comtypes.client.CreateObject("SAPI.SpVoice")
        voice.Rate = 3
        voice.Volume = 100
        return voice

    def _select_voice(self) -> None:
        voices = list(self._voice.GetVoices())
        descriptions = [self._describe(v) for v in voices]
        LOGGER.debug(
            "tts_voices_available",
            extra={"event_data": {"voices": descriptions}},
        )

        for tier in self._voice_priority():
            for voice, description in zip(voices, descriptions):
                if all(keyword in description for keyword in tier):
                    self._voice.Voice = voice
                    LOGGER.info(
                        "tts_voice_selected",
                        extra={"event_data": {"voice": description, "tier": list(tier)}},
                    )
                    return
        LOGGER.warning(
            "tts_voice_fallback_default",
            extra={"event_data": {"language": self._language}},
        )

    def _describe(self, voice) -> str:
        try:
            return voice.GetDescription().lower()
        except Exception:
            return ""

    def _voice_priority(self) -> tuple[tuple[str, ...], ...]:
        if self._language.lower().startswith("pt"):
            return (
                ("daniel",),
                ("antonio",),
                ("ricardo",),
                ("paulo",),
                ("male", "portuguese"),
                ("male", "brazil"),
                ("male", "portugu"),
                ("portugu",),
                ("brazil",),
            )
        return (
            ("david",),
            ("mark",),
            ("george",),
            ("james",),
            ("male", "english"),
            ("english",),
        )
