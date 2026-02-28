"""
XTTS v2 Microservice
====================
Standalone FastAPI server that runs XTTS v2 on GPU.
Runs in: assistify_xtts conda environment (Python 3.10, torch 2.1.x, transformers 4.40.x)

Start:
    conda activate assistify_xtts
    uvicorn xtts_service.xtts_server:app --host 127.0.0.1 --port 5002 --log-level info

POST /synthesize
    Input:  {"text": "...", "speaker": "Claribel Dervla", "language": "en"}
    Output: audio/wav binary stream

GET /health
    Returns: {"status": "ok", "gpu": "<GPU name>", "vram_used_mb": <float>}

GET /speakers
    Returns: {"speakers": [...]}

POST /reload
    Force-reload the XTTS model (e.g. after a CUDA error).
"""

import io
import logging
import os
import re
import time
import wave
from contextlib import asynccontextmanager
from threading import Lock

import numpy as np
import torch
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("xtts_service")

# ---------------------------------------------------------------------------
# Global model holder — loaded once at startup, reloadable after CUDA errors
# ---------------------------------------------------------------------------
_tts       = None
_gpu_name  = "N/A"
_load_time_s = 0.0
_cuda_poisoned = False      # True after a device-side assert — need reload
_model_lock = Lock()        # Prevent concurrent synthesis during reload

DEFAULT_SPEAKER = "Claribel Dervla"
DEFAULT_LANGUAGE = "en"
MODEL_NAME = "tts_models/multilingual/multi-dataset/xtts_v2"

# XTTS v2 GPT module has a hard token limit.  Keep each synthesis chunk
# well under that limit.  250 characters ≈ ~80 tokens — safe for all text.
MAX_CHUNK_CHARS = 230


def _vram_used_mb() -> float:
    if torch.cuda.is_available():
        return torch.cuda.memory_reserved(0) / 1024 ** 2
    return 0.0


def _load_model():
    """Load XTTS v2 onto GPU.  Call at startup or after a CUDA error."""
    global _tts, _gpu_name, _load_time_s, _cuda_poisoned
    os.environ["COQUI_TOS_AGREED"] = "1"

    # Clear any stale CUDA state before loading
    if torch.cuda.is_available():
        try:
            torch.cuda.empty_cache()
            torch.cuda.synchronize()
        except Exception:
            pass

    logger.info("Loading XTTS v2 model onto GPU...")
    t0 = time.time()
    from TTS.api import TTS  # noqa
    tts = TTS(MODEL_NAME).to("cuda")
    _load_time_s = time.time() - t0
    _tts = tts
    _cuda_poisoned = False

    if torch.cuda.is_available():
        _gpu_name = torch.cuda.get_device_name(0)
        logger.info(
            "XTTS v2 loaded on %s in %.1fs  VRAM: %.0f MB",
            _gpu_name, _load_time_s, _vram_used_mb(),
        )
    else:
        logger.warning("CUDA not available — running on CPU (slow).")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load XTTS model on startup, release on shutdown."""
    _load_model()
    yield
    logger.info("Shutting down XTTS service.")
    global _tts
    del _tts
    _tts = None
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


app = FastAPI(title="XTTS v2 Microservice", version="2.0.0", lifespan=lifespan)


# ---------------------------------------------------------------------------
# Text chunking helpers
# ---------------------------------------------------------------------------

def _clean_text(text: str) -> str:
    """Remove characters that cause out-of-vocabulary CUDA assertions in XTTS."""
    # Strip emojis and non-BMP characters
    text = re.sub(r'[\U00010000-\U0010ffff]', '', text)
    # Strip markdown bold/italic markers
    text = re.sub(r'\*+', '', text)
    # Collapse multiple spaces
    text = re.sub(r' +', ' ', text)
    return text.strip()


def _split_into_chunks(text: str, max_chars: int = MAX_CHUNK_CHARS) -> list[str]:
    """
    Split text into chunks that XTTS can safely synthesize.

    Strategy:
    1. Split on sentence boundaries (. ! ? — and line breaks).
    2. If a single sentence is still too long, split further on commas / semicolons.
    3. Hard-truncate any remaining chunk that exceeds max_chars.
    """
    # Split on sentence-ending punctuation, keeping the delimiter
    raw = re.split(r'(?<=[.!?])\s+', text)

    chunks: list[str] = []
    for sentence in raw:
        sentence = sentence.strip()
        if not sentence:
            continue
        if len(sentence) <= max_chars:
            chunks.append(sentence)
        else:
            # Split further on commas/semicolons/em-dashes
            sub_parts = re.split(r'(?<=[,;—])\s+', sentence)
            current = ""
            for part in sub_parts:
                part = part.strip()
                if not part:
                    continue
                if len(current) + len(part) + 1 <= max_chars:
                    current = (current + " " + part).strip() if current else part
                else:
                    if current:
                        chunks.append(current)
                    # Hard-truncate overlong single parts
                    while len(part) > max_chars:
                        # Try to cut at a word boundary
                        cut = part[:max_chars].rsplit(' ', 1)[0]
                        if not cut:
                            cut = part[:max_chars]
                        chunks.append(cut)
                        part = part[len(cut):].strip()
                    current = part
            if current:
                chunks.append(current)

    return [c for c in chunks if c.strip()]


def _chunks_to_wav(samples_list: list[list]) -> bytes:
    """Concatenate multiple float32 sample lists into a single PCM WAV."""
    all_samples = []
    for samples in samples_list:
        all_samples.extend(samples)

    audio_np = np.array(all_samples, dtype=np.float32)
    audio_int16 = (np.clip(audio_np, -1.0, 1.0) * 32767).astype(np.int16)

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(24000)  # XTTS v2 native sample rate
        wf.writeframes(audio_int16.tobytes())
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class SynthesizeRequest(BaseModel):
    text: str
    speaker: str = DEFAULT_SPEAKER
    language: str = DEFAULT_LANGUAGE


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {
        "status": "error" if _cuda_poisoned else "ok",
        "cuda_poisoned": _cuda_poisoned,
        "model": MODEL_NAME,
        "gpu": _gpu_name,
        "vram_used_mb": round(_vram_used_mb(), 1),
        "model_load_time_s": round(_load_time_s, 2),
        "cuda_available": torch.cuda.is_available(),
    }


@app.post("/reload")
def reload_model():
    """Force-reload the XTTS model — use after a CUDA error."""
    global _tts
    with _model_lock:
        logger.info("Manual reload requested.")
        if _tts is not None:
            del _tts
            _tts = None
        _load_model()
    return {"status": "reloaded", "vram_used_mb": round(_vram_used_mb(), 1)}


@app.get("/speakers")
def list_speakers():
    if _tts is None:
        raise HTTPException(status_code=503, detail="Model not loaded yet")
    try:
        speakers = _tts.speakers if hasattr(_tts, "speakers") else []
        return {"speakers": speakers, "count": len(speakers)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/synthesize")
def synthesize(req: SynthesizeRequest):
    """
    Synthesize speech from text.
    - Automatically chunks long text so XTTS never hits the GPT token limit.
    - Auto-reloads model after a CUDA device-side assert error.
    Returns: audio/wav binary (16-bit PCM, 24 kHz mono)
    """
    global _tts, _cuda_poisoned

    if _tts is None:
        raise HTTPException(status_code=503, detail="Model not loaded yet")

    # If CUDA was poisoned by a previous request, reload the model first
    if _cuda_poisoned:
        logger.warning("CUDA context poisoned — attempting model reload before synthesis")
        with _model_lock:
            if _cuda_poisoned:  # double-check inside lock
                try:
                    if _tts is not None:
                        del _tts
                        _tts = None
                    _load_model()
                    logger.info("Model reloaded successfully after CUDA error.")
                except Exception as reload_err:
                    raise HTTPException(
                        status_code=503,
                        detail=f"XTTS CUDA recovery failed: {reload_err}. Restart the service."
                    )

    text = _clean_text(req.text)
    if not text:
        raise HTTPException(status_code=400, detail="text must not be empty after cleaning")

    chunks = _split_into_chunks(text)
    if not chunks:
        raise HTTPException(status_code=400, detail="text produced no synthesizable chunks")

    logger.info(
        "Synthesizing %d chars in %d chunk(s) | speaker=%s",
        len(text), len(chunks), req.speaker,
    )

    t0 = time.time()
    samples_list: list[list] = []

    with _model_lock:
        for i, chunk in enumerate(chunks):
            logger.debug("  chunk %d/%d (%d chars): %s", i + 1, len(chunks), len(chunk), chunk[:60])
            try:
                samples = _tts.tts(
                    text=chunk,
                    speaker=req.speaker,
                    language=req.language,
                )
                samples_list.append(samples)
            except KeyError as exc:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unknown speaker: {exc}. Use GET /speakers for valid names.",
                )
            except (RuntimeError, Exception) as exc:
                err_str = str(exc)
                is_cuda_err = (
                    "CUDA error" in err_str
                    or "device-side assert" in err_str
                    or "srcIndex < srcSelectDimSize" in err_str
                )
                if is_cuda_err:
                    _cuda_poisoned = True
                    logger.error(
                        "CUDA assertion error on chunk %d — VRAM state poisoned. "
                        "Model will auto-reload on next request. "
                        "Chunk was (%d chars): %s",
                        i + 1, len(chunk), chunk[:120],
                    )
                    # Flush CUDA to avoid further corruption
                    try:
                        torch.cuda.empty_cache()
                    except Exception:
                        pass
                    raise HTTPException(
                        status_code=500,
                        detail=(
                            f"XTTS CUDA error on chunk {i+1}/{len(chunks)}. "
                            "Model will auto-recover on next request. "
                            f"Problematic text ({len(chunk)} chars): '{chunk[:80]}...'"
                        ),
                    )
                logger.exception("Synthesis failed on chunk %d: %s", i + 1, exc)
                raise HTTPException(status_code=500, detail=str(exc))

    latency_ms = (time.time() - t0) * 1000
    logger.info(
        "Done: %d chunk(s) | latency=%.0f ms | VRAM=%.0f MB",
        len(chunks), latency_ms, _vram_used_mb(),
    )

    wav_bytes = _chunks_to_wav(samples_list)
    return Response(
        content=wav_bytes,
        media_type="audio/wav",
        headers={
            "X-Latency-Ms": str(int(latency_ms)),
            "X-VRAM-MB": str(int(_vram_used_mb())),
            "X-Chunks": str(len(chunks)),
            "Content-Disposition": 'attachment; filename="speech.wav"',
        },
    )

