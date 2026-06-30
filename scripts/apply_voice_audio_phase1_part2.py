#!/usr/bin/env python3
"""Phase 1 part 2: extract TTS/WS, patch assistify_rag_server.py."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "backend" / "assistify_rag_server.py"
VOICE = ROOT / "backend" / "voice_audio"


def read_lines() -> list[str]:
    return SRC.read_text(encoding="utf-8").splitlines(keepends=True)


def slice_lines(lines: list[str], start: int, end: int) -> str:
    return "".join(lines[start - 1 : end])


def xform_tts(code: str) -> str:
    repl = [
        (r"\b_ws_write_locks\b", "state.ws_write_locks"),
        (r"\btts_session\b", "state.tts_session"),
        (r"\b_WS_TTS_ACTIVE_RESPONSE_IDS\b", "state.ws_tts_active_response_ids"),
        (r"\b_WS_TTS_ACTIVE_TASKS\b", "state.ws_tts_active_tasks"),
        (r"\b_XTTS_SYNTH_SEM\b", "xtts_synth_sem"),
        (r"\b_XTTS_INFLIGHT\b", "xtts_inflight"),
        (r"\b_XTTS_CACHE\b", "xtts_cache"),
        (r"\b_XTTS_CACHE_LOCK\b", "xtts_cache_lock"),
        (r"\b_XTTS_CACHE_MAX_ENTRIES\b", "XTTS_CACHE_MAX_ENTRIES"),
        (r"\b_XTTS_CACHE_MAX_BYTES_PER_ENTRY\b", "XTTS_CACHE_MAX_BYTES_PER_ENTRY"),
        (r"\b_arabic_offtopic_pcm\b", "state.arabic_offtopic_pcm"),
        (r"\b_arabic_ack_pcm\b", "state.arabic_ack_pcm"),
        (r"\b_arabic_opener_pcm\b", "state.arabic_opener_pcm"),
        (r"\b_arabic_opener_pool\b", "state.arabic_opener_pool"),
        (r"def _ws_tts_is_active", "def ws_tts_is_active"),
        (r"def _log_tts_cancelled", "def log_tts_cancelled"),
        (r"def _cancel_active_ws_tts", "def cancel_active_ws_tts"),
        (r"def _remember_ws_tts_task", "def remember_ws_tts_task"),
        (r"async def _tts_progressive_response", "async def tts_progressive_response"),
        (r"async def _tts_arabic_response", "async def tts_arabic_response"),
        (r"async def _tts_single_response", "async def tts_single_response"),
        (r"def _client_tts_allowed", "def client_tts_allowed"),
        (r"def _normalize_tts_chunk_cache_text", "def normalize_tts_chunk_cache_text"),
        (r"def _is_tts_not_found_text", "def is_tts_not_found_text"),
        (r"def _is_tts_bullet_unit", "def is_tts_bullet_unit"),
        (r"def _join_tts_units", "def join_tts_units"),
        (r"def _split_long_tts_unit", "def split_long_tts_unit"),
        (r"def _spoken_tts_units", "def spoken_tts_units"),
        (r"def _preprocess_for_tts", "def preprocess_for_tts"),
        (r"def _tts_cache_key", "def tts_cache_key"),
        (r"def _wav_bytes_to_pcm16", "def wav_bytes_to_pcm16"),
        (r"async def _tts_cache_get", "async def tts_cache_get"),
        (r"async def _tts_cache_put", "async def tts_cache_put"),
        (r"async def _xtts_synthesize_full", "async def xtts_synthesize_full"),
        (r"\b_re_mod\b", "re"),
    ]
    for pat, rep in repl:
        code = re.sub(pat, rep, code)
    return code


def xform_ws(code: str) -> str:
    repl = [
        (r"@app\.websocket\(\"/ws\"\)\s*\nasync def rag_ws_endpoint", "async def rag_ws_handler"),
        (r"\b_active_voice_task\b", "memory_guard.active_voice_task"),
        (r"\b_active_voice_conn_id\b", "memory_guard.active_voice_conn_id"),
        (r"\b_sessions_blocked\b", "memory_guard.sessions_blocked"),
        (r"\b_sessions_blocked_since\b", "memory_guard.sessions_blocked_since"),
        (r"\b_consecutive_gpu_growth\b", "memory_guard.consecutive_gpu_growth"),
        (r"\b_consecutive_cpu_growth\b", "memory_guard.consecutive_cpu_growth"),
        (r"\b_last_gpu_reserved_mb\b", "memory_guard.last_gpu_reserved_mb"),
        (r"\b_pipeline_run_count\b", "memory_guard.pipeline_run_count"),
        (r"\b_voice_transcribe_in_flight\b", "memory_guard.voice_transcribe_in_flight"),
        (r"\b_assign_voice_transcribe_task\b", "memory_guard.assign_voice_transcribe_task"),
        (r"\b_Voice_MIN_TRANSCRIBE_BYTES\b", "config.VOICE_MIN_TRANSCRIBE_BYTES"),
        (r"\b_VOICE_MIN_TRANSCRIBE_BYTES\b", "config.VOICE_MIN_TRANSCRIBE_BYTES"),
        (r"\binterrupt_events\b", "state.interrupt_events"),
        (r"\b_ws_write_locks\b", "state.ws_write_locks"),
        (r"\b_active_ws_connections\b", "deps.active_ws_connections"),
        (r"\bSESSION_COOKIE\b", "deps.session_cookie"),
        (r"\bserializer\b", "deps.serializer"),
        (r"\bresolve_request_tenant\b", "deps.resolve_request_tenant"),
        (r"\b_coerce_owner\b", "deps.coerce_owner"),
        (r"\b_request_tenant_id\b", "_tenant_ctx"),
        (r"\bget_or_create_conversation\b", "deps.get_or_create_conversation"),
        (r"\bbind_conversation_memory\b", "deps.bind_conversation_memory"),
        (r"\bappend_conversation_message\b", "deps.append_conversation_message"),
        (r"\bpersist_runtime_memory\b", "deps.persist_runtime_memory"),
        (r"\bsend_final_response\b", "deps.send_final_response"),
        (r"\b_get_memory_snapshot\b", "deps.get_memory_snapshot"),
        (r"\b_get_stable_memory_snapshot\b", "deps.get_stable_memory_snapshot"),
        (r"\bSAFE_UNBLOCK_CPU_MB\b", "memory_guard.SAFE_UNBLOCK_CPU_MB"),
        (r"\bSAFE_UNBLOCK_GPU_MB\b", "memory_guard.SAFE_UNBLOCK_GPU_MB"),
        (r"\bGPU_GROWTH_DELTA_MB\b", "memory_guard.GPU_GROWTH_DELTA_MB"),
        (r"\bGPU_HIGH_WATER_MB\b", "memory_guard.GPU_HIGH_WATER_MB"),
        (r"\bCPU_GROWTH_DELTA_MB\b", "memory_guard.CPU_GROWTH_DELTA_MB"),
        (r"\bCPU_HIGH_WATER_MB\b", "memory_guard.CPU_HIGH_WATER_MB"),
        (r"\bMEMORY_GROWTH_LIMIT\b", "memory_guard.MEMORY_GROWTH_LIMIT"),
        (r"\bSAMPLE_RATE\b", "config.SAMPLE_RATE"),
        (r"\bEFFECTIVE_DISABLE_WHISPER\b", "config.EFFECTIVE_DISABLE_WHISPER"),
        (r"\bWHISPER_AVAILABLE\b", "state.WHISPER_AVAILABLE"),
        (r"\bXTTS_LANGUAGE\b", "config.XTTS_LANGUAGE"),
        (r"\b_cancel_active_ws_tts\b", "streaming.cancel_active_ws_tts"),
        (r"\bvoice_semaphore\b", "state.voice_semaphore"),
        (r"\bconversation_history\b", "deps.conversation_history"),
        (r"\bconversation_timestamps\b", "deps.conversation_timestamps"),
        (r"global _active_voice_task, _active_voice_conn_id", "global memory_guard.active_voice_task, memory_guard.active_voice_conn_id"),
        (r"global _sessions_blocked, _sessions_blocked_since, _consecutive_gpu_growth, _consecutive_cpu_growth",
         "global memory_guard.sessions_blocked, memory_guard.sessions_blocked_since, memory_guard.consecutive_gpu_growth, memory_guard.consecutive_cpu_growth"),
    ]
    for pat, rep in repl:
        code = re.sub(pat, rep, code)
    return code


def main() -> None:
    lines = read_lines()

    (VOICE / "tts").mkdir(parents=True, exist_ok=True)
    (VOICE / "ws").mkdir(parents=True, exist_ok=True)

    # --- TTS text_utils ---
    text_utils_body = slice_lines(lines, 35997, 36119) + slice_lines(lines, 8847, 8896)
    text_utils_header = '''"""TTS text chunking and preprocessing."""
from __future__ import annotations

import re

try:
    from backend.assistify_rag_server import RAG_NO_MATCH_RESPONSE
except Exception:
    RAG_NO_MATCH_RESPONSE = "Not found in the document."

_AR_TTS_DIGIT_MAP = {
    '0': 'صِفر', '1': 'واحِد', '2': 'اثنان', '3': 'ثلاثة',
    '4': 'أربعة', '5': 'خمسة', '6': 'ستة', '7': 'سبعة',
    '8': 'ثمانية', '9': 'تسعة',
}

'''
    (VOICE / "tts" / "text_utils.py").write_text(
        text_utils_header + xform_tts(text_utils_body), encoding="utf-8"
    )
    print("wrote tts/text_utils.py")

    # --- TTS streaming ---
    streaming_body = xform_tts(slice_lines(lines, 36122, 36729))
    streaming_header = '''"""WebSocket TTS streaming helpers."""
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
from backend.voice_audio.tts.client import tts_cache_get, tts_cache_key, tts_cache_put, xtts_synth_sem
from backend.voice_audio.tts.text_utils import (
    preprocess_for_tts,
    normalize_tts_chunk_cache_text,
    split_spoken_text_for_tts,
    wav_bytes_to_pcm16,
)

logger = logging.getLogger("voice_audio.tts.streaming")

'''
    (VOICE / "tts" / "streaming.py").write_text(streaming_header + streaming_body, encoding="utf-8")
    print("wrote tts/streaming.py")

    # --- TTS client ---
    client_body = xform_tts(slice_lines(lines, 43185, 43293))
    client_header = '''"""Piper/XTTS HTTP client, cache, and synthesis."""
from __future__ import annotations

import asyncio
import collections
import hashlib
import logging
import time
from typing import Optional

import aiohttp
from fastapi import HTTPException

from backend.voice_audio.config import XTTS_SERVICE_URL

logger = logging.getLogger("voice_audio.tts.client")

xtts_synth_sem = asyncio.Semaphore(1)
xtts_inflight: dict = {}
xtts_cache: "collections.OrderedDict[str, bytes]" = collections.OrderedDict()
XTTS_CACHE_MAX_ENTRIES = 64
XTTS_CACHE_MAX_BYTES_PER_ENTRY = 2 * 1024 * 1024
xtts_cache_lock = asyncio.Lock()

'''
    (VOICE / "tts" / "client.py").write_text(client_header + client_body, encoding="utf-8")
    print("wrote tts/client.py")

    # --- TTS routes ---
    routes_body = slice_lines(lines, 43295, 43386)
    routes_body = routes_body.replace("class TTSRequest", "class TTSRequest")
    routes_body = routes_body.replace("@app.post", "@router.post")
    routes_body = routes_body.replace("_xtts_synthesize_full", "xtts_synthesize_full")
    routes_body = routes_body.replace("XTTS_SPEAKER", "config.XTTS_SPEAKER")
    routes_body = routes_body.replace("XTTS_LANGUAGE", "config.XTTS_LANGUAGE")
    routes_body = routes_body.replace("XTTS_SERVICE_URL", "config.XTTS_SERVICE_URL")
    routes_header = '''"""HTTP routes for TTS proxy."""
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

'''
    (VOICE / "tts" / "routes.py").write_text(routes_header + routes_body, encoding="utf-8")
    print("wrote tts/routes.py")

    (VOICE / "tts" / "__init__.py").write_text(
        "from backend.voice_audio.tts.streaming import (\n"
        "    cancel_active_ws_tts,\n"
        "    client_tts_allowed,\n"
        "    tts_arabic_response,\n"
        "    tts_progressive_response,\n"
        "    tts_single_response,\n"
        ")\n"
        "from backend.voice_audio.tts.client import xtts_synthesize_full\n",
        encoding="utf-8",
    )

    # --- WS capture ---
    capture_body = slice_lines(lines, 908, 937)
    capture_body = capture_body.replace("append_conversation_message", "_append")
    capture_body = capture_body.replace("persist_runtime_memory", "_persist")
    capture_header = '''"""WebSocket wrapper that persists assistant messages."""
from __future__ import annotations

from typing import Callable, Optional

from fastapi import WebSocket


class ConversationCaptureWebSocket:
    def __init__(
        self,
        websocket: WebSocket,
        conversation_id: str,
        runtime_id: str,
        append_message: Callable,
        persist_memory: Callable,
    ):
        self._websocket = websocket
        self._conversation_id = conversation_id
        self._runtime_id = runtime_id
        self._assistant_saved = False
        self._append = append_message
        self._persist = persist_memory

'''
    # rewrite capture class body manually
    (VOICE / "ws" / "capture.py").write_text('''"""WebSocket wrapper that persists assistant messages."""
from __future__ import annotations

from typing import Callable

from fastapi import WebSocket


class ConversationCaptureWebSocket:
    def __init__(
        self,
        websocket: WebSocket,
        conversation_id: str,
        runtime_id: str,
        append_message: Callable,
        persist_memory: Callable,
    ):
        self._websocket = websocket
        self._conversation_id = conversation_id
        self._runtime_id = runtime_id
        self._assistant_saved = False
        self._append = append_message
        self._persist = persist_memory

    async def send_json(self, payload):
        if isinstance(payload, dict):
            payload.setdefault("conversation_id", self._conversation_id)
        await self._websocket.send_json(payload)
        if (
            isinstance(payload, dict)
            and payload.get("type") == "aiResponseDone"
            and not self._assistant_saved
        ):
            assistant_text = str(payload.get("fullText") or payload.get("text") or "").strip()
            if assistant_text:
                try:
                    self._append(self._conversation_id, "assistant", assistant_text)
                    self._assistant_saved = True
                except Exception:
                    pass
            self._persist(self._runtime_id, self._conversation_id)

    async def send_bytes(self, data):
        await self._websocket.send_bytes(data)

    def __getattr__(self, name: str):
        return getattr(self._websocket, name)
''', encoding="utf-8")
    print("wrote ws/capture.py")

    print("Part 2 TTS modules written. Run part 3 for WS handler + main patch.")


if __name__ == "__main__":
    main()
