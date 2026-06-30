"""faster-whisper transcription."""
from __future__ import annotations

import asyncio
import logging
import re
from collections import Counter
from pathlib import Path
from typing import Any, NamedTuple

import numpy as np

from backend.voice_audio.config import EFFECTIVE_DISABLE_WHISPER
from backend.voice_audio import state
from backend.voice_audio.stt.loader import load_multilingual_whisper_model_if_available

try:
    from config import (
        WHISPER_MODEL_PATH,
        WHISPER_MODEL_SIZE,
        WHISPER_DEVICE,
        WHISPER_COMPUTE_TYPE,
        WHISPER_BEAM_SIZE,
        WHISPER_VAD_FILTER,
    )
except Exception:
    from pathlib import Path as _P
    WHISPER_MODEL_PATH = _P(__file__).resolve().parent.parent.parent / "Models" / "faster-whisper-small"
    WHISPER_MODEL_SIZE = "small.en"
    WHISPER_DEVICE = "cpu"
    WHISPER_COMPUTE_TYPE = "int8"
    WHISPER_BEAM_SIZE = 5
    WHISPER_VAD_FILTER = True

logger = logging.getLogger("voice_audio.stt")

ARABIC_STT_INITIAL_PROMPT: str | None = None


def _has_arabic_script(text: str) -> bool:
    return any('\u0600' <= c <= '\u06FF' for c in str(text or ""))


def _looks_like_english_stt_garbage_for_arabic(text: str, segments: list[Any] | None = None) -> bool:
    """Detect Latin-only transcripts that should not enter RAG in Arabic voice mode."""
    value = re.sub(r"\s+", " ", str(text or "").strip())
    if not value or _has_arabic_script(value):
        return False
    latin_words = re.findall(r"[A-Za-z']+", value)
    if not latin_words:
        return False

    avg_logprobs: list[float] = []
    for segment in segments or []:
        raw_logprob = getattr(segment, "avg_logprob", None)
        if raw_logprob is None:
            continue
        try:
            avg_logprobs.append(float(raw_logprob))
        except (TypeError, ValueError):
            continue

    low_confidence = bool(avg_logprobs and (sum(avg_logprobs) / len(avg_logprobs)) < -0.45)
    short_latin_transcript = len(latin_words) <= 8 or len(value) <= 64
    return low_confidence or short_latin_transcript


def _arabic_stt_unclear(text: str, segments: list[Any] | None = None) -> bool:
    """Return True when an Arabic-mode STT transcript looks unintelligible.

    Generic and conservative — only fires when every signal indicates noise:
    extremely low average decoder log-probability OR a transcript that is
    effectively empty / too short to hold a real Arabic question. Real
    Arabic questions (>=2 Arabic words at normal confidence) pass through.
    """
    value = re.sub(r"\s+", " ", str(text or "").strip())
    if not value:
        return True

    avg_logprobs: list[float] = []
    no_speech_probs: list[float] = []
    for segment in segments or []:
        raw_logprob = getattr(segment, "avg_logprob", None)
        if raw_logprob is not None:
            try:
                avg_logprobs.append(float(raw_logprob))
            except (TypeError, ValueError):
                pass
        raw_no_speech = getattr(segment, "no_speech_prob", None)
        if raw_no_speech is not None:
            try:
                no_speech_probs.append(float(raw_no_speech))
            except (TypeError, ValueError):
                pass

    avg_logprob = (sum(avg_logprobs) / len(avg_logprobs)) if avg_logprobs else 0.0
    avg_no_speech = (sum(no_speech_probs) / len(no_speech_probs)) if no_speech_probs else 0.0

    arabic_chars = sum(1 for c in value if "\u0600" <= c <= "\u06FF")
    arabic_words = [w for w in value.split() if any("\u0600" <= c <= "\u06FF" for c in w)]

    # Treat as unclear if: very few Arabic chars AND not a real word, OR
    # high no-speech probability, OR very low log-probability with short text.
    if arabic_chars < 2:
        return True
    if avg_no_speech and avg_no_speech > 0.85:
        return True
    if avg_logprob and avg_logprob < -1.2 and len(arabic_words) <= 2:
        return True
    return False


def _english_stt_unclear(text: str, segments: list[Any] | None = None) -> bool:
    """Return True when an English-mode STT transcript looks like noise or hallucination.

    Conservative heuristics: low decoder confidence, repeated filler sentences,
    elongated single-character tokens, or very low lexical diversity.
  """
    value = re.sub(r"\s+", " ", str(text or "").strip())
    if not value:
        return True

    avg_logprobs: list[float] = []
    no_speech_probs: list[float] = []
    for segment in segments or []:
        raw_logprob = getattr(segment, "avg_logprob", None)
        if raw_logprob is not None:
            try:
                avg_logprobs.append(float(raw_logprob))
            except (TypeError, ValueError):
                pass
        raw_no_speech = getattr(segment, "no_speech_prob", None)
        if raw_no_speech is not None:
            try:
                no_speech_probs.append(float(raw_no_speech))
            except (TypeError, ValueError):
                pass

    avg_logprob = (sum(avg_logprobs) / len(avg_logprobs)) if avg_logprobs else 0.0
    avg_no_speech = (sum(no_speech_probs) / len(no_speech_probs)) if no_speech_probs else 0.0

    if avg_no_speech and avg_no_speech > 0.7:
        return True
    if avg_logprobs and avg_logprob < -1.1:
        return True

    # Repeated-sentence hallucination (e.g. "I think it's a good idea." x3)
    sentences = [s.strip().lower() for s in re.split(r"[.!?]+", value) if s.strip()]
    if len(sentences) >= 3:
        counts = Counter(sentences)
        if counts.most_common(1)[0][1] >= 3:
            return True
        unique_ratio = len(set(sentences)) / len(sentences)
        if unique_ratio < 0.35:
            return True

    # Elongated token (e.g. "Hiiiii...")
    if re.search(r"(.)\1{9,}", value, re.IGNORECASE):
        return True

    # Low lexical diversity on longer transcripts (e.g. "awkward person" loop)
    words = re.findall(r"[A-Za-z']+", value.lower())
    if len(words) >= 8:
        unique_words = set(words)
        if len(unique_words) / len(words) < 0.35:
            return True

    # Repeated phrase loops (e.g. "awkward person" bigram x4)
    if len(words) >= 10:
        bigrams = list(zip(words, words[1:]))
        if bigrams:
            bigram_counts = Counter(bigrams)
            if bigram_counts.most_common(1)[0][1] >= 3:
                return True

    return False


class TranscriptionResult(NamedTuple):
    text: str
    segments: list
    model_label: str
    transcribe_lang: str
    retry_count: int


def _run_stt_sync(pcm16: np.ndarray, attempt_lang: str):
    from faster_whisper import WhisperModel

    attempt_lang = str(attempt_lang or "en").strip().lower()
    if attempt_lang == "ar":
        if not load_multilingual_whisper_model_if_available() or state.whisper_model_multilingual is None:
            raise RuntimeError(
                "Arabic STT requires the multilingual Whisper model; English-only fallback is disabled."
            )
        model = state.whisper_model_multilingual
        stt_lang = "ar"
        model_label = "multilingual:ar"
    else:
        if state.whisper_model is None and state.WHISPER_AVAILABLE:
            logger.info("Lazy-loading Whisper model for voice endpoint...")
            try:
                state.whisper_model = WhisperModel(
                    str(WHISPER_MODEL_PATH) if WHISPER_MODEL_PATH.exists() else WHISPER_MODEL_SIZE,
                    device=WHISPER_DEVICE,
                    compute_type=WHISPER_COMPUTE_TYPE,
                    download_root=None if WHISPER_MODEL_PATH.exists() else str(WHISPER_MODEL_PATH.parent),
                )
            except Exception as exc:
                logger.error("Failed to lazy-load Whisper model: %s", exc)
        model = state.whisper_model
        stt_lang = "en"
        model_label = "english:en"

    if model is None:
        raise RuntimeError("STT Model could not be loaded or is unavailable.")

    beam = 5 if attempt_lang == "ar" else WHISPER_BEAM_SIZE
    initial_prompt = ARABIC_STT_INITIAL_PROMPT if attempt_lang == "ar" else None
    segs_gen, info = model.transcribe(
        pcm16,
        language=stt_lang,
        beam_size=beam,
        temperature=0.0,
        vad_filter=WHISPER_VAD_FILTER,
        vad_parameters=dict(min_silence_duration_ms=300, threshold=0.3),
        condition_on_previous_text=False,
        compression_ratio_threshold=2.4,
        log_prob_threshold=-1.0,
        no_speech_threshold=0.6,
        word_timestamps=False,
        without_timestamps=True,
        initial_prompt=initial_prompt,
    )
    return list(segs_gen), info, model_label, stt_lang


async def run_transcription(pcm_bytes: bytes, lang: str = "en", timeout: float = 10.0) -> TranscriptionResult:
    requested = str(lang or "en").strip().lower()
    if requested not in {"en", "ar"}:
        requested = "en"
    pcm16 = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
    retry_count = 0
    arabic_mode = requested == "ar"

    async def _attempt(attempt_lang: str):
        loop = asyncio.get_event_loop()
        return await asyncio.wait_for(
            loop.run_in_executor(None, _run_stt_sync, pcm16, attempt_lang),
            timeout=timeout,
        )

    segments_list, _info, model_label, transcribe_lang = await _attempt(requested)
    full_text = " ".join([seg.text.strip() for seg in segments_list]).strip()

    if arabic_mode and _looks_like_english_stt_garbage_for_arabic(full_text, segments_list):
        retry_count += 1
        segments_list, _info, model_label, transcribe_lang = await _attempt("ar")
        full_text = " ".join([seg.text.strip() for seg in segments_list]).strip()

    return TranscriptionResult(
        text=full_text,
        segments=segments_list,
        model_label=model_label,
        transcribe_lang=transcribe_lang,
        retry_count=retry_count,
    )
