#!/usr/bin/env python3
"""Apply Phase 1 voice_audio extraction to assistify_rag_server.py."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "backend" / "assistify_rag_server.py"


def read_lines() -> list[str]:
    return SRC.read_text(encoding="utf-8").splitlines(keepends=True)


def write_lines(lines: list[str]) -> None:
    SRC.write_text("".join(lines), encoding="utf-8")


def delete_ranges(lines: list[str], ranges: list[tuple[int, int]]) -> list[str]:
    drop = set()
    for start, end in ranges:
        for i in range(start, end + 1):
            drop.add(i)
    return [ln for i, ln in enumerate(lines, start=1) if i not in drop]


def insert_after_line(lines: list[str], needle: str, block: str, *, once: bool = True) -> list[str]:
    out: list[str] = []
    inserted = False
    for ln in lines:
        out.append(ln)
        if needle in ln and (not once or not inserted):
            out.append(block)
            inserted = True
    if not inserted:
        raise RuntimeError(f"needle not found: {needle!r}")
    return out


def replace_block(lines: list[str], start: int, end: int, block: str) -> list[str]:
    block_lines = block if block.endswith("\n") else block + "\n"
    if not block.endswith("\n"):
        block_lines = [block + "\n"]
    else:
        block_lines = [block] if "\n" not in block[:-1] else block.splitlines(keepends=True)
    return lines[: start - 1] + block_lines + lines[end:]


def extract_voice_transcript_body(lines: list[str]) -> str:
    body = lines[43738:43841]  # conversation persist through call_llm_streaming
    text = "".join(body)
    text = text.replace("requested_voice_lang", "lang")
    return text


def extract_text_message_body(lines: list[str]) -> str:
    body = lines[44086:44436]
    text = "".join(body)
    # Remove one indent level (28 spaces -> 4 spaces for function body)
    fixed = []
    for ln in body:
        if ln.startswith("                            "):
            fixed.append("    " + ln[28:])
        elif ln.strip() == "":
            fixed.append("\n")
        else:
            fixed.append(ln)
    return "".join(fixed)


def build_callbacks(voice_body: str, text_body: str) -> str:
    return f'''
# ========== VOICE WS CALLBACKS (Phase 1 — post-STT / typed text stay in RAG server) ==========

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
{voice_body}

async def _process_ws_text_message(
    *,
    websocket,
    connection_id: str,
    payload: dict,
    user,
    session_language_ref: list,
    ws_tenant_id: int,
    ws_owner,
    activate_conversation,
    conversation_ws_factory,
):
    session_language = session_language_ref[0]
{text_body}

def _build_voice_ws_deps():
    return VoiceWebSocketDeps(
        resolve_request_tenant=resolve_request_tenant,
        coerce_owner=_coerce_owner,
        get_or_create_conversation=get_or_create_conversation,
        bind_conversation_memory=bind_conversation_memory,
        append_conversation_message=append_conversation_message,
        persist_runtime_memory=persist_runtime_memory,
        send_final_response=send_final_response,
        process_voice_transcript=_process_voice_transcript_ws,
        process_text_message=_process_ws_text_message,
        emit_perf_report=_emit_perf_report,
        session_cookie=SESSION_COOKIE,
        serializer=serializer,
        set_request_tenant_id=_request_tenant_id.set,
        get_memory_snapshot=_get_memory_snapshot,
        get_stable_memory_snapshot=_get_stable_memory_snapshot,
        conversation_history=conversation_history,
        conversation_timestamps=conversation_timestamps,
        active_ws_connections=_active_ws_connections,
    )

_rag_ws_handler = create_rag_ws_handler(_build_voice_ws_deps())


@app.websocket("/ws")
async def rag_ws_endpoint(websocket: WebSocket):  # pyright: ignore
    await _rag_ws_handler(websocket)


'''


def build_ws_handler(lines: list[str]) -> str:
    """Transform original WS handler into voice_audio/ws/handler.py."""
    chunk = lines[43389:44490]
    text = "".join(chunk)

    # Strip decorator and outer function — body starts at await websocket.accept()
    text = re.sub(r'^@app\.websocket\("/ws"\)\s*\n', "", text, flags=re.MULTILINE)
    text = re.sub(
        r'^async def rag_ws_endpoint\(websocket: WebSocket\).*?:\s*\n',
        "",
        text,
        count=1,
        flags=re.MULTILINE,
    )

    # Remove global declarations at top of handler
    text = re.sub(
        r"    global _active_voice_task, _active_voice_conn_id\n"
        r"    global _sessions_blocked, _sessions_blocked_since, _consecutive_gpu_growth, _consecutive_cpu_growth\n",
        "",
        text,
        count=1,
    )

    # auto_transcribe block — delete from marker through _auto_transcribe alias
    text = re.sub(
        r"    # ========== STABILIZED auto_transcribe ==========[\s\S]*?"
        r"    _auto_transcribe: Callable\[\.\.\., Awaitable\[None\]\] = auto_transcribe\n\n",
        "",
        text,
        count=1,
    )

    # ConversationCaptureWebSocket factory
    text = text.replace(
        "return cast(WebSocket, ConversationCaptureWebSocket(websocket, conversation_id, connection_id))",
        "return cast(WebSocket, ConversationCaptureWebSocket(\n"
        "            websocket, conversation_id, connection_id,\n"
        "            deps.append_conversation_message, deps.persist_runtime_memory,\n"
        "        ))",
    )

    # Wire deps for tenant resolution
    text = text.replace("resolve_request_tenant(user)", "deps.resolve_request_tenant(user)")
    text = text.replace("_coerce_owner(user)", "deps.coerce_owner(user)")
    text = text.replace("_request_tenant_id.set(ws_tenant_id)", "deps.set_request_tenant_id(ws_tenant_id)")
    text = text.replace("get_or_create_conversation(", "deps.get_or_create_conversation(")
    text = text.replace("bind_conversation_memory(", "deps.bind_conversation_memory(")

    # Memory / voice helpers
    text = text.replace("_voice_transcribe_in_flight(", "memory_guard.voice_transcribe_in_flight(")
    text = text.replace("_assign_voice_transcribe_task(", "memory_guard.assign_voice_transcribe_task(")
    text = text.replace("_cancel_active_ws_tts(", "cancel_active_ws_tts(")
    text = text.replace("_active_voice_task", "memory_guard.active_voice_task")
    text = text.replace("_active_voice_conn_id", "memory_guard.active_voice_conn_id")
    text = text.replace("_sessions_blocked", "memory_guard.sessions_blocked")
    text = text.replace("_sessions_blocked_since", "memory_guard.sessions_blocked_since")
    text = text.replace("_consecutive_gpu_growth", "memory_guard.consecutive_gpu_growth")
    text = text.replace("_consecutive_cpu_growth", "memory_guard.consecutive_cpu_growth")
    text = text.replace("_pipeline_run_count", "memory_guard.pipeline_run_count")
    text = text.replace("_last_gpu_reserved_mb", "memory_guard.last_gpu_reserved_mb")
    text = text.replace("_VOICE_MIN_TRANSCRIBE_BYTES", "config.VOICE_MIN_TRANSCRIBE_BYTES")

    # Active connections via deps
    text = text.replace("_active_ws_connections[connection_id] = websocket", "deps.active_ws_connections[connection_id] = websocket")
    text = text.replace("_active_ws_connections.pop(connection_id, None)", "deps.active_ws_connections.pop(connection_id, None)")

    # Conversation history cleanup via deps
    text = text.replace("conversation_history[connection_id]", "deps.conversation_history[connection_id]")
    text = text.replace("if connection_id in conversation_history:", "if connection_id in deps.conversation_history:")
    text = text.replace("del conversation_history[connection_id]", "del deps.conversation_history[connection_id]")
    text = text.replace("if connection_id in conversation_timestamps:", "if connection_id in deps.conversation_timestamps:")
    text = text.replace("del conversation_timestamps[connection_id]", "del deps.conversation_timestamps[connection_id]")

    # _run_transcribe_task helper inserted before try loop
    helper = '''
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

'''
    text = text.replace("    try:\n        while True:", helper + "    try:\n        while True:", 1)

    text = text.replace("_auto_transcribe(", "_run_transcribe_task(")

    # Replace typed text branch with callback
    text = re.sub(
        r"                        elif \"text\" in payload:[\s\S]*?"
        r"                                persist_runtime_memory\(connection_id, conversation_id_for_text\)\n",
        "                        elif \"text\" in payload:\n"
        "                            await deps.process_text_message(\n"
        "                                websocket=websocket,\n"
        "                                connection_id=connection_id,\n"
        "                                payload=payload,\n"
        "                                user=user,\n"
        "                                session_language_ref=session_language_ref,\n"
        "                                ws_tenant_id=ws_tenant_id,\n"
        "                                ws_owner=ws_owner,\n"
        "                                activate_conversation=_activate_conversation,\n"
        "                                conversation_ws_factory=_conversation_ws,\n"
        "                            )\n",
        text,
        count=1,
    )

    # session_language_ref for mutable session lang
    text = text.replace(
        "    session_language = \"en\"",
        "    session_language = \"en\"\n    session_language_ref = [session_language]",
        1,
    )
    text = text.replace("session_language = new_lang", "session_language_ref[0] = new_lang; session_language = new_lang")

    header = '''"""WebSocket /ws handler for voice audio and control messages."""
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
from backend.voice_audio.ws.audio_pipeline import run_auto_transcribe
from backend.voice_audio.ws.capture import ConversationCaptureWebSocket

logger = logging.getLogger("voice_audio.ws.handler")


def create_rag_ws_handler(deps: VoiceWebSocketDeps) -> Callable:
    async def rag_ws_handler(websocket: WebSocket) -> None:
'''
    footer = '''
    return rag_ws_handler
'''

    # Fix interrupt_events / ws locks to use state module
    text = text.replace("interrupt_events[", "state.interrupt_events[")
    text = text.replace("interrupt_events.get(", "state.interrupt_events.get(")
    text = text.replace("if connection_id in interrupt_events:", "if connection_id in state.interrupt_events:")
    text = text.replace("del interrupt_events[connection_id]", "del state.interrupt_events[connection_id]")
    text = text.replace("_ws_write_locks", "state.ws_write_locks")
    text = text.replace("voice_semaphore", "state.voice_semaphore")
    text = text.replace("_get_memory_snapshot()", "deps.get_memory_snapshot()")
    text = text.replace("WHISPER_AVAILABLE", "state.WHISPER_AVAILABLE")
    text = text.replace("SAFE_UNBLOCK_CPU_MB", "memory_guard.SAFE_UNBLOCK_CPU_MB")
    text = text.replace("SAFE_UNBLOCK_GPU_MB", "memory_guard.SAFE_UNBLOCK_GPU_MB")
    # Avoid double deps. prefix
    text = text.replace("deps.deps.", "deps.")
    text = text.replace("EFFECTIVE_DISABLE_WHISPER", "config.EFFECTIVE_DISABLE_WHISPER")
    text = text.replace("send_final_response(", "deps.send_final_response(")

    # Indent body for nested function
    body_lines = []
    for ln in text.splitlines(keepends=True):
        if ln.strip():
            body_lines.append("        " + ln)
        else:
            body_lines.append("\n")

    return header + "".join(body_lines) + footer


def main() -> None:
    lines = read_lines()
    voice_body = extract_voice_transcript_body(lines)
    text_body = extract_text_message_body(lines)

    # Write handler.py from original WS block
    handler_src = build_ws_handler(lines)
    (ROOT / "backend" / "voice_audio" / "ws" / "handler.py").write_text(handler_src, encoding="utf-8")
    print("wrote backend/voice_audio/ws/handler.py")

    (ROOT / "backend" / "voice_audio" / "ws" / "__init__.py").write_text(
        'from backend.voice_audio.ws.handler import create_rag_ws_handler\n'
        'from backend.voice_audio.ws.capture import ConversationCaptureWebSocket\n'
        'from backend.voice_audio.ws.audio_pipeline import run_auto_transcribe\n',
        encoding="utf-8",
    )

    # Delete extracted blocks (1-indexed inclusive)
    delete = [
        (44562, 44575),  # asr-status
        (43389, 44490),  # WS handler (replaced below)
        (43175, 43387),  # TTS client + /tts route
        (41974, 42046),  # arabic routes
        (35993, 36729),  # TTS streaming helpers
        (21437, 21513),  # arabic STT helpers
        (908, 937),      # ConversationCaptureWebSocket
        (6865, 6915),    # whisper multilingual loader
        (62, 88),        # voice globals (replaced with import)
    ]
    lines = delete_ranges(lines, delete)

    # Voice memory guard import block
    voice_import = (
        "from backend.voice_audio import memory_guard\n"
        "from backend.voice_audio.config import VOICE_MIN_TRANSCRIBE_BYTES as _VOICE_MIN_TRANSCRIBE_BYTES\n"
        "from backend.voice_audio import state as voice_state\n"
    )
    lines = insert_after_line(lines, "from typing import Optional, TYPE_CHECKING", voice_import)

    # Voice audio wiring imports (after config_head import)
    wiring_import = (
        "from backend.voice_audio import register_voice_routes, init_voice_audio, shutdown_voice_audio\n"
        "from backend.voice_audio import state as voice_state\n"
        "from backend.voice_audio.ws.handler import create_rag_ws_handler\n"
        "from backend.voice_audio.deps import VoiceWebSocketDeps\n"
        "from backend.voice_audio.tts.streaming import (\n"
        "    cancel_active_ws_tts,\n"
        "    tts_progressive_response,\n"
        "    remember_ws_tts_task,\n"
        "    client_tts_allowed as _client_tts_allowed,\n"
        ")\n"
    )
    lines = insert_after_line(lines, "from backend.config_head import *", wiring_import)

    # Sync whisper/tts globals with voice_state module
    lines = insert_after_line(
        lines,
        "xtts_model = None  # kept for status endpoint backward compat",
        "\n# Aliased to voice_audio.state (lifecycle updates these)\n"
        "def _sync_voice_models_from_state():\n"
        "    global whisper_model, whisper_model_multilingual, tts_session, xtts_model, llm_session\n"
        "    whisper_model = voice_state.whisper_model\n"
        "    whisper_model_multilingual = voice_state.whisper_model_multilingual\n"
        "    tts_session = voice_state.tts_session\n"
        "    xtts_model = voice_state.xtts_model\n"
        "    llm_session = voice_state.llm_session or llm_session\n\n",
    )

    # Insert callbacks + thin WS wrapper before kb-events WS
    callbacks = build_callbacks(voice_body, text_body)
    lines = insert_after_line(lines, "# ========== WEBSOCKET: Admin KB-events real-time feed ==========", callbacks)

    # Register voice HTTP routes after require_login is defined
    lines = insert_after_line(
        lines,
        "    return wrapper",
        "\nregister_voice_routes(app, require_login)\n",
    )

    # Patch startup: remove duplicate tts session block
    lines = delete_ranges(lines, [(7194, 7206)])

    # Replace whisper/xtts init with init_voice_audio
    startup_replacement = '''    # Voice STT/TTS init (Phase 1: voice_audio package)
    await init_voice_audio(
        app,
        safe_mode=ASSISTIFY_SAFE_MODE,
        disable_warmup=EFFECTIVE_DISABLE_WARMUP,
    )
    _sync_voice_models_from_state()
    logger.info("✓ Voice audio subsystem initialized")

'''
    # Find and replace block from "# Initialize faster-whisper" through warmup xtts create_task
    full = "".join(lines)
    pattern = (
        r"    # Initialize faster-whisper \(GPU required\)[\s\S]*?"
        r"        asyncio\.create_task\(_warmup_xtts\(\)\)\n"
    )
    if re.search(pattern, full):
        full = re.sub(pattern, startup_replacement, full, count=1)
    else:
        print("WARNING: startup whisper block not found")
    lines = full.splitlines(keepends=True)

    # Patch send_final_response TTS delegation
    full = "".join(lines)
    full = full.replace("_cancel_active_ws_tts(", "cancel_active_ws_tts(")
    full = full.replace("_tts_progressive_response(", "tts_progressive_response(")
    full = full.replace("_remember_ws_tts_task(", "remember_ws_tts_task(")
    full = full.replace("_WS_TTS_ACTIVE_RESPONSE_IDS[", "voice_state.ws_tts_active_response_ids[")
    full = full.replace("_WS_TTS_ACTIVE_RESPONSE_IDS.get(", "voice_state.ws_tts_active_response_ids.get(")
    full = full.replace("_WS_TTS_ACTIVE_RESPONSE_IDS.pop(", "voice_state.ws_tts_active_response_ids.pop(")
    lines = full.splitlines(keepends=True)

    # _ws_write_locks -> state
    full = "".join(lines)
    full = full.replace("_ws_write_locks", "voice_state.ws_write_locks")
    lines = full.splitlines(keepends=True)

    # memory guard globals in main
    for old, new in [
        ("_sessions_blocked", "memory_guard.sessions_blocked"),
        ("_sessions_blocked_since", "memory_guard.sessions_blocked_since"),
        ("_consecutive_gpu_growth", "memory_guard.consecutive_gpu_growth"),
        ("_consecutive_cpu_growth", "memory_guard.consecutive_cpu_growth"),
        ("_pipeline_run_count", "memory_guard.pipeline_run_count"),
        ("_last_gpu_reserved_mb", "memory_guard.last_gpu_reserved_mb"),
        ("_active_voice_task", "memory_guard.active_voice_task"),
        ("_active_voice_conn_id", "memory_guard.active_voice_conn_id"),
    ]:
        full = "".join(lines)
        if old in full:
            full = full.replace(old, new)
            lines = full.splitlines(keepends=True)

    write_lines(lines)
    print(f"Patched {SRC} ({len(lines)} lines)")


if __name__ == "__main__":
    main()
