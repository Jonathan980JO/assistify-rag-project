"""Voice/STT/TTS configuration flags."""
from __future__ import annotations

import os


def _env_flag_enabled(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


SAMPLE_RATE = 16000

XTTS_SERVICE_URL = os.environ.get("XTTS_SERVICE_URL", os.environ.get("PIPER_SERVICE_URL", "http://127.0.0.1:5002"))
# Alias: Piper is the actual TTS engine (see docs/RAG_RETRIEVAL.md).
PIPER_SERVICE_URL = XTTS_SERVICE_URL
XTTS_SPEAKER = "Claribel Dervla"
XTTS_LANGUAGE = "en"
XTTS_SAMPLE_RATE = 24000
XTTS_MODEL_NAME = "tts_models/multilingual/multi-dataset/xtts_v2"
XTTS_AVAILABLE = True

ASSISTIFY_DISABLE_TTS: bool = _env_flag_enabled("ASSISTIFY_DISABLE_TTS", default=False)
ASSISTIFY_DISABLE_WHISPER: bool = _env_flag_enabled("ASSISTIFY_DISABLE_WHISPER", default=False)
ASSISTIFY_DISABLE_WARMUP: bool = _env_flag_enabled("ASSISTIFY_DISABLE_WARMUP", default=False)
ASSISTIFY_ENABLE_ENGLISH_TTS_WARMUP: bool = _env_flag_enabled("ASSISTIFY_ENABLE_ENGLISH_TTS_WARMUP", default=False)
ASSISTIFY_ENABLE_ARABIC_TTS_WARMUP: bool = _env_flag_enabled("ASSISTIFY_ENABLE_ARABIC_TTS_WARMUP", default=False)
ASSISTIFY_ENABLE_TTS_OPENER_WARMUP: bool = _env_flag_enabled("ASSISTIFY_ENABLE_TTS_OPENER_WARMUP", default=False)

EFFECTIVE_DISABLE_TTS = ASSISTIFY_DISABLE_TTS
EFFECTIVE_DISABLE_WHISPER = ASSISTIFY_DISABLE_WHISPER
EFFECTIVE_DISABLE_WARMUP = ASSISTIFY_DISABLE_WARMUP

VOICE_MIN_TRANSCRIBE_BYTES = 32000  # ~1.0s at 16 kHz mono PCM16
VOICE_MANUAL_STOP_MIN_BYTES = 8000  # ~0.25s minimum for manual stop_recording
# ~16s of PCM16 mono @ 16kHz — prevents buffer overflow on long utterances
VOICE_MAX_BUFFER_BYTES = int(os.environ.get("VOICE_MAX_BUFFER_BYTES", str(16 * 16000 * 2)))
