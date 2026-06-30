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

import struct

import numpy as np
import torch
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response, StreamingResponse
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

# ---------------------------------------------------------------------------
# Speaker embedding cache — avoids re-extracting conditioning latents per call
# ---------------------------------------------------------------------------
_speaker_latent_cache: dict[str, tuple] = {}


def _vram_used_mb() -> float:
    if torch.cuda.is_available():
        return torch.cuda.memory_reserved(0) / 1024 ** 2
    return 0.0


def _warmup_speaker(speaker: str) -> bool:
    """Pre-load and cache speaker conditioning latents on GPU.

    For XTTS v2, this extracts ``gpt_cond_latent`` and ``speaker_embedding``
    from the model's speaker manager (loaded at model init from
    ``speakers_xtts.pth``) and pins them to the GPU so subsequent
    ``inference()`` calls skip the lookup overhead entirely.
    """
    if speaker in _speaker_latent_cache:
        return True

    try:
        model = _tts.synthesizer.tts_model
        sm = getattr(model, "speaker_manager", None) or getattr(_tts.synthesizer, "speaker_manager", None)

        if sm is None or not hasattr(sm, "speakers") or not isinstance(sm.speakers, dict):
            logger.warning("Speaker manager not found or empty — caching skipped")
            return False

        if speaker not in sm.speakers:
            logger.warning("Speaker '%s' not in speaker manager (available: %s)", speaker, list(sm.speakers.keys())[:5])
            return False

        spk_data = sm.speakers[speaker]

        # XTTS v2 stores {"gpt_cond_latent": Tensor, "speaker_embedding": Tensor}
        if isinstance(spk_data, dict):
            gpt_cond = spk_data.get("gpt_cond_latent")
            spk_emb  = spk_data.get("speaker_embedding")
        else:
            # Fallback: raw tensor (older Coqui versions)
            logger.info("Speaker data is not a dict — using raw value")
            gpt_cond = None
            spk_emb  = spk_data

        if gpt_cond is None or spk_emb is None:
            logger.warning("Missing gpt_cond_latent or speaker_embedding for '%s'", speaker)
            return False

        device = next(model.parameters()).device if hasattr(model, "parameters") else "cuda"
        if isinstance(gpt_cond, torch.Tensor):
            gpt_cond = gpt_cond.to(device)
        if isinstance(spk_emb, torch.Tensor):
            spk_emb = spk_emb.to(device)

        _speaker_latent_cache[speaker] = (gpt_cond, spk_emb)
        logger.info("Cached speaker latents for '%s' on %s  VRAM=%.0f MB", speaker, device, _vram_used_mb())
        return True

    except Exception as exc:
        logger.warning("Speaker latent caching failed for '%s': %s", speaker, exc)
        return False


def _synthesize_cached(text: str, speaker: str, language: str) -> list:
    """Synthesize using cached speaker latents when available.

    Falls back to the full ``_tts.tts()`` high-level API if the cache
    miss or if the low-level ``inference()`` call fails.
    """
    if speaker in _speaker_latent_cache:
        gpt_cond, spk_emb = _speaker_latent_cache[speaker]
        try:
            model = _tts.synthesizer.tts_model
            with torch.no_grad():
                out = model.inference(text, language, gpt_cond, spk_emb)
            wav = out["wav"]
            if isinstance(wav, torch.Tensor):
                return wav.cpu().squeeze().numpy().tolist()
            return list(wav) if not isinstance(wav, list) else wav
        except Exception as exc:
            logger.warning("Cached inference failed for '%s', falling back: %s", speaker, exc)

    return _tts.tts(text=text, speaker=speaker, language=language)


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

    # Pre-cache default speaker embedding to skip latent extraction on first request
    _speaker_latent_cache.clear()
    _warmup_speaker(DEFAULT_SPEAKER)


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

def _num_to_words(n: int) -> str:
    """Convert an integer to its English word form (supports 0–999,999)."""
    ones = ["", "one", "two", "three", "four", "five", "six", "seven", "eight",
            "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
            "sixteen", "seventeen", "eighteen", "nineteen"]
    tens = ["", "", "twenty", "thirty", "forty", "fifty",
            "sixty", "seventy", "eighty", "ninety"]

    if n == 0:
        return "zero"
    if n < 0:
        return "minus " + _num_to_words(-n)

    parts = []
    if n >= 1_000_000:
        parts.append(_num_to_words(n // 1_000_000) + " million")
        n %= 1_000_000
    if n >= 1000:
        parts.append(_num_to_words(n // 1000) + " thousand")
        n %= 1000
    if n >= 100:
        parts.append(ones[n // 100] + " hundred")
        n %= 100
    if n >= 20:
        t = tens[n // 10]
        o = ones[n % 10]
        parts.append(t + ("-" + o if o else ""))
    elif n > 0:
        parts.append(ones[n])

    return " ".join(parts)


def _clean_text(text: str) -> str:
    """Normalise text so XTTS reads it naturally.

    Handles:
    - Space-separated digits: "4 6 7" → "467" → "four hundred sixty-seven"
    - Numbers in parentheses: (467) → four hundred sixty-seven
    - Fragmented names/words: "Sh ik ab ala" → "Shikabala"
    - Year-like 4-digit numbers: 2024 → twenty twenty-four
    - Markdown bold/italic markers removed
    - Emoji / non-BMP characters removed
    """
    # Strip emojis and non-BMP characters
    text = re.sub(r'[\U00010000-\U0010ffff]', '', text)
    # Strip markdown bold/italic markers
    text = re.sub(r'\*+', '', text)
    # Remove parentheses around numbers: (467) → 467
    text = re.sub(r'\((\d+)\)', r'\1', text)
    # Remove zero-width / hidden characters
    text = re.sub(r'[\u200B-\u200D\uFEFF]', '', text)

    # ---- Currency & symbol expansion (BEFORE number-to-word conversion) ----
    # $39.99 → "thirty-nine dollars and ninety-nine cents"
    def _currency_to_words(m: re.Match) -> str:
        dollars = int(m.group(1))
        cents = int(m.group(2)) if m.group(2) else 0
        parts = []
        if dollars:
            parts.append(_num_to_words(dollars) + (' dollar' if dollars == 1 else ' dollars'))
        if cents:
            if parts:
                parts.append('and')
            parts.append(_num_to_words(cents) + (' cent' if cents == 1 else ' cents'))
        if not parts:
            parts.append('zero dollars')
        return ' '.join(parts)
    text = re.sub(r'\$(\d+)\.(\d{1,2})', _currency_to_words, text)
    # Whole-dollar amounts: $5 → "five dollars"
    text = re.sub(r'\$(\d+)\b', lambda m: _num_to_words(int(m.group(1))) + (' dollar' if int(m.group(1)) == 1 else ' dollars'), text)

    # Percentage: 15% → "fifteen percent"
    text = re.sub(r'(\d+)\s*%', lambda m: _num_to_words(int(m.group(1))) + ' percent', text)

    # Slash notation: /month → "per month", /year → "per year"
    text = re.sub(r'/(month|year|day|week|unit|item|order|hour)', r'per \1', text, flags=re.IGNORECASE)

    # Plus sign: + → "plus"
    text = re.sub(r'\s*\+\s*', ' plus ', text)

    # Stray colons (not inside time like 10:30): remove with natural pause
    text = re.sub(r'\s*:\s*', ', ', text)

    # Stray dollar signs left over (e.g. lone "$")
    text = re.sub(r'\$', '', text)

    # **FIRST: Recombine space-separated digit sequences**
    # "4 6 7" → "467", "2 1 3" → "213"
    # This must happen BEFORE number-to-word conversion
    def _recombine_digit_seq(m: re.Match) -> str:
        digits = m.group(0).replace(' ', '')
        return digits
    text = re.sub(r'\d(?:\s+\d)+', _recombine_digit_seq, text)

    # Ensure letters and digits are separated for clean tokenization
    text = re.sub(r'([A-Za-z])([0-9])', r'\1 \2', text)
    text = re.sub(r'([0-9])([A-Za-z])', r'\1 \2', text)

    # **SECOND: Recombine fragmented words/names BEFORE number conversion**
    # "Sh ik ab ala" → "Shikabala" (uppercase start + 2-3 char lowercase fragments)
    # Exclude common English stop words to avoid false positives
    STOP_WORDS = {"is", "in", "on", "at", "to", "of", "or", "an", "as", "be", "by", "he", "it", "me", "my", "no", "so", "up", "we"}
    toks = text.split(' ')
    i = 0
    out_toks = []
    while i < len(toks):
        tok = toks[i]
        # Match: starts with uppercase AND next token is 2-3 chars AND not a stop word
        if (re.match(r'^[A-Z]', tok) and i + 1 < len(toks) and 
            re.match(r'^[a-z]{2,3}$', toks[i+1]) and toks[i+1] not in STOP_WORDS):
            j = i + 1
            parts = [tok]
            # Gather following 2–3 char lowercase tokens (not stop words)
            while j < len(toks) and re.match(r'^[a-z]{2,3}$', toks[j]) and toks[j] not in STOP_WORDS and len(parts) < 8:
                parts.append(toks[j])
                j += 1
            candidate = ''.join(parts)
            # Only recombine if combined form is plausible (8–20 chars, 3+ fragments)
            if len(parts) >= 3 and 8 <= len(candidate) <= 20:
                out_toks.append(candidate)
                i = j
                continue
        out_toks.append(tok)
        i += 1
    text = ' '.join(out_toks)

    # **THIRD: Convert decimal numbers to words**
    # Handle decimal numbers first (e.g. 3.5 → "three point five")
    def _replace_decimal(m: re.Match) -> str:
        whole = int(m.group(1))
        frac = m.group(2)
        parts = [_num_to_words(whole), 'point']
        for digit in frac:
            parts.append(_num_to_words(int(digit)))
        return ' '.join(parts)
    text = re.sub(r'\b(\d+)\.(\d+)\b', _replace_decimal, text)

    # **FOURTH: Convert remaining whole numbers to words**
    def _replace_number(m: re.Match) -> str:
        n = int(m.group(0))
        # Treat 4-digit numbers as year pairs if in range 1000–2099
        if 1000 <= n <= 2099:
            high, low = divmod(n, 100)
            high_w = _num_to_words(high)
            low_w  = "hundred" if low == 0 else ("oh " + _num_to_words(low) if low < 10 else _num_to_words(low))
            return high_w + " " + low_w
        return _num_to_words(n)

    text = re.sub(r'\b\d+\b', _replace_number, text)

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


def _make_streaming_wav_header(sample_rate: int = 24000, bits_per_sample: int = 16, channels: int = 1) -> bytes:
    """Create a 44-byte WAV header with max-size placeholders for streaming."""
    byte_rate = sample_rate * channels * bits_per_sample // 8
    block_align = channels * bits_per_sample // 8
    header  = struct.pack('<4sI4s', b'RIFF', 0x7FFFFFFF, b'WAVE')
    header += struct.pack('<4sIHHIIHH',
        b'fmt ', 16, 1, channels, sample_rate, byte_rate, block_align, bits_per_sample)
    header += struct.pack('<4sI', b'data', 0x7FFFFFFF)
    return header


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

    def audio_generator():
        global _cuda_poisoned
        t_start = time.perf_counter()
        vram_before = _vram_used_mb()
        first_chunk_latency = None
        header_sent = False

        # Ensure speaker latents are cached (lazy warm-up)
        _warmup_speaker(req.speaker)

        with _model_lock:
            for i, chunk in enumerate(chunks):
                logger.debug("  chunk %d/%d (%d chars): %s", i + 1, len(chunks), len(chunk), chunk[:60])
                try:
                    # ----------------------------------------------------------------
                    # Fast path: inference_stream yields PCM as the GPT decoder runs,
                    # cutting first-byte latency from ~2 s down to ~300-500 ms.
                    # ----------------------------------------------------------------
                    if req.speaker in _speaker_latent_cache:
                        gpt_cond, spk_emb = _speaker_latent_cache[req.speaker]
                        model = _tts.synthesizer.tts_model
                        try:
                            stream_yielded = False
                            with torch.no_grad():
                                for wav_tensor in model.inference_stream(
                                    chunk, req.language, gpt_cond, spk_emb
                                ):
                                    if isinstance(wav_tensor, torch.Tensor):
                                        samples = wav_tensor.cpu().squeeze().numpy()
                                    else:
                                        samples = np.array(wav_tensor, dtype=np.float32)

                                    if samples.size == 0:
                                        continue

                                    audio_int16 = (
                                        np.clip(samples, -1.0, 1.0) * 32767
                                    ).astype(np.int16)
                                    pcm_bytes = audio_int16.tobytes()
                                    if not pcm_bytes:
                                        continue

                                    if first_chunk_latency is None:
                                        first_chunk_latency = (
                                            time.perf_counter() - t_start
                                        ) * 1000
                                        logger.info(
                                            "First chunk latency (stream): %.0f ms",
                                            first_chunk_latency,
                                        )

                                    if not header_sent:
                                        yield _make_streaming_wav_header()
                                        header_sent = True

                                    yield pcm_bytes
                                    stream_yielded = True

                            if stream_yielded:
                                continue  # advance to next text chunk
                            # inference_stream yielded nothing — fall through to full synthesis
                        except Exception as stream_exc:
                            logger.warning(
                                "inference_stream failed for chunk %d (%s) — "
                                "falling back to full synthesis.",
                                i + 1, stream_exc,
                            )

                    # ----------------------------------------------------------------
                    # Fallback: full synthesis (used when latents not cached or
                    # inference_stream raised an exception).
                    # ----------------------------------------------------------------
                    samples = _synthesize_cached(
                        text=chunk,
                        speaker=req.speaker,
                        language=req.language,
                    )
                    if first_chunk_latency is None:
                        first_chunk_latency = (time.perf_counter() - t_start) * 1000
                        logger.info("First chunk latency: %.0f ms", first_chunk_latency)

                    audio_np = np.array(samples, dtype=np.float32)
                    audio_int16 = (np.clip(audio_np, -1.0, 1.0) * 32767).astype(np.int16)
                    pcm_bytes = audio_int16.tobytes()

                    if not header_sent:
                        yield _make_streaming_wav_header()
                        header_sent = True

                    yield pcm_bytes

                except KeyError as exc:
                    logger.error("Unknown speaker '%s': %s", req.speaker, exc)
                    return
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
                        try:
                            torch.cuda.empty_cache()
                        except Exception:
                            pass
                    logger.exception("Synthesis failed on chunk %d: %s", i + 1, exc)
                    return

        latency_ms = (time.perf_counter() - t_start) * 1000
        vram_after = _vram_used_mb()
        logger.info(
            "Done: %d chunk(s) | latency=%.0f ms | VRAM=%.0f MB (first_chunk=%.0f ms)",
            len(chunks), latency_ms, vram_after, first_chunk_latency or 0,
        )

    return StreamingResponse(
        audio_generator(),
        media_type="audio/wav",
        headers={
            "X-Chunks": str(len(chunks)),
            "Content-Disposition": 'attachment; filename="speech.wav"',
            "Cache-Control": "no-cache",
        },
    )

