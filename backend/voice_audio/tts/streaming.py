"""WebSocket TTS streaming helpers."""
from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Optional

import aiohttp
from fastapi import WebSocket

from backend.voice_audio import state
from backend.voice_audio.config import (
    EFFECTIVE_DISABLE_TTS,
    XTTS_LANGUAGE,
    XTTS_SERVICE_URL,
    XTTS_SPEAKER,
)
from backend.voice_audio.tts.client import (
    tts_cache_get,
    tts_cache_key,
    tts_cache_put,
    wav_bytes_to_pcm16,
    xtts_synth_sem,
)

from backend.voice_audio.tts.text_utils import (
    normalize_tts_chunk_cache_text,
    preprocess_for_tts,
    split_spoken_text_for_tts,
)

def _arabic_off_topic_response() -> str:
    try:
        from backend.assistify_rag_server import ARABIC_OFF_TOPIC_RESPONSE
        return ARABIC_OFF_TOPIC_RESPONSE
    except Exception:
        return ""


logger = logging.getLogger("voice_audio.tts.streaming")

def ws_tts_is_active(connection_id: str, response_id: str, cancel_event: Optional[asyncio.Event] = None) -> bool:
    if cancel_event is not None and cancel_event.is_set():
        return False
    return state.ws_tts_active_response_ids.get(connection_id) == response_id


def log_tts_cancelled(connection_id: str, response_id: str, reason: str) -> None:
    logger.info(
        "[TTS CHUNK CANCELLED] reason=%s response_id=%s connection_id=%s",
        reason,
        response_id,
        connection_id,
    )


def cancel_active_ws_tts(connection_id: str, reason: str) -> None:
    response_id = state.ws_tts_active_response_ids.pop(connection_id, None)
    task = state.ws_tts_active_tasks.pop(connection_id, None)
    if response_id:
        log_tts_cancelled(connection_id, response_id, reason)
    if task is not None and not task.done():
        task.cancel()


def remember_ws_tts_task(connection_id: str, response_id: str, task: asyncio.Task) -> None:
    state.ws_tts_active_tasks[connection_id] = task

    def _cleanup(done_task: asyncio.Task) -> None:
        if state.ws_tts_active_tasks.get(connection_id) is done_task:
            state.ws_tts_active_tasks.pop(connection_id, None)
        if state.ws_tts_active_response_ids.get(connection_id) == response_id:
            state.ws_tts_active_response_ids.pop(connection_id, None)
        try:
            exc = done_task.exception()
        except asyncio.CancelledError:
            return
        except Exception:
            return
        if exc is not None:
            logger.warning("[ASYNC TTS] task_error response_id=%s error=%s", response_id, exc)

    task.add_done_callback(_cleanup)


async def tts_progressive_response(
    text: str,
    websocket: WebSocket,
    connection_id: str,
    language: str,
    response_id: str,
    *,
    t_meta: Optional[dict] = None,
    cancel_event: Optional[asyncio.Event] = None,
) -> None:
    spoken_text = str(text or "").strip()
    if not spoken_text or EFFECTIVE_DISABLE_TTS:
        return

    chunks = split_spoken_text_for_tts(spoken_text, language)
    preview = re.sub(r"\s+", " ", chunks[0] if chunks else "")[:80]
    logger.info(
        "[TTS CHUNKING] chunks=%s first_chars=%s total_chars=%s",
        len(chunks),
        preview,
        len(spoken_text),
    )
    if not chunks:
        return

    if connection_id not in state.ws_write_locks:
        state.ws_write_locks[connection_id] = asyncio.Lock()
    write_lock = state.ws_write_locks[connection_id]

    async def _ws_send_json(payload: dict) -> None:
        if payload.get("response_id") == response_id and not ws_tts_is_active(connection_id, response_id, cancel_event):
            return
        async with write_lock:
            if payload.get("response_id") == response_id and not ws_tts_is_active(connection_id, response_id, cancel_event):
                return
            await websocket.send_json(payload)

    async def _ws_send_bytes(data: bytes) -> None:
        if not ws_tts_is_active(connection_id, response_id, cancel_event):
            return
        async with write_lock:
            if not ws_tts_is_active(connection_id, response_id, cancel_event):
                return
            await websocket.send_bytes(data)

    local_tts_session = None
    tts_sess = state.tts_session
    if tts_sess is None or tts_sess.closed:
        local_tts_session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=None, sock_connect=5, sock_read=None)
        )
        tts_sess = local_tts_session

    total_chunks = len(chunks)
    audio_started = False
    total_audio_bytes = 0
    try:
        logger.info("[ASYNC TTS] audio_continues_after_done=True response_id=%s", response_id)
        for chunk_index, raw_chunk in enumerate(chunks, start=1):
            if not ws_tts_is_active(connection_id, response_id, cancel_event):
                reason = "user_barge_in" if cancel_event is not None and cancel_event.is_set() else "stale_response"
                log_tts_cancelled(connection_id, response_id, reason)
                return

            clean = normalize_tts_chunk_cache_text(raw_chunk)
            clean = preprocess_for_tts(clean, language=language)
            if not clean:
                continue

            cache_key = tts_cache_key(clean, language, XTTS_SPEAKER)
            cached_wav = await tts_cache_get(cache_key)
            cache_hit = cached_wav is not None
            logger.info(
                "[TTS CHUNK CACHE] hit=%s index=%s/%s language=%s key=%s",
                bool(cache_hit),
                chunk_index,
                total_chunks,
                language,
                cache_key,
            )
            if t_meta is not None:
                t_meta["tts_cache_hit"] = bool(cache_hit)

            chunk_start = time.perf_counter()
            sent_start = False
            emitted_audio = False
            audio_bytes_sent = 0
            wav_accum = bytearray()
            try:
                await _ws_send_json({
                    "type": "ttsAudioStart",
                    "sampleRate": 24000,
                    "response_id": response_id,
                    "chunk_index": chunk_index,
                    "chunk_total": total_chunks,
                })
                sent_start = True
                audio_started = True

                if cached_wav is not None:
                    pcm_data = wav_bytes_to_pcm16(cached_wav)
                    if pcm_data and ws_tts_is_active(connection_id, response_id, cancel_event):
                        if t_meta is not None and not t_meta.get("first_tts_chunk"):
                            t_meta["first_tts_chunk"] = time.perf_counter()
                        await _ws_send_bytes(pcm_data)
                        emitted_audio = True
                        audio_bytes_sent = len(pcm_data)
                    elif not pcm_data:
                        await _ws_send_json({"type": "ttsFallback", "text": clean})
                else:
                    wait_start = time.perf_counter()
                    logger.info(
                        "[TTS QUEUE] progressive waiting_for_synth_lock response_id=%s index=%s/%s text_len=%s lang=%s",
                        response_id,
                        chunk_index,
                        total_chunks,
                        len(clean),
                        language,
                    )
                    async with xtts_synth_sem:
                        wait_done = time.perf_counter()
                        if t_meta is not None:
                            t_meta["tts_wait_ms"] = int(round((wait_done - wait_start) * 1000))
                        if not ws_tts_is_active(connection_id, response_id, cancel_event):
                            reason = "user_barge_in" if cancel_event is not None and cancel_event.is_set() else "stale_response"
                            log_tts_cancelled(connection_id, response_id, reason)
                            return
                        resp = await tts_sess.post(
                            f"{XTTS_SERVICE_URL}/synthesize",
                            json={"text": clean, "speaker": XTTS_SPEAKER, "language": language},
                        )
                        if resp.status == 200:
                            header_skipped = False
                            header_buf = b""
                            pcm_remainder = b""
                            async for chunk in resp.content.iter_chunked(4096):
                                if not ws_tts_is_active(connection_id, response_id, cancel_event):
                                    reason = "user_barge_in" if cancel_event is not None and cancel_event.is_set() else "stale_response"
                                    log_tts_cancelled(connection_id, response_id, reason)
                                    resp.close()
                                    return
                                if chunk:
                                    wav_accum.extend(chunk)
                                if not header_skipped:
                                    header_buf += chunk
                                    if len(header_buf) < 44:
                                        continue
                                    data = header_buf[44:]
                                    header_skipped = True
                                    header_buf = b""
                                    if not data:
                                        continue
                                else:
                                    data = chunk
                                if pcm_remainder:
                                    data = pcm_remainder + data
                                    pcm_remainder = b""
                                if len(data) % 2 != 0:
                                    pcm_remainder = data[-1:]
                                    data = data[:-1]
                                if data:
                                    if t_meta is not None and not t_meta.get("first_tts_chunk"):
                                        t_meta["first_tts_chunk"] = time.perf_counter()
                                    await _ws_send_bytes(data)
                                    emitted_audio = True
                                    audio_bytes_sent += len(data)
                            resp.close()
                            if emitted_audio and wav_accum and ws_tts_is_active(connection_id, response_id, cancel_event):
                                await tts_cache_put(cache_key, bytes(wav_accum))
                                logger.info(
                                    "[WS TTS CACHE] stored=True language=%s key=%s bytes=%s text_len=%s",
                                    language,
                                    cache_key,
                                    len(wav_accum),
                                    len(clean),
                                )
                        else:
                            detail = await resp.text()
                            resp.close()
                            logger.warning("Progressive TTS returned %s: %s", resp.status, detail[:100])
                            await _ws_send_json({"type": "ttsFallback", "text": clean})
                if emitted_audio and t_meta is not None:
                    now = time.perf_counter()
                    t_meta["xtts_last_chunk"] = now
                    t_meta["audio_bytes"] = int(t_meta.get("audio_bytes") or 0) + audio_bytes_sent
                total_audio_bytes += audio_bytes_sent
            finally:
                if sent_start:
                    try:
                        await _ws_send_json({
                            "type": "ttsAudioEnd",
                            "response_id": response_id,
                            "chunk_index": chunk_index,
                            "chunk_total": total_chunks,
                        })
                    except Exception:
                        pass
                synth_ms = int(round((time.perf_counter() - chunk_start) * 1000))
                if t_meta is not None:
                    t_meta["tts_ms"] = int(t_meta.get("tts_ms") or 0) + synth_ms
                    t_meta["tts_synthesis_ms"] = int(t_meta.get("tts_synthesis_ms") or 0) + (0 if cache_hit else synth_ms)
                logger.info("[TTS CHUNK] index=%s/%s synth_ms=%s", chunk_index, total_chunks, synth_ms)
                await asyncio.sleep(0)

        if ws_tts_is_active(connection_id, response_id, cancel_event):
            await _ws_send_json({
                "type": "ttsComplete",
                "response_id": response_id,
                "chunks": total_chunks,
                "audio_bytes": total_audio_bytes,
            })
            logger.info(
                "[ASYNC TTS] complete response_id=%s chunks=%s audio_bytes=%s audio_started=%s",
                response_id,
                total_chunks,
                total_audio_bytes,
                bool(audio_started),
            )
    except asyncio.CancelledError:
        log_tts_cancelled(connection_id, response_id, "user_barge_in" if cancel_event is not None and cancel_event.is_set() else "task_cancelled")
        raise
    except Exception as exc:
        logger.warning("[ASYNC TTS] error response_id=%s error=%s", response_id, exc)
        if ws_tts_is_active(connection_id, response_id, cancel_event):
            try:
                await _ws_send_json({"type": "ttsComplete", "response_id": response_id, "error": True})
            except Exception:
                pass
    finally:
        if local_tts_session is not None and not local_tts_session.closed:
            await local_tts_session.close()


async def tts_arabic_response(
    arabic_text: str,
    websocket: WebSocket,
    connection_id: str = "",
    *,
    perf_start: float = 0.0,
) -> tuple:
    """Send a full Arabic text string to XTTS and stream PCM audio over WebSocket.

    Returns (first_chunk_time, chunk_count, total_time_s) for latency tracking.
    Can be awaited directly to capture real TTS timings in the latency report.
    """
    if not arabic_text or not arabic_text.strip():
        return None, 0, 0.0
    if EFFECTIVE_DISABLE_TTS:
        return None, 0, 0.0

    # Split into ~200-char chunks to respect XTTS token limit
    import re as _re2
    MAX_CHUNK = 200
    # Split on sentence boundaries first, then hard-clip remaining pieces
    raw_sentences = _re2.split(r'(?<=[.؟!،])\s+', arabic_text.strip())
    tts_sentences = []
    for s in raw_sentences:
        while len(s) > MAX_CHUNK:
            tts_sentences.append(s[:MAX_CHUNK])
            s = s[MAX_CHUNK:]
        if s.strip():
            tts_sentences.append(s.strip())

    # Use the shared per-connection write lock so this background task never
    # sends bytes concurrently with call_llm_streaming (which causes WS errors).
    _lock = state.ws_write_locks.get(connection_id) or asyncio.Lock()

    async def _ws_send_json(payload):
        async with _lock:
            await websocket.send_json(payload)

    async def _ws_send_bytes(data):
        async with _lock:
            await websocket.send_bytes(data)

    first_chunk_time: Optional[float] = None
    chunk_count: int = 0
    total_time: float = 0.0

    try:
        _sess = state.tts_session
        if _sess is None or _sess.closed:
            return None, 0, 0.0  # TTS service not available

        for sentence in tts_sentences:
            clean = _re2.sub(r'[\U00010000-\U0010ffff]', '', sentence, flags=_re2.UNICODE).strip()
            if not clean:
                continue
            try:
                chunk_start = time.perf_counter()
                await _ws_send_json({"type": "ttsAudioStart", "sampleRate": 24000})
                resp = await _sess.post(
                    f"{XTTS_SERVICE_URL}/synthesize",
                    json={"text": clean, "speaker": XTTS_SPEAKER, "language": "ar"},
                )
                if resp.status == 200:
                    header_skipped = False
                    header_buf = b''
                    pcm_remainder = b''
                    async for chunk in resp.content.iter_chunked(4096):
                        if not header_skipped:
                            header_buf += chunk
                            if len(header_buf) >= 44:
                                data = header_buf[44:]
                                header_skipped = True
                                header_buf = b''
                                if not data:
                                    continue
                            else:
                                continue
                        else:
                            data = chunk
                        if pcm_remainder:
                            data = pcm_remainder + data
                            pcm_remainder = b''
                        if len(data) % 2 != 0:
                            pcm_remainder = data[-1:]
                            data = data[:-1]
                        if data:
                            await _ws_send_bytes(data)
                            if first_chunk_time is None:
                                first_chunk_time = time.perf_counter()
                                if perf_start:
                                    logger.info(
                                        f"LATENCY [First TTS Chunk (Arabic)]: "
                                        f"{(first_chunk_time - perf_start) * 1000:.0f}ms"
                                    )
                    resp.close()
                    chunk_elapsed = time.perf_counter() - chunk_start
                    chunk_count += 1
                    total_time += chunk_elapsed
                else:
                    resp.close()
                    await _ws_send_json({"type": "ttsFallback", "text": clean})
                await _ws_send_json({"type": "ttsAudioEnd"})
            except Exception as e:
                logger.warning(f"Arabic TTS chunk error: {e}")
    except Exception as e:
        logger.warning(f"Arabic TTS session error: {e}")

    try:
        async with _lock:
            await websocket.send_json({"type": "arabic_tts_complete"})
    except Exception:
        pass

    return first_chunk_time, chunk_count, total_time


async def tts_single_response(
    text: str,
    websocket: WebSocket,
    connection_id: str,
    language: str,
    t_meta: Optional[dict] = None,
) -> None:
    """Synthesize a single short response via XTTS and stream it over WebSocket."""
    if not text or not text.strip():
        return
    if EFFECTIVE_DISABLE_TTS:
        return

    if connection_id not in state.ws_write_locks:
        state.ws_write_locks[connection_id] = asyncio.Lock()
    _lock = state.ws_write_locks[connection_id]

    async def _ws_send_json(payload):
        async with _lock:
            await websocket.send_json(payload)

    async def _ws_send_bytes(data):
        async with _lock:
            await websocket.send_bytes(data)

    # Fast path: use prewarmed cached PCM for Arabic off-topic refusal.
    if language == "ar" and text.strip() == _arabic_off_topic_response() and state.arabic_offtopic_pcm:
        try:
            await _ws_send_json({"type": "ttsAudioStart", "sampleRate": 24000})
            if t_meta is not None:
                now = time.perf_counter()
                t_meta.setdefault("xtts_send", now)
                t_meta.setdefault("first_tts_chunk", now)
                t_meta["xtts_last_chunk"] = now
            await _ws_send_bytes(state.arabic_offtopic_pcm)
        finally:
            await _ws_send_json({"type": "ttsAudioEnd"})
        return

    clean = preprocess_for_tts(text.strip(), language=language)
    if not clean:
        return

    if t_meta is not None:
        t_meta.setdefault("tts_wait_ms", 0)
        t_meta.setdefault("tts_synthesis_ms", 0)
        t_meta.setdefault("audio_bytes", 0)

    cache_key = tts_cache_key(clean, language, XTTS_SPEAKER)
    cached_wav = await tts_cache_get(cache_key)
    cache_hit = cached_wav is not None
    logger.info(
        "[WS TTS CACHE] hit=%s language=%s key=%s text_len=%s",
        bool(cache_hit),
        language,
        cache_key,
        len(clean),
    )
    if t_meta is not None:
        t_meta["tts_cache_hit"] = bool(cache_hit)
    if language == "ar":
        logger.info("[AR PERF] cache_hit=%s stage=tts", bool(cache_hit))

    if cached_wav is not None:
        cached_start = time.perf_counter()
        try:
            await _ws_send_json({"type": "ttsAudioStart", "sampleRate": 24000})
            if t_meta is not None:
                t_meta.setdefault("xtts_send", cached_start)
            pcm_data = wav_bytes_to_pcm16(cached_wav)
            if pcm_data:
                if t_meta is not None and not t_meta.get("first_tts_chunk"):
                    t_meta["first_tts_chunk"] = time.perf_counter()
                await _ws_send_bytes(pcm_data)
                if t_meta is not None:
                    t_meta["xtts_last_chunk"] = time.perf_counter()
                    t_meta["audio_bytes"] = len(pcm_data)
                    t_meta["audio_wav_bytes"] = len(cached_wav)
            else:
                await _ws_send_json({"type": "ttsFallback", "text": clean})
        finally:
            await _ws_send_json({"type": "ttsAudioEnd"})
        cached_ms = int(round((time.perf_counter() - cached_start) * 1000))
        if t_meta is not None:
            t_meta["tts_ms"] = cached_ms
            t_meta["tts_wait_ms"] = 0
            t_meta["tts_synthesis_ms"] = 0
        if language == "ar":
            logger.info(
                "[AR PERF] tts_ms=%s tts_wait_ms=0 tts_synthesis_ms=0 audio_bytes=%s cache_hit=True",
                cached_ms,
                int(t_meta.get("audio_bytes") or 0) if t_meta is not None else 0,
            )
        return

    _local_tts_session = None
    _tts_sess = state.tts_session
    if _tts_sess is None or _tts_sess.closed:
        _local_tts_session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=None, sock_connect=5, sock_read=None)
        )
        _tts_sess = _local_tts_session

    chunk_start = time.perf_counter()
    audio_bytes_sent = 0
    wav_bytes_accumulated = 0
    try:
        if t_meta is not None:
            t_meta.setdefault("xtts_send", chunk_start)
        await _ws_send_json({"type": "ttsAudioStart", "sampleRate": 24000})
        synthesis_start = time.perf_counter()
        resp = await _tts_sess.post(
            f"{XTTS_SERVICE_URL}/synthesize",
            json={"text": clean, "speaker": XTTS_SPEAKER, "language": language},
        )

        if resp.status == 200:
            header_skipped = False
            header_buf = b''
            pcm_remainder = b''
            emitted_audio = False
            wav_accum = bytearray()

            async for chunk in resp.content.iter_chunked(4096):
                if chunk:
                    wav_accum.extend(chunk)
                if not header_skipped:
                    header_buf += chunk
                    if len(header_buf) >= 44:
                        data = header_buf[44:]
                        header_skipped = True
                        header_buf = b''
                        if not data:
                            continue
                    else:
                        continue
                else:
                    data = chunk

                if pcm_remainder:
                    data = pcm_remainder + data
                    pcm_remainder = b''
                if len(data) % 2 != 0:
                    pcm_remainder = data[-1:]
                    data = data[:-1]

                if data:
                    if t_meta is not None and not t_meta.get("first_tts_chunk"):
                        t_meta["first_tts_chunk"] = time.perf_counter()
                    await _ws_send_bytes(data)
                    audio_bytes_sent += len(data)
                    emitted_audio = True
            resp.close()
            if t_meta is not None and emitted_audio:
                t_meta["xtts_last_chunk"] = time.perf_counter()
                t_meta["tts_synthesis_ms"] = int(round((t_meta["xtts_last_chunk"] - synthesis_start) * 1000))
                t_meta["audio_bytes"] = audio_bytes_sent
            if emitted_audio and wav_accum:
                wav_bytes_accumulated = len(wav_accum)
                await tts_cache_put(cache_key, bytes(wav_accum))
                logger.info(
                    "[WS TTS CACHE] stored=True language=%s key=%s bytes=%s text_len=%s",
                    language,
                    cache_key,
                    len(wav_accum),
                    len(clean),
                )

            # XTTS can occasionally return a valid WAV header but no PCM payload.
            # In that case, force browser speech fallback so user still hears audio.
            if not emitted_audio:
                logger.warning("Strict-guard XTTS returned no audio bytes; using browser fallback")
                await _ws_send_json({"type": "ttsFallback", "text": clean})
        else:
            detail = await resp.text()
            resp.close()
            logger.warning(f"Strict-guard XTTS returned {resp.status}: {detail[:100]}")
            await _ws_send_json({"type": "ttsFallback", "text": clean})
    except Exception as e:
        logger.warning(f"Strict-guard XTTS error: {e}")
        try:
            await _ws_send_json({"type": "ttsFallback", "text": clean})
        except Exception:
            pass
    finally:
        try:
            await _ws_send_json({"type": "ttsAudioEnd"})
        except Exception:
            pass
        try:
            tts_ms = int(round((time.perf_counter() - chunk_start) * 1000))
            if t_meta is not None:
                t_meta["tts_ms"] = tts_ms
                t_meta["tts_wait_ms"] = int(t_meta.get("tts_wait_ms") or 0)
                t_meta.setdefault("tts_synthesis_ms", tts_ms)
                t_meta.setdefault("audio_bytes", audio_bytes_sent)
                if wav_bytes_accumulated:
                    t_meta["audio_wav_bytes"] = wav_bytes_accumulated
            if language == "ar":
                logger.info(
                    "[AR PERF] tts_ms=%s tts_wait_ms=%s tts_synthesis_ms=%s audio_bytes=%s cache_hit=False",
                    tts_ms,
                    int(t_meta.get("tts_wait_ms") or 0) if t_meta is not None else 0,
                    int(t_meta.get("tts_synthesis_ms") or tts_ms) if t_meta is not None else tts_ms,
                    int(t_meta.get("audio_bytes") or audio_bytes_sent) if t_meta is not None else audio_bytes_sent,
                )
        except Exception:
            pass
        if _local_tts_session is not None and not _local_tts_session.closed:
            await _local_tts_session.close()


def client_tts_allowed(client_tts_enabled: bool) -> bool:
    """Honor client voice-mode flag only when server TTS is globally enabled."""
    return bool(not EFFECTIVE_DISABLE_TTS and client_tts_enabled)
