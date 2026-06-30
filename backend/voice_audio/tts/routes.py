"""HTTP routes for TTS proxy."""
from __future__ import annotations

import asyncio
import logging
import re
import time
import uuid

import aiohttp
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel

from backend.voice_audio import config
from backend.voice_audio.tts.client import xtts_synthesize_full

logger = logging.getLogger("voice_audio.tts.routes")
router = APIRouter(tags=["voice"])

class TTSRequest(BaseModel):
    text: str
    speaker: str = config.XTTS_SPEAKER
    language: str = config.XTTS_LANGUAGE

@router.post("/tts")
async def tts_endpoint(req: TTSRequest, request: Request):
    """
    TTS proxy for XTTS v2 microservice.

    Buffers the full WAV (cache-friendly) and serializes XTTS calls via
    `_XTTS_SYNTH_SEM` so XTTS is never asked to synthesize two requests in
    parallel. Identical (text|lang|speaker) requests are deduplicated and
    answered from the LRU cache when possible.
    """
    # ---- TTS PERF instrumentation (timing only, no behavior change) ----
    _tts_req_id = f"tts_{uuid.uuid4().hex[:6]}"
    _t_received = time.perf_counter()
    _client_ip = (request.client.host if request and request.client else "?")
    _is_prefetch = (request.headers.get("X-TTS-Prefetch", "").lower() in ("1", "true", "yes")
                    or request.headers.get("Purpose", "").lower() == "prefetch") if request else False

    text = req.text.strip()
    if not text:
        logger.info(f"[TTS PERF] {_tts_req_id} request received but empty text — rejecting")
        raise HTTPException(status_code=400, detail="Empty text")

    # Remove emojis to avoid synthesis artefacts
    import re
    text = re.sub(r'[\U00010000-\U0010ffff]', '', text, flags=re.UNICODE).strip()
    if not text:
        logger.info(f"[TTS PERF] {_tts_req_id} text empty after emoji strip — rejecting")
        raise HTTPException(status_code=400, detail="Text empty after cleaning")

    _text_len = len(text)
    _text_preview = text[:60].replace("\n", " ")
    logger.info(
        f"[TTS PERF] {_tts_req_id} request received | client={_client_ip} "
        f"text_len={_text_len} lang={req.language} speaker={req.speaker} "
        f"prefetch_hint={_is_prefetch} preview=\"{_text_preview}\""
    )

    # ---- TTS chunk-size policy guard ----
    # Frontend chunks text into <=80-char pieces before calling /tts. If a
    # longer text slips through (older client / regression), warn loudly.
    _TTS_POLICY_MAX_CHARS = 100
    if _text_len > _TTS_POLICY_MAX_CHARS:
        logger.warning(
            f"[TTS POLICY] long_text_received_for_tts req_id={_tts_req_id} "
            f"chars={_text_len} max={_TTS_POLICY_MAX_CHARS} "
            f"prefetch_hint={_is_prefetch} client={_client_ip} "
            f"preview=\"{_text_preview}\""
        )

    try:
        data = await xtts_synthesize_full(
            text=text, speaker=req.speaker, language=req.language, req_id=_tts_req_id,
        )
    except HTTPException:
        raise
    except aiohttp.ClientConnectorError:
        logger.warning(f"[PIPER PERF] {_tts_req_id} piper service unreachable at {config.XTTS_SERVICE_URL}")
        raise HTTPException(
            status_code=503,
            detail=f"Piper TTS service unavailable at {config.XTTS_SERVICE_URL}. Run: start_piper_service.bat",
        )
    except (asyncio.TimeoutError, TimeoutError):
        logger.warning(f"[PIPER PERF] {_tts_req_id} piper synthesis connect/timeout")
        raise HTTPException(
            status_code=504,
            detail="TTS synthesis timed out. The Piper service may still be loading — please try again in a few seconds.",
        )
    except Exception as e:
        logger.error(f"[TTS PERF] {_tts_req_id} synthesis error: {e}")
        raise HTTPException(status_code=500, detail=f"TTS proxy failed: {e}")

    _t_done = time.perf_counter()
    logger.info(
        f"[TTS PERF] {_tts_req_id} response ready "
        f"| total_proxy_time={int((_t_done - _t_received) * 1000)}ms "
        f"| bytes={len(data)} text_len={_text_len} lang={req.language} "
        f"prefetch_hint={_is_prefetch}"
    )

    return Response(
        content=data,
        media_type="audio/wav",
        headers={
            "Cache-Control": "no-cache",
            "X-TTS-Req-Id": _tts_req_id,
        },
    )
