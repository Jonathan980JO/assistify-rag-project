"""
Piper TTS Microservice
======================
Single-engine TTS for Assistify (replaces XTTS v2).

Runs on:  127.0.0.1:5002   (same port the rest of the system already calls)
Engine:   Piper (CPU only, ONNX runtime). No GPU usage. No conflict with
          Ollama/Qwen which keeps the GPU free.

API contract (kept identical to the previous XTTS service so the backend,
frontend, and TTS proxy do not need protocol changes):

    GET  /health                -> {"status":"ok","engine":"piper",...}
    GET  /voices                -> {"voices":{"en":..., "ar":...}}
    POST /synthesize            -> audio/wav  (16-bit PCM, mono, 24000 Hz)

Synthesize request body:
    {"text": "...", "speaker": "<ignored>", "language": "en" | "ar"}

Language routing (NO auto-detect — controlled by the UI selector):
    "en" / "en-*"  -> English voice  (PIPER_EN_VOICE_PATH)
    "ar" / "ar-*"  -> Arabic voice   (PIPER_AR_VOICE_PATH)
    anything else  -> English voice  (safe default)

Start command (Windows, conda env `assistify_main`):
    %USERPROFILE%\\miniconda3\\envs\\assistify_main\\python.exe ^
        -m uvicorn tts_service.piper_server:app --host 127.0.0.1 --port 5002

Env vars (all optional — defaults point to ./models/piper/{en,ar}/voice.onnx):
    PIPER_EN_VOICE_PATH   absolute path to English .onnx model
    PIPER_AR_VOICE_PATH   absolute path to Arabic .onnx model
    PIPER_OUTPUT_SR       output sample rate (default 24000) — must match
                          what the frontend AudioContext expects.
"""

from __future__ import annotations

import io
import logging
import os
import re
import struct
import time
import wave
from contextlib import asynccontextmanager
from pathlib import Path
from threading import Lock
from typing import Optional

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from piper import PiperVoice  # type: ignore

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("piper_service")


# ---------------------------------------------------------------------------
# Voice paths & config
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent

_DEFAULT_EN_PATH = _PROJECT_ROOT / "models" / "piper" / "en" / "voice.onnx"
_DEFAULT_AR_PATH = _PROJECT_ROOT / "models" / "piper" / "ar" / "voice.onnx"

PIPER_EN_VOICE_PATH = Path(os.environ.get("PIPER_EN_VOICE_PATH", str(_DEFAULT_EN_PATH)))
PIPER_AR_VOICE_PATH = Path(os.environ.get("PIPER_AR_VOICE_PATH", str(_DEFAULT_AR_PATH)))
OUTPUT_SR = int(os.environ.get("PIPER_OUTPUT_SR", "24000"))

# Loaded voice handles + load metadata
_voices: dict[str, PiperVoice] = {}
_voice_paths: dict[str, str] = {}
_voice_native_sr: dict[str, int] = {}
_load_time_s: float = 0.0
_engine_ready: bool = False
_synth_lock = Lock()  # piper-tts inference is not thread-safe across voices


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------
def _load_voice(tag: str, path: Path) -> Optional[PiperVoice]:
    if not path.exists():
        logger.error("[PIPER] voice_missing tag=%s path=%s", tag, path)
        return None
    json_path = path.with_suffix(path.suffix + ".json")
    if not json_path.exists():
        logger.error("[PIPER] voice_config_missing tag=%s json=%s", tag, json_path)
        return None
    t0 = time.perf_counter()
    voice = PiperVoice.load(str(path), config_path=str(json_path), use_cuda=False)
    sr = int(getattr(voice.config, "sample_rate", 22050))
    _voices[tag] = voice
    _voice_paths[tag] = str(path)
    _voice_native_sr[tag] = sr
    logger.info(
        "[PIPER] voice_loaded tag=%s path=%s sample_rate=%d load_ms=%d",
        tag, path.name, sr, int((time.perf_counter() - t0) * 1000),
    )
    return voice


def _load_all_voices() -> None:
    global _load_time_s, _engine_ready
    t0 = time.perf_counter()
    logger.info("[TTS ENGINE] piper")
    logger.info("[PIPER] loading voices en=%s ar=%s", PIPER_EN_VOICE_PATH, PIPER_AR_VOICE_PATH)
    _load_voice("en", PIPER_EN_VOICE_PATH)
    _load_voice("ar", PIPER_AR_VOICE_PATH)
    _load_time_s = time.perf_counter() - t0
    _engine_ready = bool(_voices)
    if _engine_ready:
        logger.info(
            "[PIPER] ready voices=%s output_sr=%d total_load_ms=%d",
            list(_voices.keys()), OUTPUT_SR, int(_load_time_s * 1000),
        )
    else:
        logger.error(
            "[PIPER] not_ready no_voices_loaded — check PIPER_EN_VOICE_PATH / PIPER_AR_VOICE_PATH"
        )


# ---------------------------------------------------------------------------
# FastAPI lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(_app: FastAPI):
    _load_all_voices()
    yield


app = FastAPI(title="Piper TTS Microservice", version="1.0.0", lifespan=lifespan)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_LANG_TO_TAG = {
    "en": "en", "en-us": "en", "en-gb": "en", "en_us": "en", "en_gb": "en",
    "ar": "ar", "ar-sa": "ar", "ar-jo": "ar", "ar_sa": "ar", "ar_jo": "ar",
}


def _resolve_voice_tag(language: str) -> str:
    key = (language or "en").strip().lower().replace("_", "-")
    if key in _LANG_TO_TAG:
        return _LANG_TO_TAG[key]
    base = key.split("-", 1)[0]
    return _LANG_TO_TAG.get(base, "en")


# Light Arabic normalization — keep it minimal so we don't fight Piper's own
# phonemizer. We only:
#   - strip emojis / private-use chars
#   - collapse runs of duplicate Arabic punctuation
#   - leave digits / words intact (Piper handles Arabic digits natively)
_ARABIC_RANGE_RE = re.compile(r"[\u0600-\u06FF]")
_EMOJI_RE = re.compile(r"[\U00010000-\U0010FFFF]", flags=re.UNICODE)
_DUP_AR_PUNCT = re.compile(r"([،؛؟])\1+")


def _normalize_arabic(text: str) -> str:
    text = _EMOJI_RE.sub("", text)
    text = _DUP_AR_PUNCT.sub(r"\1", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _normalize_english(text: str) -> str:
    text = _EMOJI_RE.sub("", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _synthesize_int16(voice: PiperVoice, text: str) -> tuple[np.ndarray, int]:
    """Run Piper synthesis and return (int16_samples, native_sample_rate)."""
    sr = int(getattr(voice.config, "sample_rate", 22050))
    pcm_chunks: list[bytes] = []
    # piper-tts AudioChunk yields raw 16-bit PCM bytes; field name is
    # `audio_int16_bytes` in 1.4.x. Fall back to common alternates for
    # forward/backward compatibility.
    for chunk in voice.synthesize(text):
        data = (
            getattr(chunk, "audio_int16_bytes", None)
            or getattr(chunk, "audio_bytes", None)
            or getattr(chunk, "audio", None)
        )
        if data is None:
            continue
        if isinstance(data, np.ndarray):
            if data.dtype != np.int16:
                data = (np.clip(data, -1.0, 1.0) * 32767).astype(np.int16)
            data = data.tobytes()
        pcm_chunks.append(bytes(data))
    if not pcm_chunks:
        return np.zeros(0, dtype=np.int16), sr
    samples = np.frombuffer(b"".join(pcm_chunks), dtype=np.int16)
    return samples, sr


def _resample_int16(samples: np.ndarray, src_sr: int, dst_sr: int) -> np.ndarray:
    if src_sr == dst_sr or samples.size == 0:
        return samples
    # Use scipy for high-quality polyphase resampling (low latency on CPU)
    from math import gcd
    from scipy.signal import resample_poly  # type: ignore

    g = gcd(src_sr, dst_sr)
    up = dst_sr // g
    down = src_sr // g
    f = samples.astype(np.float32) / 32768.0
    out = resample_poly(f, up, down)
    out = np.clip(out, -1.0, 1.0)
    return (out * 32767.0).astype(np.int16)


def _wav_bytes(samples_int16: np.ndarray, sample_rate: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(samples_int16.tobytes())
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class SynthesizeRequest(BaseModel):
    text: str
    speaker: str = ""        # accepted for API compatibility — ignored by Piper
    language: str = "en"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.get("/health")
def health():
    return {
        "status": "ok" if _engine_ready else "error",
        "engine": "piper",
        "ready": _engine_ready,
        "voices": {tag: _voice_paths.get(tag) for tag in _voices},
        "native_sample_rates": dict(_voice_native_sr),
        "output_sample_rate": OUTPUT_SR,
        "model_load_time_s": round(_load_time_s, 3),
    }


@app.get("/voices")
def list_voices():
    return {
        "engine": "piper",
        "voices": {
            tag: {
                "path": _voice_paths.get(tag),
                "native_sample_rate": _voice_native_sr.get(tag),
            }
            for tag in _voices
        },
        "output_sample_rate": OUTPUT_SR,
    }


@app.post("/synthesize")
def synthesize(req: SynthesizeRequest):
    if not _engine_ready:
        raise HTTPException(status_code=503, detail="Piper voices not loaded")

    text = (req.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Empty text")

    tag = _resolve_voice_tag(req.language)
    voice = _voices.get(tag)
    if voice is None:
        # Fall back to whichever voice IS loaded so we still produce audio
        fallback_tag = next(iter(_voices.keys()), None)
        if fallback_tag is None:
            raise HTTPException(status_code=503, detail="No Piper voices available")
        logger.warning(
            "[PIPER] voice_missing_for_lang requested=%s using=%s",
            req.language, fallback_tag,
        )
        tag = fallback_tag
        voice = _voices[tag]

    if tag == "ar":
        text = _normalize_arabic(text)
    else:
        text = _normalize_english(text)
    if not text:
        raise HTTPException(status_code=400, detail="Text empty after normalization")

    t0 = time.perf_counter()
    try:
        # piper-tts synthesis path is not guaranteed thread-safe, and the
        # backend already serializes /tts via _XTTS_SYNTH_SEM. Add a local
        # lock as a second line of defence.
        with _synth_lock:
            samples, native_sr = _synthesize_int16(voice, text)
    except Exception as e:  # pragma: no cover — surfaced as HTTP 500
        logger.exception("[PIPER PERF] synth_failed tag=%s err=%s", tag, e)
        raise HTTPException(status_code=500, detail=f"Piper synthesis failed: {e}")

    if samples.size == 0:
        raise HTTPException(status_code=500, detail="Piper produced no audio")

    t_synth_ms = int((time.perf_counter() - t0) * 1000)

    t1 = time.perf_counter()
    out_samples = _resample_int16(samples, native_sr, OUTPUT_SR)
    t_resample_ms = int((time.perf_counter() - t1) * 1000)

    wav = _wav_bytes(out_samples, OUTPUT_SR)
    logger.info(
        "[PIPER PERF] tag=%s text_len=%d native_sr=%d out_sr=%d "
        "synth_ms=%d resample_ms=%d wav_bytes=%d",
        tag, len(text), native_sr, OUTPUT_SR,
        t_synth_ms, t_resample_ms, len(wav),
    )
    return Response(content=wav, media_type="audio/wav")
