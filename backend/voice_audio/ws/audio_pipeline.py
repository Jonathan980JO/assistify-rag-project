"""Voice STT orchestration after PCM capture."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Awaitable, Callable, Optional

import torch
from fastapi import WebSocket

from backend.voice_audio import memory_guard, state
from backend.voice_audio.config import XTTS_LANGUAGE
from backend.voice_audio.stt.transcribe import (
    _arabic_stt_unclear,
    _english_stt_unclear,
    _looks_like_english_stt_garbage_for_arabic,
    run_transcription,
)
from backend.voice_audio.concurrency import voice_inference_slot
from backend.voice_audio.tts.streaming import cancel_active_ws_tts

logger = logging.getLogger("voice_audio.ws.audio_pipeline")


async def send_stt_failed(
    ws: WebSocket,
    conn_id: str,
    reason: str,
    message: str,
) -> None:
    """Notify client that STT did not produce usable text (recoverable)."""
    try:
        await ws.send_json({
            "type": "stt_failed",
            "reason": reason,
            "message": message,
            "voice_recoverable": True,
        })
    except Exception as exc:
        logger.warning("%s stt_failed send failed (%s): %s", conn_id, reason, exc)


async def run_auto_transcribe(
    data_bytes: bytes,
    ws: WebSocket,
    conn_id: str,
    *,
    process_voice_transcript: Callable,
    send_final_response: Callable,
    t_meta: Optional[dict] = None,
    lang: str = "en",
    get_memory_snapshot: Optional[Callable[[], dict]] = None,
    get_stable_memory_snapshot: Optional[Callable[[], Awaitable[dict]]] = None,
) -> None:
    """STT + delegate post-transcript routing to the RAG server callback."""
    import time as _time

    _mem = get_memory_snapshot or (lambda: {"cpu_rss_mb": 0, "gpu_reserved_mb": 0, "gpu_allocated_mb": 0})

    async def _default_stable() -> dict:
        return _mem()

    _stable = get_stable_memory_snapshot or _default_stable

    if memory_guard.sessions_blocked:
        current_mem = _mem()
        if (
            current_mem["cpu_rss_mb"] <= memory_guard.SAFE_UNBLOCK_CPU_MB
            and (
                not torch.cuda.is_available()
                or current_mem["gpu_reserved_mb"] <= memory_guard.SAFE_UNBLOCK_GPU_MB
            )
        ):
            memory_guard.sessions_blocked = False
            memory_guard.sessions_blocked_since = 0.0
            memory_guard.consecutive_gpu_growth = 0
            memory_guard.consecutive_cpu_growth = 0
            logger.warning(
                "MEMORY GUARD AUTO-RECOVERED — re-enabling voice sessions [%s]",
                conn_id,
            )

    if memory_guard.sessions_blocked:
        logger.error("MEMORY LEAK SUSPECTED — refusing new voice session [%s]", conn_id)
        try:
            await send_final_response(
                conn_id,
                "System is stabilizing memory. Please try again in a few seconds.",
                XTTS_LANGUAGE,
                False,
                websocket=ws,
                sources=0,
                arabic_mode=False,
                t_meta={"request_start": time.perf_counter()},
                branch="voice_memory_guard",
                extra_payload={"error": True},
            )
        except Exception:
            pass
        return

    session_start = _time.perf_counter()
    mem_before = _mem()
    client_notified = False

    try:
        cancel_active_ws_tts(conn_id, "new_voice_query")

        current_task = asyncio.current_task()
        if (
            memory_guard.active_voice_task
            and not memory_guard.active_voice_task.done()
            and memory_guard.active_voice_task is not current_task
        ):
            memory_guard.active_voice_task.cancel()
            try:
                await memory_guard.active_voice_task
            except (asyncio.CancelledError, Exception):
                pass
        memory_guard.active_voice_conn_id = conn_id

        logger.info("===== VOICE SESSION START  [%s] =====", conn_id)
        logger.info(
            "  GPU before: reserved=%.0fMB  alloc=%.0fMB  |  CPU RSS=%.0fMB",
            mem_before["gpu_reserved_mb"],
            mem_before.get("gpu_allocated_mb", 0),
            mem_before["cpu_rss_mb"],
        )

        async with voice_inference_slot(ws, conn_id):
            requested_voice_lang = str(lang or "en").strip().lower()
            if requested_voice_lang not in {"en", "ar"}:
                requested_voice_lang = "en"
            arabic_voice_mode = requested_voice_lang == "ar"

            if len(data_bytes) < 8000:
                await send_stt_failed(
                    ws,
                    conn_id,
                    "audio_too_short",
                    "Didn't catch enough audio. Please try again.",
                )
                client_notified = True
                return

            try:
                result = await run_transcription(data_bytes, requested_voice_lang)
            except asyncio.TimeoutError:
                logger.error("%s STT TIMEOUT", conn_id)
                await send_stt_failed(
                    ws,
                    conn_id,
                    "timeout",
                    "Speech recognition timed out. Please try again.",
                )
                client_notified = True
                return
            except Exception as exc:
                logger.error("%s STT Error: %s", conn_id, exc)
                client_notified = True
                try:
                    await send_final_response(
                        conn_id,
                        "Speech to text is currently disabled.",
                        XTTS_LANGUAGE,
                        False,
                        websocket=ws,
                        sources=0,
                        arabic_mode=False,
                        t_meta={"request_start": time.perf_counter()},
                        branch="stt_error",
                        extra_payload={"error": True},
                    )
                except Exception:
                    pass
                return

            full_text = result.text
            if arabic_voice_mode and _looks_like_english_stt_garbage_for_arabic(full_text, result.segments):
                try:
                    await ws.send_json({
                        "type": "error",
                        "message": "Arabic speech was not transcribed confidently. Please try again.",
                        "arabic_mode": True,
                    })
                    client_notified = True
                except Exception:
                    pass
                return

            if arabic_voice_mode and _arabic_stt_unclear(full_text, result.segments):
                try:
                    await send_final_response(
                        conn_id,
                        "لم أفهم السؤال بشكل واضح، هل يمكنك إعادة المحاولة؟",
                        "ar",
                        True,
                        websocket=ws,
                        sources=0,
                        arabic_mode=True,
                        t_meta={"request_start": time.perf_counter()},
                        branch="stt_unclear_arabic",
                    )
                    client_notified = True
                except Exception:
                    pass
                return

            if not full_text or len(full_text) <= 2:
                await send_stt_failed(
                    ws,
                    conn_id,
                    "empty_transcript",
                    "Couldn't understand that. Please speak again.",
                )
                client_notified = True
                return

            if not arabic_voice_mode and _english_stt_unclear(full_text, result.segments):
                await send_stt_failed(
                    ws,
                    conn_id,
                    "unclear_speech",
                    "Couldn't understand that clearly. Please try again.",
                )
                client_notified = True
                return

            t_meta = dict(t_meta or {})
            t_meta.update({
                "stt_requested_language": requested_voice_lang,
                "stt_transcribe_language": result.transcribe_lang,
                "stt_model": result.model_label,
                "stt_retry_count": result.retry_count,
            })

            await ws.send_json({
                "type": "transcript",
                "text": full_text,
                "final": True,
                "timing": t_meta,
            })
            client_notified = True

            await process_voice_transcript(
                ws=ws,
                conn_id=conn_id,
                full_text=full_text,
                lang=requested_voice_lang,
                t_meta=t_meta,
                segments_list=result.segments,
            )
    except asyncio.CancelledError:
        logger.warning("%s Voice pipeline cancelled (superseded)", conn_id)
    except Exception as exc:
        logger.exception("Auto-transcription error: %s", exc)
        if not client_notified:
            await send_stt_failed(
                ws,
                conn_id,
                "pipeline_error",
                "Voice processing failed. Please try again.",
            )
    finally:
        mem_after_raw = _mem()
        mem_after = await _stable()
        duration = (_time.perf_counter() - session_start) * 1000
        memory_guard.pipeline_run_count += 1
        logger.info("===== VOICE SESSION END    [%s] =====", conn_id)
        logger.info("  SESSION DURATION: %.0fms", duration)
        logger.info(
            "  GPU after : reserved=%.0fMB  alloc=%.0fMB  |  CPU RSS=%.0fMB",
            mem_after["gpu_reserved_mb"],
            mem_after.get("gpu_allocated_mb", 0),
            mem_after["cpu_rss_mb"],
        )
        delta_gpu = mem_after["gpu_reserved_mb"] - mem_before["gpu_reserved_mb"]
        delta_cpu = mem_after["cpu_rss_mb"] - mem_before["cpu_rss_mb"]

        gpu_growth_suspected = (
            delta_gpu > memory_guard.GPU_GROWTH_DELTA_MB
            and mem_after["gpu_reserved_mb"] > memory_guard.GPU_HIGH_WATER_MB
        )
        if gpu_growth_suspected:
            memory_guard.consecutive_gpu_growth += 1
            logger.warning(
                "  GPU memory grew by %.0fMB (consecutive: %d/%d)",
                delta_gpu,
                memory_guard.consecutive_gpu_growth,
                memory_guard.MEMORY_GROWTH_LIMIT,
            )
        else:
            memory_guard.consecutive_gpu_growth = 0

        cpu_growth_suspected = (
            delta_cpu > memory_guard.CPU_GROWTH_DELTA_MB
            and mem_after["cpu_rss_mb"] > memory_guard.CPU_HIGH_WATER_MB
        )
        if cpu_growth_suspected:
            memory_guard.consecutive_cpu_growth += 1
            logger.warning(
                "  CPU RSS grew by %.0fMB (consecutive: %d/%d)",
                delta_cpu,
                memory_guard.consecutive_cpu_growth,
                memory_guard.MEMORY_GROWTH_LIMIT,
            )
        else:
            memory_guard.consecutive_cpu_growth = 0

        if (
            memory_guard.pipeline_run_count > 1
            and mem_after["gpu_reserved_mb"] > memory_guard.last_gpu_reserved_mb + 100
        ):
            logger.warning(
                "  CONTINUOUS GPU GROWTH across runs (prev=%.0f now=%.0f)",
                memory_guard.last_gpu_reserved_mb,
                mem_after["gpu_reserved_mb"],
            )
        memory_guard.last_gpu_reserved_mb = mem_after["gpu_reserved_mb"]

        if (
            memory_guard.consecutive_gpu_growth >= memory_guard.MEMORY_GROWTH_LIMIT
            or memory_guard.consecutive_cpu_growth >= memory_guard.MEMORY_GROWTH_LIMIT
        ):
            memory_guard.sessions_blocked = True
            memory_guard.sessions_blocked_since = _time.time()
            logger.critical("  MEMORY LEAK SUSPECTED — blocking all new voice sessions")

        memory_guard.active_voice_task = None
        memory_guard.active_voice_conn_id = None
