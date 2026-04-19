from __future__ import annotations

import io
import logging
import time
import wave

from jarvis.interfaces.ispeech_to_text import UnintelligibleSpeechError
from jarvis.interfaces.istt_provider import CapturedAudio, ISTTProvider
from jarvis.utils.performance import Category, perf_log

LOGGER = logging.getLogger(__name__)


_LANGUAGE_TO_WHISPER = {
    "pt-BR": "pt",
    "pt-br": "pt",
    "pt": "pt",
    "en-US": "en",
    "en-us": "en",
    "en": "en",
}

# Whisper's `initial_prompt` is the strongest knob we have for short
# command audio: the decoder treats it as conversation so far, which
# heavily biases token probabilities toward the words and phrasings it
# saw. The prompt is intentionally PT-only and free of the wake word —
# the wake word is detected upstream and trimmed from the audio so
# Whisper decodes a clean PT command. Including "Jarvis" here would
# bias the model toward English (the name has strong English
# associations) and produce "Open Spotify" instead of "abre o Spotify".
#
# Verb-tense drift ("abre" → "abriu") was the other field failure: the
# imperative forms are now embedded inside real command sentences so the
# decoder learns the conjugation in context, not as a bare verb list.
_BASE_PROMPT_PT = (
    "Comandos em portugues brasileiro, com nomes proprios em ingles. "
    "Toca Lana Del Rey. Toca Coldplay. Toca Taylor Swift no Spotify. "
    "Toca uma musica do Queen. Toca Beyonce. Pausa a musica. "
    "Pula a musica. Abre o Spotify. Fecha o Discord. Abre o Chrome. "
    "Pesquisa video do Neymar no YouTube. Busca preco de iPhone no Google. "
    "Abre o GitHub. Abre meu email. Abre o Gmail. "
    "Manda mensagem para o Renan no Discord dizendo ola. "
    "Responde dizendo que ja volto. Muta meu microfone. "
    "Entra na call. Sai da call. Foca o Discord. "
    "Proxima aba. Fecha a aba. Abre nova aba. "
    "Que horas sao? Que dia e hoje? Tem feriado esse mes?"
)
_BASE_PROMPT_EN = (
    "Voice commands. "
    "Open Spotify. Close Discord. "
    "Play a Coldplay song. Pause the music. "
    "Skip the song. Open Chrome. "
    "Search a video on YouTube. Search Google. "
    "Open GitHub. Open my email. "
    "Send a message to Renan on Discord. "
    "Reply saying I'll be right back. "
    "Mute my microphone. Join the call. "
    "Leave the call. Focus Discord. "
    "Next tab. Close the tab. "
    "What time is it? What day is today?"
)
_BASE_PROMPT_BY_LANG = {"pt": _BASE_PROMPT_PT, "en": _BASE_PROMPT_EN}

# Keeps the decoder prompt bounded. Whisper's prompt shares the context
# window with the audio — flooding it with 500 app names would reduce
# the effective audio context and hurt long-phrase transcription.
_MAX_VOCABULARY_ENTRIES = 40


class WhisperSTTProvider(ISTTProvider):
    """Local transcription via faster-whisper (CTranslate2 backend).

    Tuned for low-latency command recognition in PT-BR on CPU:
    - `small` model is the default — clearly more accurate than `base` on
      proper names ("Jarvis") and verb tense ("abre" vs "abriu"), at the
      cost of ~1s extra decode. The wake-word reliability matters more
      than the speed savings; `base` was tested and dropped because it
      hallucinated the wake word ("Jarvis" → "Já já vi") often enough to
      kill the UX.
    - `beam_size` controls decode search breadth. Defaulted to 3 because
      beam=1 (greedy) was mishearing proper names and common verbs too
      often in field use ("Abre o Spotify" → "Abra-se por favor",
      "pesquisa" → "visam"); beam=3 catches those with ~30% extra CPU
      decode time — acceptable trade for the accuracy jump. beam=5+
      doesn't improve further on short commands and just adds latency.
    - `vad_filter=True` strips leading/trailing silence inside the model,
      which both speeds up decode and prevents hallucinated filler words
      on empty chunks.
    - `int8` compute type on CPU keeps memory ~250MB for `small` and
      runs faster than float32 on most CPUs.

    The model is loaded lazily on first transcribe() call so app boot
    stays fast and an unused STT (wake-word disabled, text-only session,
    etc.) doesn't pay the ~1-2s load cost or the memory.
    """

    def __init__(
        self,
        model_size: str = "small",
        device: str = "auto",
        compute_type: str = "int8",
        beam_size: int = 3,
    ) -> None:
        self._model_size = model_size
        self._device = device
        self._compute_type = compute_type
        self._beam_size = beam_size
        self._model = None  # type: ignore[var-annotated]
        # Extra entity names (apps installed on this machine, known
        # contacts, recent artists) spliced into the decoder prompt.
        # Built at runtime — never hardcoded — so the vocabulary matches
        # reality and stays honest when apps are uninstalled or contacts
        # change.
        self._vocabulary: tuple[str, ...] = ()

    @property
    def name(self) -> str:
        return "whisper"

    def set_vocabulary(self, entries: list[str]) -> None:
        """Replace the dynamic vocabulary used in the decoder prompt.

        Idempotent. Entries are deduped (case-insensitive) and capped so
        the prompt doesn't balloon into Whisper's token budget — a long
        prompt eats into the audio context window.
        """
        seen: set[str] = set()
        unique: list[str] = []
        for entry in entries:
            cleaned = (entry or "").strip()
            if not cleaned:
                continue
            key = cleaned.lower()
            if key in seen:
                continue
            seen.add(key)
            unique.append(cleaned)
            if len(unique) >= _MAX_VOCABULARY_ENTRIES:
                break
        self._vocabulary = tuple(unique)
        LOGGER.debug(
            "whisper_vocabulary_set",
            extra={"event_data": {"count": len(self._vocabulary)}},
        )

    def warmup(self) -> None:
        """Eagerly load the model so the first listen() doesn't pay the
        load cost and any native/DLL error surfaces at boot (where we can
        log it and fall back) instead of crashing a worker thread."""
        self._ensure_model()

    def _ensure_model(self) -> None:
        if self._model is not None:
            return
        from faster_whisper import WhisperModel

        t0 = time.perf_counter()
        self._model = WhisperModel(
            self._model_size,
            device=self._device,
            compute_type=self._compute_type,
        )
        perf_log(
            Category.STT,
            "whisper model loaded",
            int((time.perf_counter() - t0) * 1000),
            model=self._model_size,
            device=self._device,
            compute_type=self._compute_type,
        )

    def transcribe(self, audio: CapturedAudio, language: str) -> str:
        self._ensure_model()
        whisper_lang = _LANGUAGE_TO_WHISPER.get(language, "pt")
        wav_bytes = _pcm_to_wav(audio)
        t0 = time.perf_counter()
        segments, info = self._model.transcribe(  # type: ignore[union-attr]
            io.BytesIO(wav_bytes),
            language=whisper_lang,
            beam_size=self._beam_size,
            # Short temperature fallback chain — triggers only when the
            # first decode looks hallucinated (compression ratio or
            # log-prob below threshold). On clean audio it's a single
            # greedy pass; on edge cases like "toca Lana Del Rey no
            # Spotify" (where greedy at 0.0 produced "qualquer um de
            # outros hands") the 0.2 retry usually recovers. We cap at
            # 0.4 to avoid the creative-garbage end of the chain.
            temperature=(0.0, 0.2, 0.4),
            # VAD disabled here: we already run Silero VAD upstream to
            # endpoint the capture, so the audio passed in is already
            # trimmed. Running faster-whisper's internal VAD on top of
            # that was occasionally re-splitting a 1.5-2s command on
            # intra-word low-energy frames and producing fragments that
            # Whisper then "bridged" into hallucinated text.
            vad_filter=False,
            condition_on_previous_text=False,
            # Lower no_speech threshold means Whisper is less trigger-
            # happy about declaring a segment silent and dropping it.
            # For short commands the default (0.6) sometimes drops
            # real speech; 0.35 keeps more while still suppressing
            # empty chunks.
            no_speech_threshold=0.35,
            initial_prompt=self._build_prompt(whisper_lang),
        )
        text = " ".join(segment.text.strip() for segment in segments).strip()
        transcribe_ms = int((time.perf_counter() - t0) * 1000)
        perf_log(
            Category.STT,
            "whisper decode",
            transcribe_ms,
            chars=len(text),
            language=whisper_lang,
            lang_prob=round(info.language_probability, 3),
        )
        if not text:
            raise UnintelligibleSpeechError("whisper produced empty transcript")
        return text

    def _build_prompt(self, whisper_lang: str) -> str | None:
        base = _BASE_PROMPT_BY_LANG.get(whisper_lang)
        if base is None:
            return None
        if not self._vocabulary:
            return base
        return f"{base} Nomes conhecidos: {', '.join(self._vocabulary)}."


def _pcm_to_wav(audio: CapturedAudio) -> bytes:
    """Wrap raw PCM in a minimal WAV container. faster-whisper's decoder
    reads anything ffmpeg/soundfile can open; WAV is the cheapest format
    to produce in pure Python."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(audio.channels)
        wav.setsampwidth(audio.sample_width)
        wav.setframerate(audio.sample_rate)
        wav.writeframes(audio.pcm_bytes)
    return buf.getvalue()
