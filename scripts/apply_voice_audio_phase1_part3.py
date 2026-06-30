#!/usr/bin/env python3
"""Phase 1 part 3: WS handler, lifecycle, STT routes, patch main server."""
from __future__ import annotations

import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "backend" / "assistify_rag_server.py"
VOICE = ROOT / "backend" / "voice_audio"


def read_lines() -> list[str]:
    return SRC.read_text(encoding="utf-8").splitlines(keepends=True)


def delete_ranges(lines: list[str], ranges: list[tuple[int, int]]) -> list[str]:
    drop = set()
    for start, end in ranges:
        for i in range(start, end + 1):
            drop.add(i)
    return [ln for i, ln in enumerate(lines, start=1) if i not in drop]


def main() -> None:
    lines = read_lines()

    # Save callbacks extracted from WS before deletion
    voice_transcript = "".join(lines[43730:43841])  # post-STT body inside auto_transcribe
    text_message = "".join(lines[44086:44436])  # elif "text" in payload branch

    (VOICE / "ws" / "audio_pipeline.py").write_text(
        textwrap.dedent(
            '''\
            """Voice STT orchestration after PCM capture."""
            from __future__ import annotations

            import asyncio
            import logging
            import time
            from typing import Any, Callable, Optional

            import numpy as np
            import torch
            from fastapi import WebSocket

            from backend.voice_audio import config, memory_guard, state
            from backend.voice_audio.config import SAMPLE_RATE, XTTS_LANGUAGE
            from backend.voice_audio.stt.transcribe import (
                TranscriptionResult,
                _arabic_stt_unclear,
                _looks_like_english_stt_garbage_for_arabic,
                run_transcription,
            )
            from backend.voice_audio.tts.streaming import cancel_active_ws_tts

            logger = logging.getLogger("voice_audio.ws.audio_pipeline")


            async def run_auto_transcribe(
                data_bytes: bytes,
                ws: WebSocket,
                conn_id: str,
                *,
                process_voice_transcript: Callable,
                send_final_response: Callable,
                t_meta: Optional[dict] = None,
                lang: str = "en",
            ) -> None:
                """STT + delegate post-transcript routing to the RAG server callback."""
                import time as _time

                get_mem = process_voice_transcript.__self__ if False else None  # noqa: unused

                if memory_guard.sessions_blocked:
                    current_mem = {"cpu_rss_mb": 0, "gpu_reserved_mb": 0}
                    try:
                        from backend.assistify_rag_server import _get_memory_snapshot
                        current_mem = _get_memory_snapshot()
                    except Exception:
                        pass
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

                if memory_guard.sessions_blocked:
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

                try:
                    async with state.voice_semaphore:
                        requested_voice_lang = str(lang or "en").strip().lower()
                        if requested_voice_lang not in {"en", "ar"}:
                            requested_voice_lang = "en"
                        arabic_voice_mode = requested_voice_lang == "ar"

                        if len(data_bytes) < 8000:
                            return

                        try:
                            result = await run_transcription(data_bytes, requested_voice_lang)
                        except asyncio.TimeoutError:
                            logger.error("%s STT TIMEOUT", conn_id)
                            return
                        except Exception as exc:
                            logger.error("%s STT Error: %s", conn_id, exc)
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
                            except Exception:
                                pass
                            return

                        if not full_text or len(full_text) <= 2:
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

                        await process_voice_transcript(
                            ws=ws,
                            conn_id=conn_id,
                            full_text=full_text,
                            lang=requested_voice_lang,
                            t_meta=t_meta,
                            segments_list=result.segments,
                        )
                except asyncio.CancelledError:
                    logger.warning("%s Voice pipeline cancelled", conn_id)
                except Exception as exc:
                    logger.exception("Auto-transcription error: %s", exc)
                finally:
                    memory_guard.active_voice_task = None
                    memory_guard.active_voice_conn_id = None
            '''
        ),
        encoding="utf-8",
    )
    print("wrote ws/audio_pipeline.py")

    # Fix transcribe exports for arabic helpers
    stt_init = VOICE / "stt" / "__init__.py"
    stt_init.write_text(
        "from backend.voice_audio.stt.transcribe import (\n"
        "    TranscriptionResult,\n"
        "    run_transcription,\n"
        "    _arabic_stt_unclear,\n"
        "    _looks_like_english_stt_garbage_for_arabic,\n"
        ")\n"
        "from backend.voice_audio.stt.loader import (\n"
        "    load_multilingual_whisper_model_if_available,\n"
        "    resolve_multilingual_model_path,\n"
        "    arabic_multilingual_model_ready,\n"
        "    MULTILINGUAL_MODEL_PATH,\n"
        ")\n",
        encoding="utf-8",
    )

    # lifecycle.py - simplified
    (VOICE / "lifecycle.py").write_text(
        textwrap.dedent(
            '''\
            """Startup/shutdown for voice STT/TTS subsystems."""
            from __future__ import annotations

            import asyncio
            import logging
            from typing import Any, Optional

            import aiohttp
            import torch
            from fastapi import FastAPI
            from faster_whisper import WhisperModel

            from backend.voice_audio import config, state
            from backend.voice_audio.stt.loader import (
                MULTILINGUAL_MODEL_PATH,
                load_multilingual_whisper_model_if_available,
                resolve_multilingual_model_path,
            )
            from backend.voice_audio.tts.client import xtts_synth_sem

            logger = logging.getLogger("voice_audio.lifecycle")

            try:
                from config import WHISPER_MODEL_PATH, WHISPER_MODEL_SIZE, WHISPER_DEVICE, WHISPER_COMPUTE_TYPE, WHISPER_BEAM_SIZE, WHISPER_VAD_FILTER
            except Exception:
                from pathlib import Path
                WHISPER_MODEL_PATH = Path(__file__).resolve().parent.parent / "Models" / "faster-whisper-tiny.en"
                WHISPER_MODEL_SIZE = "tiny.en"
                WHISPER_DEVICE = "cpu"
                WHISPER_COMPUTE_TYPE = "int8"
                WHISPER_BEAM_SIZE = 1
                WHISPER_VAD_FILTER = True


            async def init_voice_audio(app: FastAPI, *, safe_mode: bool = False, disable_warmup: bool = False) -> None:
                """Load Whisper, create TTS session, probe Piper."""
                if safe_mode:
                    logger.warning("Safe mode: skipping voice audio initialization")
                    return

                if not state.WHISPER_AVAILABLE:
                    raise ImportError("CRITICAL: faster-whisper not installed")

                whisper_device = WHISPER_DEVICE
                whisper_compute = WHISPER_COMPUTE_TYPE
                if not torch.cuda.is_available() and whisper_device == "cuda":
                    whisper_device = "cpu"
                    whisper_compute = "int8"

                logger.info("Loading faster-whisper '%s' on %s...", WHISPER_MODEL_SIZE, whisper_device)
                if WHISPER_MODEL_PATH.exists():
                    state.whisper_model = WhisperModel(
                        str(WHISPER_MODEL_PATH),
                        device=whisper_device,
                        compute_type=whisper_compute,
                        download_root=None,
                    )
                else:
                    WHISPER_MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
                    state.whisper_model = WhisperModel(
                        WHISPER_MODEL_SIZE,
                        device=whisper_device,
                        compute_type=whisper_compute,
                        download_root=str(WHISPER_MODEL_PATH.parent),
                    )
                logger.info("faster-whisper loaded")

                tts_connector = aiohttp.TCPConnector(limit=4, limit_per_host=2, force_close=False, enable_cleanup_closed=True)
                state.tts_session = aiohttp.ClientSession(
                    connector=tts_connector,
                    timeout=aiohttp.ClientTimeout(total=None, sock_connect=5, sock_read=None),
                    headers={"Connection": "keep-alive"},
                )

                if config.ASSISTIFY_DISABLE_TTS:
                    state.xtts_model = None
                    config.EFFECTIVE_DISABLE_TTS = True
                else:
                    import json
                    import urllib.request as _urllib_req
                    try:
                        req = _urllib_req.urlopen(f"{config.XTTS_SERVICE_URL}/health", timeout=5)
                        health = json.loads(req.read().decode())
                        if health.get("status") == "ok" and health.get("engine") == "piper" and health.get("ready"):
                            state.xtts_model = True
                            config.EFFECTIVE_DISABLE_TTS = False
                        else:
                            state.xtts_model = None
                            config.EFFECTIVE_DISABLE_TTS = True
                    except Exception as exc:
                        logger.warning("Piper not reachable: %s", exc)
                        state.xtts_model = None
                        config.EFFECTIVE_DISABLE_TTS = True

                ml = resolve_multilingual_model_path()
                if ml:
                    load_multilingual_whisper_model_if_available()
                else:
                    logger.info("Multilingual Whisper not found at %s", MULTILINGUAL_MODEL_PATH)

                if not disable_warmup and not config.EFFECTIVE_DISABLE_WARMUP:
                    asyncio.create_task(_warmup_tts())


            async def _warmup_tts() -> None:
                await asyncio.sleep(10)
                if config.EFFECTIVE_DISABLE_TTS:
                    return
                try:
                    async with xtts_synth_sem:
                        if state.tts_session and not state.tts_session.closed:
                            async with state.tts_session.post(
                                f"{config.XTTS_SERVICE_URL}/synthesize",
                                json={"text": "warmup", "speaker": config.XTTS_SPEAKER, "language": config.XTTS_LANGUAGE},
                                timeout=aiohttp.ClientTimeout(total=30),
                            ) as resp:
                                if resp.status == 200:
                                    await resp.read()
                except Exception as exc:
                    logger.warning("TTS warmup failed: %s", exc)


            async def shutdown_voice_audio() -> None:
                if state.tts_session and not state.tts_session.closed:
                    await state.tts_session.close()
            '''
        ),
        encoding="utf-8",
    )
    print("wrote lifecycle.py")

    # stt routes
    (VOICE / "stt" / "routes.py").write_text(
        textwrap.dedent(
            '''\
            """STT-related HTTP routes."""
            from __future__ import annotations

            import asyncio
            import logging
            from typing import Callable

            import torch
            from fastapi import APIRouter, Depends

            from backend.voice_audio import config, state
            from backend.voice_audio.stt.loader import (
                MULTILINGUAL_MODEL_PATH,
                arabic_multilingual_model_ready,
                load_multilingual_whisper_model_if_available,
            )

            logger = logging.getLogger("voice_audio.stt.routes")
            router = APIRouter(tags=["voice-stt"])


            def register_stt_routes(app_router: APIRouter, require_login: Callable) -> None:
                @app_router.get("/arabic/status")
                async def arabic_status(user=Depends(require_login())):
                    model_on_disk = MULTILINGUAL_MODEL_PATH.exists() or arabic_multilingual_model_ready()
                    model_loaded = state.whisper_model_multilingual is not None
                    return {
                        "multilingual_model_ready": model_on_disk or model_loaded,
                        "multilingual_model_loaded": model_loaded,
                        "multilingual_model_on_disk": model_on_disk,
                        "xtts_arabic_ready": state.xtts_model is not None,
                        "download_state": state.arabic_download_status.get("state", "idle"),
                        "download_message": state.arabic_download_status.get("message", ""),
                        "model_path": str(MULTILINGUAL_MODEL_PATH),
                    }

                @app_router.post("/arabic/download")
                async def arabic_download_models(user=Depends(require_login())):
                    if arabic_multilingual_model_ready():
                        return {"status": "already_ready", "message": "Multilingual model already present."}
                    if state.arabic_download_task and not state.arabic_download_task.done():
                        return {"status": "downloading", "message": "Download already in progress."}

                    async def _do_download():
                        state.arabic_download_status = {"state": "downloading", "message": "Downloading..."}
                        dest = MULTILINGUAL_MODEL_PATH
                        dest.mkdir(parents=True, exist_ok=True)
                        try:
                            from faster_whisper import WhisperModel
                            from config import WHISPER_DEVICE, WHISPER_COMPUTE_TYPE
                            import os
                            dl_kwargs = {"device": WHISPER_DEVICE, "compute_type": WHISPER_COMPUTE_TYPE, "download_root": str(dest.parent)}
                            if WHISPER_DEVICE == "cpu":
                                dl_kwargs.update({"cpu_threads": int(os.getenv("WHISPER_CPU_THREADS", "4")), "num_workers": 1})
                            state.whisper_model_multilingual = WhisperModel("small", **dl_kwargs)
                            state.arabic_download_status = {"state": "ready", "message": "Multilingual model ready."}
                        except Exception as exc:
                            state.arabic_download_status = {"state": "error", "message": str(exc)}

                    state.arabic_download_task = asyncio.create_task(_do_download())
                    return {"status": "downloading", "message": "Download started in background."}

                @app_router.get("/internal/asr-status")
                def asr_status():
                    try:
                        from config import WHISPER_MODEL_SIZE, WHISPER_DEVICE, WHISPER_COMPUTE_TYPE, WHISPER_BEAM_SIZE, WHISPER_VAD_FILTER
                    except Exception:
                        WHISPER_MODEL_SIZE = "tiny.en"
                        WHISPER_DEVICE = "cpu"
                        WHISPER_COMPUTE_TYPE = "int8"
                        WHISPER_BEAM_SIZE = 1
                        WHISPER_VAD_FILTER = True
                    return {
                        "engine": "faster-whisper",
                        "model_size": WHISPER_MODEL_SIZE,
                        "device": WHISPER_DEVICE,
                        "compute_type": WHISPER_COMPUTE_TYPE,
                        "beam_size": WHISPER_BEAM_SIZE,
                        "vad_enabled": WHISPER_VAD_FILTER,
                        "sample_rate": config.SAMPLE_RATE,
                        "model_loaded": state.whisper_model is not None,
                        "gpu_available": torch.cuda.is_available() if state.WHISPER_AVAILABLE else False,
                    }
            '''
        ),
        encoding="utf-8",
    )
    print("wrote stt/routes.py")

    # Write handler - simplified version calling audio_pipeline
    (VOICE / "ws" / "handler.py").write_text(
        textwrap.dedent(
            '''\
            """WebSocket /ws handler for voice audio and control messages."""
            from __future__ import annotations

            import asyncio
            import json
            import logging
            import uuid
            from typing import Callable, Optional

            import numpy as np
            from fastapi import WebSocket, WebSocketDisconnect

            from backend.voice_audio import config, memory_guard, state
            from backend.voice_audio.deps import VoiceWebSocketDeps
            from backend.voice_audio.ws.audio_pipeline import run_auto_transcribe
            from backend.voice_audio.ws.capture import ConversationCaptureWebSocket
            from backend.voice_audio.tts.streaming import cancel_active_ws_tts

            logger = logging.getLogger("voice_audio.ws.handler")


            def create_rag_ws_handler(deps: VoiceWebSocketDeps) -> Callable:
                async def rag_ws_handler(websocket: WebSocket) -> None:
                    await websocket.accept()
                    connection_id = f"conn_{uuid.uuid4().hex[:8]}"
                    logger.info("New websocket connection %s", connection_id)
                    if deps.active_ws_connections is not None:
                        deps.active_ws_connections[connection_id] = websocket

                    cancel_event = asyncio.Event()
                    state.interrupt_events[connection_id] = cancel_event
                    state.ws_write_locks[connection_id] = asyncio.Lock()

                    user = None
                    try:
                        token = websocket.cookies.get(deps.session_cookie)
                        if token and deps.serializer:
                            user = deps.serializer.loads(token)
                    except Exception:
                        user = None

                    ws_tenant_id = deps.resolve_request_tenant(user)
                    ws_owner = deps.coerce_owner(user)
                    if deps.set_request_tenant_id:
                        deps.set_request_tenant_id(ws_tenant_id)

                    audio_buffer = bytearray()
                    speech_start_time = None
                    silence_counter = 0
                    silence_chunks_needed = 14
                    silence_threshold_energy = 0.008
                    session_language = "en"
                    active_conversation_id: Optional[str] = None
                    current_ws_conversation_id: Optional[str] = None
                    stt_disabled_notified = False

                    def _activate_conversation(requested_id: Optional[str] = None) -> str:
                        nonlocal active_conversation_id
                        clean_requested = str(requested_id or "").strip() or active_conversation_id
                        conversation = deps.get_or_create_conversation(
                            clean_requested, tenant_id=ws_tenant_id, owner=ws_owner
                        )
                        conversation_id = str(conversation["id"])
                        active_conversation_id = conversation_id
                        deps.bind_conversation_memory(connection_id, conversation_id)
                        return conversation_id

                    def _conversation_ws(conversation_id: str) -> WebSocket:
                        return ConversationCaptureWebSocket(
                            websocket,
                            conversation_id,
                            connection_id,
                            deps.append_conversation_message,
                            deps.persist_runtime_memory,
                        )

                    try:
                        while True:
                            msg = await websocket.receive()
                            if msg["type"] != "websocket.receive":
                                continue
                            if msg.get("bytes") is not None:
                                audio = msg["bytes"]
                                if config.EFFECTIVE_DISABLE_WHISPER or not state.WHISPER_AVAILABLE:
                                    if not stt_disabled_notified:
                                        stt_disabled_notified = True
                                        try:
                                            await deps.send_final_response(
                                                connection_id,
                                                "Speech to text is currently disabled.",
                                                config.XTTS_LANGUAGE,
                                                False,
                                                websocket=websocket,
                                                sources=0,
                                                arabic_mode=False,
                                                t_meta={"request_start": __import__("time").perf_counter()},
                                                branch="stt_disabled",
                                                extra_payload={"error": True},
                                            )
                                        except Exception:
                                            pass
                                    continue

                                pcm_samples = np.frombuffer(audio, dtype=np.int16).astype(np.float32) / 32768.0
                                energy = float(np.sqrt(np.mean(pcm_samples ** 2)))
                                if energy < silence_threshold_energy:
                                    silence_counter += 1
                                else:
                                    if not speech_start_time and len(audio_buffer) > 0:
                                        speech_start_time = __import__("time").perf_counter()
                                    silence_counter = 0
                                audio_buffer.extend(audio)

                                if (
                                    silence_counter >= silence_chunks_needed
                                    and len(audio_buffer) > config.VOICE_MIN_TRANSCRIBE_BYTES
                                    and speech_start_time is not None
                                ):
                                    chunk = bytes(audio_buffer)
                                    audio_buffer.clear()
                                    silence_counter = 0
                                    speech_start_time = None
                                    if not memory_guard.voice_transcribe_in_flight(connection_id):
                                        task = asyncio.create_task(
                                            run_auto_transcribe(
                                                chunk,
                                                websocket,
                                                connection_id,
                                                process_voice_transcript=lambda **kw: deps.process_voice_transcript(
                                                    user=user,
                                                    active_conversation_id=active_conversation_id,
                                                    _activate_conversation=_activate_conversation,
                                                    _conversation_ws=_conversation_ws,
                                                    **kw,
                                                ),
                                                send_final_response=deps.send_final_response,
                                                lang=session_language,
                                            )
                                        )
                                        memory_guard.assign_voice_transcribe_task(task, connection_id)
                            elif msg.get("text") is not None:
                                try:
                                    payload = json.loads(msg["text"])
                                except Exception:
                                    payload = {"text": msg["text"]}
                                if not isinstance(payload, dict):
                                    continue
                                if payload.get("type") == "ping":
                                    await websocket.send_json({"type": "pong"})
                                    continue
                                if payload.get("type") == "control":
                                    action = payload.get("action")
                                    if action == "stop_recording" and len(audio_buffer) >= 16000:
                                        if not memory_guard.voice_transcribe_in_flight(connection_id):
                                            chunk = bytes(audio_buffer)
                                            audio_buffer.clear()
                                            task = asyncio.create_task(
                                                run_auto_transcribe(
                                                    chunk,
                                                    websocket,
                                                    connection_id,
                                                    process_voice_transcript=lambda **kw: deps.process_voice_transcript(
                                                        user=user,
                                                        active_conversation_id=active_conversation_id,
                                                        _activate_conversation=_activate_conversation,
                                                        _conversation_ws=_conversation_ws,
                                                        **kw,
                                                    ),
                                                    send_final_response=deps.send_final_response,
                                                    lang=session_language,
                                                )
                                            )
                                            memory_guard.assign_voice_transcribe_task(task, connection_id)
                                    elif action == "clear_audio_buffer":
                                        audio_buffer.clear()
                                        silence_counter = 0
                                    elif action == "interrupt":
                                        cancel_event = state.interrupt_events.get(connection_id)
                                        if cancel_event:
                                            cancel_event.set()
                                        cancel_active_ws_tts(connection_id, "user_barge_in")
                                        audio_buffer.clear()
                                        silence_counter = 0
                                    elif action == "set_language":
                                        new_lang = str(payload.get("language", "en") or "en").strip().lower()
                                        session_language = new_lang if new_lang in ("en", "ar") else "en"
                                    elif action == "set_conversation_id":
                                        cid = _activate_conversation(str(payload.get("conversation_id") or ""))
                                        current_ws_conversation_id = cid
                                        await websocket.send_json({"type": "conversation", "conversation_id": cid})
                                    continue
                                if "text" in payload:
                                    await deps.process_text_message(
                                        websocket=websocket,
                                        connection_id=connection_id,
                                        payload=payload,
                                        user=user,
                                        session_language=session_language,
                                        ws_tenant_id=ws_tenant_id,
                                        ws_owner=ws_owner,
                                        activate_conversation=_activate_conversation,
                                        conversation_ws_factory=_conversation_ws,
                                        set_session_language=lambda lang: nonlocal_set(session_language, lang),
                                    )
                    except WebSocketDisconnect:
                        logger.info("Websocket %s closed by client", connection_id)
                    except Exception as exc:
                        logger.exception("Websocket %s error: %s", connection_id, exc)
                        try:
                            await websocket.close()
                        except Exception:
                            pass
                    finally:
                        state.interrupt_events.pop(connection_id, None)
                        state.ws_write_locks.pop(connection_id, None)
                        if deps.active_ws_connections is not None:
                            deps.active_ws_connections.pop(connection_id, None)
                        if deps.conversation_history is not None:
                            deps.conversation_history.pop(connection_id, None)
                        if deps.conversation_timestamps is not None:
                            deps.conversation_timestamps.pop(connection_id, None)
                        if (
                            memory_guard.active_voice_task
                            and not memory_guard.active_voice_task.done()
                            and memory_guard.active_voice_conn_id == connection_id
                        ):
                            memory_guard.active_voice_task.cancel()
                        logger.info("Websocket %s fully cleaned up", connection_id)

                return rag_ws_handler


            def nonlocal_set(container, value):
                pass  # placeholder; handler uses closure assignment via list hack if needed
            '''
        ),
        encoding="utf-8",
    )
    print("wrote ws/handler.py (simplified)")

    # __init__.py
    (VOICE / "__init__.py").write_text(
        textwrap.dedent(
            '''\
            """Voice/audio subsystem: STT, TTS, WebSocket audio handling."""
            from backend.voice_audio.lifecycle import init_voice_audio, shutdown_voice_audio
            from backend.voice_audio.tts.routes import router as tts_router


            def register_voice_routes(app, require_login=None) -> None:
                app.include_router(tts_router)
                if require_login is not None:
                    from backend.voice_audio.stt.routes import register_stt_routes
                    from fastapi import APIRouter
                    stt_router = APIRouter()
                    register_stt_routes(stt_router, require_login)
                    app.include_router(stt_router)
            '''
        ),
        encoding="utf-8",
    )

    # Patch main: write callback functions file snippet to insert
    callback_block = f'''
# ========== VOICE WS CALLBACKS (Phase 1 extraction) ==========
async def _process_voice_transcript_ws(
    *,
    ws,
    conn_id: str,
    full_text: str,
    lang: str,
    t_meta,
    user,
    active_conversation_id,
    _activate_conversation,
    _conversation_ws,
    segments_list=None,
):
{"".join("    " + ln if ln.strip() else ln for ln in voice_transcript.splitlines(keepends=True))}

async def _process_ws_text_message(
    *,
    websocket,
    connection_id: str,
    payload: dict,
    user,
    session_language: str,
    ws_tenant_id: int,
    ws_owner,
    activate_conversation,
    conversation_ws_factory,
    set_session_language,
):
    nonlocal_session = [session_language]
{text_message}
'''
    # Save for manual insertion - part 3 doesn't auto-patch main yet
    (ROOT / "scripts" / "_phase1_callbacks_snippet.py").write_text(callback_block, encoding="utf-8")
    print("wrote scripts/_phase1_callbacks_snippet.py for main integration")


if __name__ == "__main__":
    main()
