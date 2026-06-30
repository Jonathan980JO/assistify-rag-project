"""Piper/XTTS HTTP client, cache, and synthesis."""
from __future__ import annotations

import asyncio
import collections
import hashlib
import logging
import time

import aiohttp
from fastapi import HTTPException

from backend.voice_audio.config import XTTS_SERVICE_URL

logger = logging.getLogger("voice_audio.tts.client")

xtts_synth_sem = asyncio.Semaphore(1)
xtts_inflight: dict = {}
xtts_cache: collections.OrderedDict[str, bytes] = collections.OrderedDict()
XTTS_CACHE_MAX_ENTRIES = 64
XTTS_CACHE_MAX_BYTES_PER_ENTRY = 2 * 1024 * 1024
xtts_cache_lock = asyncio.Lock()


def tts_cache_key(text: str, language: str, speaker: str) -> str:
    h = hashlib.sha256()
    h.update((text or "").strip().encode("utf-8", errors="ignore"))
    h.update(b"|")
    h.update((language or "").encode("utf-8", errors="ignore"))
    h.update(b"|")
    h.update((speaker or "").encode("utf-8", errors="ignore"))
    return h.hexdigest()[:16]


def wav_bytes_to_pcm16(wav_bytes: bytes) -> bytes:
    if not wav_bytes:
        return b""
    data = wav_bytes[44:] if len(wav_bytes) >= 44 else wav_bytes
    if len(data) % 2 != 0:
        data = data[:-1]
    return data


async def tts_cache_get(key: str):
    async with xtts_cache_lock:
        data = xtts_cache.get(key)
        if data is not None:
            xtts_cache.move_to_end(key)
        return data


async def tts_cache_put(key: str, data: bytes):
    if not data or len(data) > XTTS_CACHE_MAX_BYTES_PER_ENTRY:
        return
    async with xtts_cache_lock:
        xtts_cache[key] = data
        xtts_cache.move_to_end(key)
        while len(xtts_cache) > XTTS_CACHE_MAX_ENTRIES:
            xtts_cache.popitem(last=False)


async def xtts_synthesize_full(text: str, speaker: str, language: str, req_id: str) -> bytes:
    """Call XTTS microservice once and return the full WAV bytes."""
    key = tts_cache_key(text, language, speaker)

    cached = await tts_cache_get(key)
    if cached is not None:
        logger.info("[TTS CACHE HIT] %s key=%s bytes=%s text_len=%s", req_id, key, len(cached), len(text))
        return cached

    pending = xtts_inflight.get(key)
    if pending is not None and not pending.done():
        logger.info("[TTS QUEUE] %s dedup_wait key=%s text_len=%s", req_id, key, len(text))
        return await pending

    loop = asyncio.get_event_loop()
    fut: asyncio.Future = loop.create_future()
    xtts_inflight[key] = fut

    try:
        t_wait = time.perf_counter()
        logger.info("[TTS QUEUE] %s waiting_for_synth_lock key=%s text_len=%s", req_id, key, len(text))
        async with xtts_synth_sem:
            t_acq = time.perf_counter()
            logger.info(
                "[TTS QUEUE] %s acquired_synth_lock key=%s wait_ms=%s",
                req_id,
                key,
                int((t_acq - t_wait) * 1000),
            )
            timeout = aiohttp.ClientTimeout(total=None, sock_connect=5, sock_read=None)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    f"{XTTS_SERVICE_URL}/synthesize",
                    json={"text": text, "speaker": speaker, "language": language},
                ) as resp:
                    if resp.status != 200:
                        body = await resp.text()
                        raise HTTPException(
                            status_code=502 if resp.status not in (400, 503) else resp.status,
                            detail=f"XTTS service error ({resp.status}): {body[:200]}",
                        )
                    data = await resp.read()
            t_done = time.perf_counter()
            logger.info(
                "[TTS QUEUE] %s released_synth_lock key=%s synth_ms=%s bytes=%s",
                req_id,
                key,
                int((t_done - t_acq) * 1000),
                len(data),
            )
            await tts_cache_put(key, data)
            logger.info("[TTS CACHE STORE] %s key=%s bytes=%s text_len=%s", req_id, key, len(data), len(text))
            fut.set_result(data)
            return data
    except BaseException as e:
        if not fut.done():
            fut.set_exception(e if isinstance(e, Exception) else RuntimeError(str(e)))
        raise
    finally:
        if xtts_inflight.get(key) is fut:
            xtts_inflight.pop(key, None)
