"""WebSocket /ws handler for voice audio and control messages."""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Callable, cast

import numpy as np
import torch
from fastapi import WebSocket, WebSocketDisconnect

from backend.voice_audio import config, memory_guard, state
from backend.voice_audio.config import SAMPLE_RATE, XTTS_LANGUAGE, EFFECTIVE_DISABLE_WHISPER
from backend.voice_audio.deps import VoiceWebSocketDeps
from backend.voice_audio.tts.streaming import cancel_active_ws_tts
from backend.voice_audio.ws.audio_pipeline import run_auto_transcribe, send_stt_failed
from backend.voice_audio.ws.capture import ConversationCaptureWebSocket
from Login_system.session_validation import load_and_validate_session_token

logger = logging.getLogger("voice_audio.ws.handler")


def create_rag_ws_handler(deps: VoiceWebSocketDeps) -> Callable:
    async def rag_ws_handler(websocket: WebSocket) -> None:
        await websocket.accept()
        connection_id = f"conn_{uuid.uuid4().hex[:8]}"
        logger.info(f"New websocket connection {connection_id}")
        # Register for KB broadcast notifications (tenant bound after auth below).
        deps.active_ws_connections[connection_id] = websocket

        # Create cancel event for barge-in support
        cancel_event = asyncio.Event()
        state.interrupt_events[connection_id] = cancel_event
        # Per-connection write lock — shared with _tts_arabic_response background tasks
        state.ws_write_locks[connection_id] = asyncio.Lock()

        user = None
        try:
            token = websocket.cookies.get(deps.session_cookie)
            if token and deps.serializer is not None:
                user, _err = load_and_validate_session_token(deps.serializer, token)
        except Exception:
            user = None

        ws_owner = deps.coerce_owner(user)
        if not ws_owner:
            try:
                from config import ALLOW_PUBLIC_GUEST_CHAT
                from Login_system.guest_session import GUEST_OWNER_HEADER, is_valid_guest_id

                if ALLOW_PUBLIC_GUEST_CHAT:
                    guest_hdr = websocket.headers.get(GUEST_OWNER_HEADER) or websocket.headers.get(
                        str(GUEST_OWNER_HEADER).lower()
                    )
                    if guest_hdr and is_valid_guest_id(guest_hdr):
                        ws_owner = str(guest_hdr).strip()
            except Exception:
                pass

        if not user and not ws_owner:
            logger.debug(f"Websocket {connection_id}: no valid session cookie found; continuing as anonymous")
        elif not ws_owner:
            ws_owner = deps.coerce_owner(user)

        if not ws_owner:
            ws_owner = None

        # Per-connection active chat tenant (mutable; not session-scoped).
        # Resolve from the authenticated session immediately so the tenant context
        # is correct from the first message, not only after set_conversation arrives.
        _default_tid = int(getattr(deps, "default_tenant_id", 1) or 1)
        _initial_tid = _default_tid
        if user is not None and deps.resolve_request_tenant is not None:
            try:
                _initial_tid = int(deps.resolve_request_tenant(user))
            except Exception:
                _initial_tid = _default_tid
        session_tenant_ref = [_initial_tid]
        if deps.set_request_tenant_id is not None:
            deps.set_request_tenant_id(session_tenant_ref[0])
        if deps.active_ws_tenants is not None:
            deps.active_ws_tenants[connection_id] = session_tenant_ref[0]
        logger.info(
            "Websocket %s initial chat tenant=%s owner=%s",
            connection_id,
            session_tenant_ref[0],
            ws_owner,
        )

        def _current_chat_tenant() -> int:
            return int(session_tenant_ref[0])

        def _activate_conversation(requested_id: str | None = None) -> str:
            nonlocal active_conversation_id
            clean_requested = str(requested_id or "").strip() or active_conversation_id
            conversation = deps.get_or_create_conversation(
                clean_requested,
                owner=ws_owner,
                active_tenant_id=_current_chat_tenant(),
            )
            conversation_id = str(conversation["id"])
            active_conversation_id = conversation_id
            if conversation.get("active_tenant_id") is not None:
                session_tenant_ref[0] = int(conversation["active_tenant_id"])
                if deps.set_request_tenant_id is not None:
                    deps.set_request_tenant_id(session_tenant_ref[0])
            deps.bind_conversation_memory(connection_id, conversation_id)
            return conversation_id

        # Buffer for accumulating audio chunks
        audio_buffer = bytearray()
        first_audio_arrival = None
        speech_start_time = None
        silence_counter = 0
        silence_chunks_needed = 12
        silence_threshold_energy = 0.008
        session_language = "en"
        session_language_ref = [session_language]
        active_conversation_id: str | None = None
        current_ws_conversation_id: str | None = None
        stt_disabled_notified = False

        def _conversation_ws(conversation_id: str) -> WebSocket:
            return cast(WebSocket, ConversationCaptureWebSocket(
                websocket, conversation_id, connection_id,
                deps.append_conversation_message, deps.persist_runtime_memory,
            ))


        async def _run_transcribe_task(data_bytes: bytes, ws, conn_id, t_meta=None, lang="en") -> None:
            await run_auto_transcribe(
                data_bytes,
                ws,
                conn_id,
                process_voice_transcript=lambda **kw: deps.process_voice_transcript(
                    user=user,
                    active_conversation_id=active_conversation_id,
                    _activate_conversation=_activate_conversation,
                    _conversation_ws=_conversation_ws,
                    **kw,
                ),
                send_final_response=deps.send_final_response,
                t_meta=t_meta,
                lang=lang,
                get_memory_snapshot=deps.get_memory_snapshot,
                get_stable_memory_snapshot=deps.get_stable_memory_snapshot,
            )

        # Per-connection text/control rate bucket: max 30 text frames per 60s.
        # Binary audio streams at ~20 fps and must not count toward this limit.
        _ws_msg_bucket = {"count": 0, "reset": time.monotonic() + 60}
        _WS_MSG_RATE_LIMIT = 30

        try:
            while True:
                msg = await websocket.receive()
                if msg["type"] == "websocket.receive":
                    if "bytes" in msg and msg["bytes"] is not None:
                        audio = msg["bytes"]
                        current_time = time.perf_counter()

                        if not first_audio_arrival and len(audio_buffer) == 0:
                            first_audio_arrival = current_time

                        if config.EFFECTIVE_DISABLE_WHISPER or not state.WHISPER_AVAILABLE:
                            if not stt_disabled_notified:
                                stt_disabled_notified = True
                                logger.warning(f"{connection_id} received audio while STT is disabled/unavailable")
                                try:
                                    await deps.send_final_response(
                                        connection_id,
                                        "Speech to text is currently disabled.",
                                        XTTS_LANGUAGE,
                                        False,
                                        websocket=websocket,
                                        sources=0,
                                        arabic_mode=False,
                                        t_meta={"request_start": time.perf_counter()},
                                        branch="stt_disabled",
                                        extra_payload={"error": True},
                                    )
                                except Exception:
                                    pass
                            continue

                        # Calculate energy of this audio chunk to detect silence
                        pcm_samples = np.frombuffer(audio, dtype=np.int16).astype(np.float32) / 32768.0
                        energy = np.sqrt(np.mean(pcm_samples ** 2))

                        if energy < silence_threshold_energy:
                            # This chunk is silent
                            silence_counter += 1
                        else:
                            # Speech detected - reset silence counter
                            if not speech_start_time and len(audio_buffer) > 0:
                                speech_start_time = current_time
                                logger.debug(f"{connection_id} Speech start detected (buffer={len(audio_buffer)} bytes, energy={energy:.6f})")
                            silence_counter = 0

                        # Always accumulate audio
                        audio_buffer.extend(audio)

                        if len(audio_buffer) > config.VOICE_MAX_BUFFER_BYTES:
                            logger.warning(
                                "%s audio buffer cap reached (%d bytes); forcing transcription",
                                connection_id,
                                len(audio_buffer),
                            )
                            silence_counter = silence_chunks_needed
                            if speech_start_time is None and len(audio_buffer) > config.VOICE_MIN_TRANSCRIBE_BYTES:
                                speech_start_time = current_time

                        # If we've had enough consecutive silent chunks AND we have audio buffered
                        # AND we actually detected speech at some point (prevents noise-only transcriptions)
                        if silence_counter >= silence_chunks_needed and len(audio_buffer) > config.VOICE_MIN_TRANSCRIBE_BYTES and speech_start_time is not None:
                            # Transcribe everything we've accumulated
                            # 32000 bytes = ~1.0s minimum audio at 16 kHz mono PCM16
                            speech_end_time = current_time
                            chunk = bytes(audio_buffer)
                            audio_duration_sec = len(chunk) / (SAMPLE_RATE * 2)
                            triggered_after = silence_counter  # capture before reset
                            audio_buffer.clear()
                            silence_counter = 0

                            # Capture timing metadata
                            timing_meta = {
                                "first_audio": first_audio_arrival,
                                "speech_start": speech_start_time,
                                "speech_end": speech_end_time,
                                "audio_len_sec": audio_duration_sec
                            }
                            # Reset for next segment
                            first_audio_arrival = None
                            speech_start_time = None

                            if memory_guard.voice_transcribe_in_flight(connection_id):
                                logger.info(
                                    f"{connection_id} VAD transcribe skipped — transcription already in flight"
                                )
                                audio_buffer.clear()
                                silence_counter = 0
                                first_audio_arrival = None
                                speech_start_time = None
                            else:
                                logger.info(f"{connection_id} ✓ TRANSCRIBE TRIGGERED: {len(chunk)} bytes ({audio_duration_sec:.2f}s audio) after {triggered_after} silent chunks")
                                task = asyncio.create_task(_run_transcribe_task(chunk, websocket, connection_id, timing_meta, lang=session_language))
                                memory_guard.assign_voice_transcribe_task(task, connection_id)
                        elif silence_counter >= silence_chunks_needed and len(audio_buffer) <= config.VOICE_MIN_TRANSCRIBE_BYTES and speech_start_time is not None:
                            # Buffer too small to be a real utterance — drain it
                            logger.debug(f"{connection_id} Buffer too small ({len(audio_buffer)} bytes < {config.VOICE_MIN_TRANSCRIBE_BYTES} min), discarding")
                            audio_buffer.clear()
                            silence_counter = 0
                            speech_start_time = None
                            first_audio_arrival = None
                        elif silence_counter >= silence_chunks_needed and speech_start_time is None:
                            # Silence accumulated but no speech was ever detected — just background
                            # noise. Drain the buffer so we don't carry stale noise into next segment.
                            if len(audio_buffer) > 0:
                                logger.debug(f"{connection_id} Draining {len(audio_buffer)} bytes (no speech detected in this segment)")
                            audio_buffer.clear()
                            silence_counter = 0
                            first_audio_arrival = None
                    elif "text" in msg and msg["text"] is not None:
                        # Rate-limit text/control frames only (binary audio is exempt).
                        _now_mono = time.monotonic()
                        if _now_mono > _ws_msg_bucket["reset"]:
                            _ws_msg_bucket["count"] = 0
                            _ws_msg_bucket["reset"] = _now_mono + 60
                        _ws_msg_bucket["count"] += 1
                        if _ws_msg_bucket["count"] > _WS_MSG_RATE_LIMIT:
                            await websocket.send_json({"type": "error", "message": "Rate limit exceeded. Please wait before sending more messages."})
                            continue
                        try:
                            payload = json.loads(msg["text"])
                        except Exception:
                            payload = {"text": msg["text"]}

                        if isinstance(payload, dict):
                            if payload.get("type") == "ping":
                                await websocket.send_json({"type": "pong"})

                            elif payload.get("type") == "control":
                                # Handle control messages like stop/start recording
                                action = payload.get("action")
                                if action == "stop_recording":
                                    # User stopped recording — transcribe unless VAD already started STT.
                                    if memory_guard.voice_transcribe_in_flight(connection_id):
                                        if len(audio_buffer) > 0:
                                            logger.info(
                                                f"{connection_id} ⏹ MANUAL STOP skipped — transcription already in flight "
                                                f"(discarding {len(audio_buffer)} trailing bytes)"
                                            )
                                            audio_buffer.clear()
                                        else:
                                            logger.info(
                                                f"{connection_id} ⏹ MANUAL STOP skipped — transcription already in flight"
                                            )
                                        silence_counter = 0
                                        speech_start_time = None
                                        first_audio_arrival = None
                                    elif len(audio_buffer) > 0:
                                        chunk = bytes(audio_buffer)
                                        audio_duration_sec = len(chunk) / (SAMPLE_RATE * 2)
                                        audio_buffer.clear()
                                        silence_counter = 0
                                        speech_start_time = None
                                        first_audio_arrival = None
                                        # Match auto_transcribe minimum (~0.25s)
                                        if len(chunk) < config.VOICE_MANUAL_STOP_MIN_BYTES:
                                            logger.info(
                                                f"{connection_id} ⏹ MANUAL STOP ignored — buffer too short "
                                                f"({len(chunk)} bytes, {audio_duration_sec:.2f}s)"
                                            )
                                            await send_stt_failed(
                                                websocket,
                                                connection_id,
                                                "manual_stop_too_short",
                                                "Didn't catch enough audio. Please try again.",
                                            )
                                        else:
                                            logger.info(
                                                f"{connection_id} ⏹ MANUAL STOP: transcribing {len(chunk)} bytes "
                                                f"({audio_duration_sec:.2f}s audio)"
                                            )
                                            task = asyncio.create_task(
                                                _run_transcribe_task(chunk, websocket, connection_id, lang=session_language)
                                            )
                                            memory_guard.assign_voice_transcribe_task(task, connection_id)
                                elif action == "clear_audio_buffer":
                                    # User muted - clear the buffer without transcribing
                                    if len(audio_buffer) > 0:
                                        logger.info(f"{connection_id} Clearing audio buffer ({len(audio_buffer)} bytes) due to mute")
                                        audio_buffer.clear()
                                        silence_counter = 0
                                    else:
                                        logger.info(f"{connection_id} Recording stopped - buffer cleared")
                                elif action == "interrupt":
                                    # Barge-in: user started speaking during AI TTS playback
                                    cancel_evt = state.interrupt_events.get(connection_id)
                                    if cancel_evt:
                                        cancel_evt.set()
                                    cancel_active_ws_tts(connection_id, "user_barge_in")
                                    audio_buffer.clear()
                                    silence_counter = 0
                                    logger.info(f"{connection_id} User barge-in - LLM generation interrupted")

                                elif action == "set_language":
                                    # Frontend informed us of language selection; voice STT only accepts en/ar.
                                    new_lang = str(payload.get("language", "en") or "en").strip().lower()
                                    if new_lang not in ("en", "ar"):
                                        new_lang = "en"
                                    session_language_ref[0] = new_lang; session_language = new_lang
                                    logger.info(f"{connection_id} Language set to: {session_language}")

                                elif action == "set_conversation_id":
                                    requested_conversation_id = str(payload.get("conversation_id") or "").strip()
                                    if requested_conversation_id and requested_conversation_id == current_ws_conversation_id:
                                        logger.info("[CONV] duplicate set_conversation ignored id=%s", requested_conversation_id)
                                        continue
                                    conversation_id = _activate_conversation(requested_conversation_id)
                                    current_ws_conversation_id = conversation_id
                                    if deps.active_ws_tenants is not None:
                                        deps.active_ws_tenants[connection_id] = session_tenant_ref[0]
                                    await websocket.send_json({
                                        "type": "conversation",
                                        "conversation_id": conversation_id,
                                        "active_tenant_id": session_tenant_ref[0],
                                    })

                                elif action == "set_active_tenant":
                                    raw_tid = payload.get("tenant_id")
                                    if raw_tid is None:
                                        continue
                                    if deps.assert_chat_tenant_allowed is not None:
                                        new_tid = deps.assert_chat_tenant_allowed(user, raw_tid)
                                    else:
                                        new_tid = int(raw_tid)
                                    from_tid = session_tenant_ref[0]
                                    session_tenant_ref[0] = new_tid
                                    if deps.set_request_tenant_id is not None:
                                        deps.set_request_tenant_id(new_tid)
                                    if deps.active_ws_tenants is not None:
                                        deps.active_ws_tenants[connection_id] = new_tid
                                    conv_id = active_conversation_id or current_ws_conversation_id
                                    if conv_id and deps.set_conversation_active_tenant is not None:
                                        stored_tid = None
                                        try:
                                            from backend import chat_store as _chat_store_mod

                                            stored_tid = _chat_store_mod.get_active_tenant_id(conv_id, ws_owner)
                                        except Exception:
                                            stored_tid = None
                                        if stored_tid is not None and int(stored_tid) == int(new_tid):
                                            logger.info(
                                                "[CHAT] skip duplicate set_active_tenant id=%s tenant=%s",
                                                conv_id,
                                                new_tid,
                                            )
                                        else:
                                            try:
                                                deps.set_conversation_active_tenant(
                                                    conv_id,
                                                    new_tid,
                                                    ws_owner,
                                                    from_tenant_id=from_tid,
                                                    emit_system_message=True,
                                                )
                                            except Exception:
                                                logger.exception("[CHAT] set_active_tenant failed id=%s", conv_id)
                                    from_name = (
                                        deps.get_tenant_name(from_tid) if deps.get_tenant_name else str(from_tid)
                                    )
                                    to_name = (
                                        deps.get_tenant_name(new_tid) if deps.get_tenant_name else str(new_tid)
                                    )
                                    await websocket.send_json({
                                        "type": "tenant_switched",
                                        "from_tenant_id": from_tid,
                                        "to_tenant_id": new_tid,
                                        "from_name": from_name,
                                        "to_name": to_name,
                                    })

                            elif "text" in payload:
                                await deps.process_text_message(
                                    websocket=websocket,
                                    connection_id=connection_id,
                                    payload=payload,
                                    user=user,
                                    session_language_ref=session_language_ref,
                                    ws_tenant_ref=session_tenant_ref,
                                    ws_owner=ws_owner,
                                    activate_conversation=_activate_conversation,
                                    conversation_ws_factory=_conversation_ws,
                                )

                elif msg["type"] == "websocket.disconnect":
                    logger.info(f"Websocket {connection_id} disconnected")
                    break
        except WebSocketDisconnect:
            logger.info(f"Websocket {connection_id} closed by client")
        except Exception as e:
            # FAILURE RESPONSE MODE: log diagnostic summary on unexpected error
            mem = deps.get_memory_snapshot()
            logger.exception(f"Websocket {connection_id} error: {e}")
            logger.error(f"  DIAGNOSTIC: GPU={mem['gpu_reserved_mb']:.0f}MB  CPU={mem['cpu_rss_mb']:.0f}MB  "
                         f"pipeline_runs={memory_guard.pipeline_run_count}  sessions_blocked={memory_guard.sessions_blocked}")
            try:
                await websocket.close()
            except Exception:
                pass
        finally:
            # Stop in-flight TTS/LLM work before tearing down per-connection state.
            cancel_evt = state.interrupt_events.get(connection_id)
            if cancel_evt is not None and not cancel_evt.is_set():
                cancel_evt.set()
            cancel_active_ws_tts(connection_id, "ws_disconnect")
            ws_tts_task = state.ws_tts_active_tasks.pop(connection_id, None)
            if ws_tts_task and not ws_tts_task.done():
                ws_tts_task.cancel()
            state.ws_tts_active_response_ids.pop(connection_id, None)

            if memory_guard.active_voice_task and not memory_guard.active_voice_task.done() and memory_guard.active_voice_conn_id == connection_id:
                logger.info(f"Cancelling dangling voice task for {connection_id}")
                memory_guard.active_voice_task.cancel()
                try:
                    await memory_guard.active_voice_task
                except (asyncio.CancelledError, Exception):
                    pass

            if deps.on_ws_disconnect is not None:
                try:
                    deps.on_ws_disconnect(connection_id)
                except Exception:
                    logger.exception("on_ws_disconnect failed for %s", connection_id)

            if connection_id in state.interrupt_events:
                del state.interrupt_events[connection_id]
            state.ws_write_locks.pop(connection_id, None)
            # Clean up conversation memory for this connection
            if deps.conversation_history is not None and connection_id in deps.conversation_history:
                del deps.conversation_history[connection_id]
            if deps.conversation_timestamps is not None and connection_id in deps.conversation_timestamps:
                del deps.conversation_timestamps[connection_id]
            # Deregister from KB broadcast pool
            if deps.active_ws_connections is not None:
                deps.active_ws_connections.pop(connection_id, None)
            if deps.active_ws_tenants is not None:
                deps.active_ws_tenants.pop(connection_id, None)
            mem_final = deps.get_memory_snapshot()
            if memory_guard.sessions_blocked:
                if (
                    mem_final["cpu_rss_mb"] <= memory_guard.SAFE_UNBLOCK_CPU_MB
                    and (
                        not torch.cuda.is_available()
                        or mem_final["gpu_reserved_mb"] <= memory_guard.SAFE_UNBLOCK_GPU_MB
                    )
                ):
                    memory_guard.sessions_blocked = False
                    memory_guard.sessions_blocked_since = 0.0
                    memory_guard.consecutive_gpu_growth = 0
                    memory_guard.consecutive_cpu_growth = 0
                    logger.warning(
                        f"MEMORY GUARD AUTO-UNBLOCK after websocket cleanup [{connection_id}] "
                        f"| GPU={mem_final['gpu_reserved_mb']:.0f}MB CPU={mem_final['cpu_rss_mb']:.0f}MB"
                    )
            logger.info(f"Websocket {connection_id} fully cleaned up | GPU={mem_final['gpu_reserved_mb']:.0f}MB CPU={mem_final['cpu_rss_mb']:.0f}MB")

    return rag_ws_handler
