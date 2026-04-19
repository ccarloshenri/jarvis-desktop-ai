from __future__ import annotations

import logging
import time

import speech_recognition as sr

from jarvis.interfaces.iaudio_capture import IAudioCapture
from jarvis.interfaces.ispeech_to_text import SpeechTimeoutError
from jarvis.interfaces.istt_provider import CapturedAudio
from jarvis.utils.performance import Category, log, perf_log

LOGGER = logging.getLogger(__name__)


class AudioCapture(IAudioCapture):
    """Microphone capture with energy-based VAD endpointing.

    Wraps `speech_recognition`'s Microphone + Recognizer.listen() — which
    already implements start/end-of-phrase detection via a calibrated energy
    threshold plus a pause timeout. The output is raw PCM handed to an
    ISTTProvider for transcription.

    Keeping this layer thin (rather than rolling our own webrtcvad pipeline)
    is deliberate: the energy-threshold VAD in speech_recognition is battle-
    tested, the mic plumbing handles PyAudio quirks on Windows, and the real
    accuracy win comes from swapping Google for Whisper on the transcription
    side — not from re-implementing endpointing.
    """

    def __init__(
        self,
        recognizer: sr.Recognizer | None = None,
        microphone: sr.Microphone | None = None,
        listen_timeout: int = 2,
        phrase_time_limit: int = 5,
    ) -> None:
        self._recognizer = recognizer or sr.Recognizer()
        # Tuning calibrated against perf logs showing captures stuck at the
        # phrase_time_limit for 2-3s utterances — VAD was reading fan/breath
        # noise as continued speech because dynamic threshold adapted too
        # low. Static threshold + higher floor + tight pause keeps captures
        # close to the actual speech duration.
        self._recognizer.dynamic_energy_threshold = False
        self._recognizer.energy_threshold = 400
        # 0.3s pause closes the recording fast after the user stops speaking.
        # Going lower clips natural micro-pauses inside short commands; this
        # is the lowest value that doesn't hurt phrasing on "Jarvis, abre X".
        self._recognizer.pause_threshold = 0.3
        self._recognizer.phrase_threshold = 0.15
        self._recognizer.non_speaking_duration = 0.2
        # Whisper is trained on 16 kHz mono. Capturing at the device's
        # default (often 44.1 kHz) forces the decoder to resample, which
        # costs accuracy on the small models. Asking PyAudio for 16 kHz
        # directly is cheaper and matches the training distribution.
        self._microphone = microphone or sr.Microphone(sample_rate=16000)
        self._listen_timeout = listen_timeout
        self._phrase_time_limit = phrase_time_limit
        self._calibrated = False

    def recalibrate(self) -> None:
        self._calibrated = False

    def capture(self) -> CapturedAudio:
        with self._microphone as source:
            if not self._calibrated:
                t0 = time.perf_counter()
                self._recognizer.adjust_for_ambient_noise(source, duration=0.8)
                self._calibrated = True
                calibrate_ms = int((time.perf_counter() - t0) * 1000)
                perf_log(
                    Category.VOICE,
                    "mic calibrated",
                    calibrate_ms,
                    energy_threshold=self._recognizer.energy_threshold,
                )
            log(Category.VOICE, "listening for phrase...")
            listen_start = time.perf_counter()
            try:
                audio = self._recognizer.listen(
                    source,
                    timeout=self._listen_timeout,
                    phrase_time_limit=self._phrase_time_limit,
                )
            except sr.WaitTimeoutError as exc:
                raise SpeechTimeoutError("no speech detected") from exc
            listen_ms = int((time.perf_counter() - listen_start) * 1000)

        perf_log(
            Category.VOICE,
            "phrase captured",
            listen_ms,
            audio_bytes=len(audio.frame_data),
            sample_rate=audio.sample_rate,
        )
        return CapturedAudio(
            pcm_bytes=audio.frame_data,
            sample_rate=audio.sample_rate,
            sample_width=audio.sample_width,
            channels=1,
        )
