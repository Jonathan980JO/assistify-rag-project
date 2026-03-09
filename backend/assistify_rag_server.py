import os
import uuid
import json
import asyncio
import logging
import sqlite3
from pathlib import Path
from collections import defaultdict

# Suppress HuggingFace symlink warning on Windows
os.environ.setdefault('HF_HUB_DISABLE_SYMLINKS_WARNING', '1')
# Disable chromadb telemetry BEFORE any chromadb import (must be at module top)
os.environ['ANONYMIZED_TELEMETRY'] = 'False'
os.environ['CHROMA_TELEMETRY_IMPL'] = 'none'
# Silence posthog logger so telemetry errors don't pollute logs
logging.getLogger('chromadb.telemetry.product.posthog').setLevel(logging.CRITICAL)

# Ensure posthog.capture compatibility (stub if needed) to avoid telemetry exceptions
try:
    import posthog
    def _safe_capture(*a, **k):
        try:
            return posthog.capture(*a, **k)
        except Exception:
            return None
    posthog.capture = _safe_capture
except Exception:
    import sys
    class _PosthogStub:
        @staticmethod
        def capture(*a, **k):
            return None
        @staticmethod
        def identify(*a, **k):
            return None
    sys.modules['posthog'] = _PosthogStub()
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException, status, Request, UploadFile, File
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse, Response, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from passlib.context import CryptContext
from itsdangerous import URLSafeSerializer
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel
from typing import Optional, TYPE_CHECKING

import io
import wave
import aiohttp
import torch
import time
import numpy as np
import psutil
import traceback

# Import TOON for token-efficient RAG context
from backend.toon import format_rag_context_toon, compare_token_efficiency

# ========== SPEECH RECOGNITION: faster-whisper (GPU required) ==========
try:
    from faster_whisper import WhisperModel
    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False
    WhisperModel = None

if TYPE_CHECKING:
    # Provide WhisperModel to type-checkers only. At runtime the name may be None
    from faster_whisper import WhisperModel as _WhisperModel

# ========== TEXT-TO-SPEECH: XTTS v2 Microservice (assistify_xtts env) ==========
# XTTS v2 runs as a separate process in its own conda environment to avoid
# dependency conflicts (transformers 4.40.x vs 4.49.x, TTS 0.22.0 vs none).
# This server proxies /tts requests to the microservice on port 5002.
XTTS_SERVICE_URL = os.environ.get("XTTS_SERVICE_URL", "http://127.0.0.1:5002")
XTTS_SPEAKER     = "Claribel Dervla"
XTTS_LANGUAGE    = "en"
XTTS_SAMPLE_RATE = 24000
# Not used directly here but kept for backward compatibility
XTTS_MODEL_NAME  = "tts_models/multilingual/multi-dataset/xtts_v2"
XTTS_AVAILABLE   = True  # Assumed available; checked at request time via /health

# Centralized configuration
try:
    from config import (
        WHISPER_MODEL_PATH, WHISPER_MODEL_SIZE, WHISPER_DEVICE, 
        WHISPER_COMPUTE_TYPE, WHISPER_BEAM_SIZE, WHISPER_VAD_FILTER,
        LLM_URL, ASSETS_DIR, SESSION_SECRET, SESSION_COOKIE, 
        ANALYTICS_DB, DEVELOPMENT,
        OLLAMA_HOST, OLLAMA_PORT, OLLAMA_MODEL
    )
except Exception:
    # Fallbacks if config isn't importable
    from pathlib import Path as _P
    WHISPER_MODEL_PATH = _P(__file__).resolve().parent / "Models" / "faster-whisper-medium.en"
    WHISPER_MODEL_SIZE = "medium.en"
    WHISPER_DEVICE = "cuda"
    WHISPER_COMPUTE_TYPE = "float16"
    WHISPER_BEAM_SIZE = 5
    WHISPER_VAD_FILTER = True
    LLM_URL = "http://127.0.0.1:11434/v1/chat/completions"
    ASSETS_DIR = _P(__file__).resolve().parent / "assets"
    SESSION_SECRET = "X!3p7#9v@Yqe*rQ6CwZ8l&FbM%tUJdfPsoH1XEaN"
    SESSION_COOKIE = "session"
    ANALYTICS_DB = _P(__file__).resolve().parent / "analytics.db"
    DEVELOPMENT = True
    OLLAMA_HOST = "127.0.0.1"
    OLLAMA_PORT = 11434
    OLLAMA_MODEL = "qwen2.5:3b"

from backend.knowledge_base import search_documents, add_document, chunk_and_add_document, delete_document, delete_documents_with_prefix, delete_documents_by_filename, update_document, find_base_doc_id_by_filename, list_uploaded_files
from backend.database import init_database, save_conversation, start_session, end_session, get_stats
from backend.analytics import init_analytics_db, log_usage, log_kb_event, get_kb_stats, get_kb_events
from backend.response_validator import validate_response

# ========== CONFIGURATION ==========
SAMPLE_RATE = 16000

# Ollama direct URL — all LLM calls go here, main_llm_server.py is NOT used
OLLAMA_API_URL = f"http://{OLLAMA_HOST}:{OLLAMA_PORT}/api/chat"

# Track interrupt events per connection for barge-in support
interrupt_events = {}
# Per-connection WebSocket write lock — prevents concurrent send() calls from
# call_llm_streaming and _tts_arabic_response background tasks crashing the socket.
_ws_write_locks: dict[str, asyncio.Lock] = {}

# ========== STABILIZATION: Concurrency + Resource Guards ==========
# Semaphore(1) = only ONE voice pipeline at a time (Part 2)
voice_semaphore = asyncio.Semaphore(1)
# Track the currently-active voice task so we can cancel it on new session
_active_voice_task: asyncio.Task | None = None
_active_voice_conn_id: str | None = None

# Memory tracking across runs (Part 7)
_pipeline_run_count = 0
_last_gpu_reserved_mb = 0.0
_consecutive_gpu_growth = 0          # how many sessions in a row GPU grew >50MB
_consecutive_cpu_growth = 0          # how many sessions in a row CPU grew >100MB
_sessions_blocked = False             # True → refuse new voice sessions
MEMORY_GROWTH_LIMIT = 3              # abort after this many consecutive growth sessions

def _get_memory_snapshot() -> dict:
    """Return current GPU + CPU memory stats for logging."""
    snapshot = {
        "cpu_rss_mb": psutil.Process().memory_info().rss / 1024**2,
        "gpu_reserved_mb": 0.0,
        "gpu_allocated_mb": 0.0,
    }
    if torch.cuda.is_available():
        snapshot["gpu_reserved_mb"] = torch.cuda.memory_reserved(0) / 1024**2
        snapshot["gpu_allocated_mb"] = torch.cuda.memory_allocated(0) / 1024**2
    return snapshot

# ========== SYSTEM PREFLIGHT CHECK ==========
def _system_preflight() -> dict:
    """Verify system config matches strict stability rules. Returns dict of checks."""
    checks = {}
    checks["stt_model"] = WHISPER_MODEL_SIZE
    checks["stt_device"] = WHISPER_DEVICE
    checks["stt_compute"] = WHISPER_COMPUTE_TYPE
    checks["stt_beam"] = WHISPER_BEAM_SIZE
    checks["ollama_streaming"] = True   # hardcoded in payload
    checks["reload_disabled"] = True    # hardcoded in __main__
    checks["semaphore_limit"] = 1
    checks["silence_chunks"] = 6
    # Validate
    ok = True
    issues = []
    if WHISPER_DEVICE != "cpu":
        ok = False; issues.append(f"STT device should be cpu, got {WHISPER_DEVICE}")
    if WHISPER_COMPUTE_TYPE != "int8":
        ok = False; issues.append(f"STT compute should be int8, got {WHISPER_COMPUTE_TYPE}")
    if WHISPER_BEAM_SIZE != 1:
        ok = False; issues.append(f"STT beam should be 1, got {WHISPER_BEAM_SIZE}")
    checks["all_ok"] = ok
    checks["issues"] = issues
    return checks

serializer = URLSafeSerializer(SESSION_SECRET)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Assistify")

# ========== CONVERSATION MEMORY ==========
conversation_history = defaultdict(list)
MAX_CONVERSATIONS = 1000  # Maximum number of conversations to keep in memory
MAX_CONVERSATION_AGE = 3600  # Maximum age of conversation in seconds (1 hour)
conversation_timestamps = {}  # Track last activity time for cleanup

def cleanup_old_conversations():
    """Remove old conversations to prevent memory leak."""
    import time
    current_time = time.time()
    expired_ids = [
        conn_id for conn_id, last_time in conversation_timestamps.items()
        if current_time - last_time > MAX_CONVERSATION_AGE
    ]
    for conn_id in expired_ids:
        if conn_id in conversation_history:
            del conversation_history[conn_id]
        del conversation_timestamps[conn_id]


def clear_all_conversation_history():
    """Wipe every in-memory conversation so stale KB answers are never reused.

    Called automatically after a KB reindex to prevent the LLM from seeing
    old Q&A pairs that contradict the updated knowledge base.
    """
    count = len(conversation_history)
    conversation_history.clear()
    conversation_timestamps.clear()
    if count:
        logger.info(f"Cleared {count} conversation(s) after KB reindex")


async def flush_ollama_cache():
    """Unload the Ollama model from GPU memory to flush its internal KV cache.

    Ollama caches the model + KV state in VRAM.  After a KB change the old
    cached context can cause the LLM to repeat stale answers even though the
    RAG context is fresh.  Sending keep_alive=0 forces Ollama to unload the
    model; it will be reloaded automatically on the next query with a clean
    KV cache.
    """
    try:
        import aiohttp as _aiohttp
        ollama_url = f"http://{OLLAMA_HOST}:{OLLAMA_PORT}/api/chat"
        payload = {
            "model": OLLAMA_MODEL,
            "messages": [],
            "keep_alive": "0"
        }
        async with _aiohttp.ClientSession() as _sess:
            async with _sess.post(ollama_url, json=payload, timeout=_aiohttp.ClientTimeout(total=10)) as resp:
                logger.info(f"Ollama cache flush: status={resp.status} (model will reload on next query)")
    except Exception as e:
        logger.warning(f"Ollama cache flush failed (non-fatal): {e}")


# ========== REAL-TIME KB EVENT BROADCAST ==========
# All active user WebSocket connections (keyed by connection_id → WebSocket)
_active_ws_connections: dict = {}
# Admin KB-events subscribers (connected to /ws/kb-events)
_kb_event_subscribers: set = set()
# Global KB version counter — incremented on every mutation
_kb_global_version: int = 0


async def broadcast_kb_event(action: str, filename: str = "*",
                              chunks_added: int = 0, chunks_deleted: int = 0,
                              triggered_by: str = "admin"):
    """Broadcast a KB mutation event to all connected sockets.

    Sends:
      - A ``kb_updated`` message to every active user chat session so the
        frontend can show a "new information available" notice.
      - The full event payload to every admin KB-events subscriber.
    """
    global _kb_global_version
    _kb_global_version += 1
    event = {
        "type": "kb_updated",
        "action": action,
        "filename": filename,
        "chunks_added": chunks_added,
        "chunks_deleted": chunks_deleted,
        "kb_version": _kb_global_version,
        "triggered_by": triggered_by,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    # Persist the event to the analytics DB
    log_kb_event(
        action=action,
        filename=filename,
        chunks_added=chunks_added,
        chunks_deleted=chunks_deleted,
        kb_version=_kb_global_version,
        triggered_by=triggered_by,
    )

    # Notify every active user session (chat WebSocket)
    dead_conns = []
    for conn_id, ws in list(_active_ws_connections.items()):
        try:
            await ws.send_json({
                "type": "kb_updated",
                "message": "Knowledge base was updated — your next reply will use the latest information.",
                "kb_version": _kb_global_version,
                "timestamp": event["timestamp"],
            })
        except Exception:
            dead_conns.append(conn_id)
    for conn_id in dead_conns:
        _active_ws_connections.pop(conn_id, None)

    # Broadcast full event to admin KB-events subscribers
    dead_subs = []
    for ws in list(_kb_event_subscribers):
        try:
            await ws.send_json(event)
        except Exception:
            dead_subs.append(ws)
    for ws in dead_subs:
        _kb_event_subscribers.discard(ws)

    logger.info(f"KB broadcast: action={action} file={filename} v{_kb_global_version} "
                f"→ {len(_active_ws_connections)} user sessions, "
                f"{len(_kb_event_subscribers)} admin subscribers")


async def invalidate_all_caches(action: str = "cache_clear", filename: str = "*",
                                 chunks_added: int = 0, chunks_deleted: int = 0,
                                 triggered_by: str = "admin"):
    """Nuclear option: clear conversation history + flush Ollama KV cache + broadcast.

    Call this after any KB mutation (upload, edit, delete, reindex) to
    guarantee the next user query gets a fully fresh answer.
    """
    clear_all_conversation_history()
    await flush_ollama_cache()
    await broadcast_kb_event(action=action, filename=filename,
                              chunks_added=chunks_added, chunks_deleted=chunks_deleted,
                              triggered_by=triggered_by)
    logger.info("All caches invalidated (conversations + Ollama KV cache)")

# ========== ANALYTICS DB ==========
ANALYTICS_DB = str(ANALYTICS_DB)

# ========== FASTAPI APP INSTANCE (must come before decorators) ==========
app = FastAPI(title="Assistify RAG Voice Engine")

# Global aiohttp session for LLM requests (reuse connections)
llm_session: aiohttp.ClientSession = None

# Global aiohttp session for TTS requests (reuse connections, avoids TCP
# handshake overhead on every query)
tts_session: aiohttp.ClientSession = None

# Global faster-whisper model (typing-safe forward reference)
whisper_model: Optional['_WhisperModel'] = None
# Multilingual faster-whisper model — loaded at startup when present, used for Arabic STT
whisper_model_multilingual: Optional['_WhisperModel'] = None

# Path to multilingual model (sibling of english model dir)
# "small" (~244M) is used — fast enough on GPU (<0.5s) and much lighter than "medium" on CPU
_MULTILINGUAL_MODEL_PATH = Path(WHISPER_MODEL_PATH).parent / "faster-whisper-small"

# XTTS v2 is now a separate microservice — no local model held in this process
xtts_model = None  # kept for status endpoint backward compat

# Pre-rendered Arabic acknowledgment PCM audio (populated at startup via XTTS).
# Streamed immediately when an Arabic query arrives so the user hears audio
# within ~1 second while the actual answer is still being generated.
_arabic_ack_pcm: bytes = b""

@app.on_event("startup")
async def startup_event():
    global llm_session, tts_session, whisper_model, whisper_model_multilingual, xtts_model, WHISPER_DEVICE, WHISPER_COMPUTE_TYPE
    
    init_database()
    init_analytics_db()
    
    # Create persistent session for LLM requests with connection pooling
    connector = aiohttp.TCPConnector(
        limit=10,
        limit_per_host=5,
        ttl_dns_cache=300,
        force_close=False,
        enable_cleanup_closed=True
    )
    timeout = aiohttp.ClientTimeout(total=30, connect=5, sock_read=10)
    llm_session = aiohttp.ClientSession(
        connector=connector,
        timeout=timeout,
        headers={'Connection': 'keep-alive'}
    )

    # Create persistent session for TTS requests — avoids TCP handshake on
    # every query (XTTS microservice on localhost:5002).
    tts_connector = aiohttp.TCPConnector(
        limit=4,
        limit_per_host=2,
        force_close=False,
        enable_cleanup_closed=True,
    )
    tts_session = aiohttp.ClientSession(
        connector=tts_connector,
        timeout=aiohttp.ClientTimeout(total=None, sock_connect=5, sock_read=None),
        headers={'Connection': 'keep-alive'},
    )

    logger.info("✓ Databases ready")
    logger.info("✓ Persistent LLM session created with connection pooling")
    logger.info("✓ Persistent TTS session created")
    
    # Initialize faster-whisper (GPU required)
    if not WHISPER_AVAILABLE:
        error_msg = "CRITICAL: faster-whisper not installed. Install with: pip install faster-whisper"
        logger.error(error_msg)
        raise ImportError(error_msg)
    
    if not torch.cuda.is_available() and WHISPER_DEVICE == "cuda":
        logger.warning("CUDA not available for faster-whisper — falling back to CPU with int8 compute.")
        # Override device/compute to CPU-compatible values so the server can still start
        WHISPER_DEVICE = "cpu"
        WHISPER_COMPUTE_TYPE = "int8"
    
    logger.info(f"Loading faster-whisper model '{WHISPER_MODEL_SIZE}' on {WHISPER_DEVICE}...")
    logger.info(f"Model path: {WHISPER_MODEL_PATH}")
    
    try:
        # Load model from local directory
        if WHISPER_MODEL_PATH.exists():
            logger.info(f"Using local model from: {WHISPER_MODEL_PATH}")
            whisper_model = WhisperModel(
                str(WHISPER_MODEL_PATH),
                device=WHISPER_DEVICE,
                compute_type=WHISPER_COMPUTE_TYPE,
                download_root=None  # Don't download, use local only
            )
        else:
            # Download model to specified directory
            logger.info(f"Downloading model '{WHISPER_MODEL_SIZE}' to: {WHISPER_MODEL_PATH}")
            WHISPER_MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
            whisper_model = WhisperModel(
                WHISPER_MODEL_SIZE,
                device=WHISPER_DEVICE,
                compute_type=WHISPER_COMPUTE_TYPE,
                download_root=str(WHISPER_MODEL_PATH.parent)
            )
        
        logger.info(f"✓ faster-whisper loaded successfully")
        logger.info(f"  Device: {WHISPER_DEVICE}")
        logger.info(f"  Compute type: {WHISPER_COMPUTE_TYPE}")
        logger.info(f"  Beam size: {WHISPER_BEAM_SIZE}")
        logger.info(f"  VAD filter: {WHISPER_VAD_FILTER}")
        
    except Exception as e:
        error_msg = f"CRITICAL: Failed to load faster-whisper: {e}"
        logger.error(error_msg)
        raise RuntimeError(error_msg)

    # XTTS v2 runs as a separate microservice — check it is reachable
    import urllib.request
    try:
        req = urllib.request.urlopen(f"{XTTS_SERVICE_URL}/health", timeout=5)
        health = req.read().decode()
        logger.info(f"XTTS microservice reachable: {health[:80]}")
        xtts_model = True  # acts as a flag — True means service is up
    except Exception as e:
        logger.warning(f"XTTS microservice not reachable at {XTTS_SERVICE_URL} — TTS unavailable. "
                       f"Start it with: start_xtts_service.bat  ({e})")
        xtts_model = None

    # ---- Try to load multilingual faster-whisper model for Arabic STT ----
    # Resolution order:
    #   1. Direct folder  (faster-whisper-small/)        ← created by /arabic/download or manual placement
    #   2. HF cache folder (models--Systran--faster-whisper-small/snapshots/<hash>/)  ← already present if
    #      the model was previously downloaded via huggingface_hub
    def _find_ml_model_path() -> Path | None:
        """Return the best available multilingual model path, or None."""
        # 1. Direct folder
        if _MULTILINGUAL_MODEL_PATH.exists() and any(_MULTILINGUAL_MODEL_PATH.iterdir()):
            return _MULTILINGUAL_MODEL_PATH
        # 2. HF cache format: Models/models--Systran--faster-whisper-small/snapshots/<hash>/
        _hf_cache = _MULTILINGUAL_MODEL_PATH.parent / "models--Systran--faster-whisper-small" / "snapshots"
        if _hf_cache.exists():
            _snaps = sorted(_hf_cache.iterdir())
            if _snaps:
                return _snaps[-1]   # latest snapshot
        return None

    _ml_resolved = _find_ml_model_path()
    if _ml_resolved:
        logger.info(f"Multilingual faster-whisper model found at {_ml_resolved} — loading for Arabic STT...")
        try:
            # Prefer GPU for multilingual model: drops Arabic STT from ~6s → ~0.3s
            _ml_device  = "cuda" if torch.cuda.is_available() else "cpu"
            _ml_compute = "float16" if _ml_device == "cuda" else "int8"
            _ml_kwargs: dict = {"device": _ml_device, "compute_type": _ml_compute, "download_root": None}
            if _ml_device == "cpu":
                import os as _os
                _cpu_threads = int(_os.getenv("WHISPER_CPU_THREADS", str(min(_os.cpu_count() or 4, 8))))
                _ml_kwargs.update({"cpu_threads": _cpu_threads, "num_workers": 1})
            whisper_model_multilingual = WhisperModel(str(_ml_resolved), **_ml_kwargs)
            logger.info(f"✓ Multilingual faster-whisper loaded (Arabic STT ready, device={_ml_device}, compute={_ml_compute})")
        except Exception as _ml_e:
            logger.warning(f"Multilingual model found but failed to load: {_ml_e} — Arabic STT will use English model as fallback")
    else:
        logger.info(f"Multilingual faster-whisper not found at {_MULTILINGUAL_MODEL_PATH} — Arabic STT download available via /arabic/download")

    # Fire-and-forget warmups — run in the background, invisible to users
    asyncio.create_task(_warmup_llm())
    asyncio.create_task(_warmup_xtts())

    # Assets watcher: prefer watchdog (OS events) for instant reindexing,
    # fallback to the polling watcher if watchdog isn't installed.
    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler

        class _AssetsHandler(FileSystemEventHandler):
            def on_created(self, event):
                if event.is_directory:
                    return
                try:
                    fname = Path(event.src_path).name
                    asyncio.get_event_loop().call_soon_threadsafe(
                        lambda: asyncio.create_task(_reindex_file_auto(fname))
                    )
                except Exception:
                    logger.exception("Assets handler on_created error")

            def on_modified(self, event):
                if event.is_directory:
                    return
                try:
                    fname = Path(event.src_path).name
                    asyncio.get_event_loop().call_soon_threadsafe(
                        lambda: asyncio.create_task(_reindex_file_auto(fname))
                    )
                except Exception:
                    logger.exception("Assets handler on_modified error")

        observer = Observer()
        observer.schedule(_AssetsHandler(), str(ASSETS_DIR), recursive=False)
        observer.daemon = True
        observer.start()
        app.state.assets_observer = observer
        logger.info("Assets watchdog started (watchdog installed)")
    except Exception:
        logger.info("watchdog not available — using polling assets watcher")
        asyncio.create_task(_assets_watcher())

async def _warmup_llm():
    """
    Background task: preload the Ollama model into VRAM on startup.

    Uses the official Ollama preload method: POST /api/generate with no
    prompt and keep_alive: -1.  This loads the model weights into GPU
    memory and tells Ollama to NEVER evict them, so every user query
    gets a fast first token instead of waiting 8+ seconds for a cold load.
    """
    await asyncio.sleep(3)          # let server finish binding first
    OLLAMA_BASE = f"http://{OLLAMA_HOST}:{OLLAMA_PORT}"
    preload_url = f"{OLLAMA_BASE}/api/generate"
    logger.info(f"[Warmup] Preloading {OLLAMA_MODEL} into VRAM (keep_alive=-1)...")
    payload = {
        "model": OLLAMA_MODEL,
        "keep_alive": -1,   # never evict from VRAM
        # No 'prompt' key — this is the official Ollama preload pattern.
        # Ollama loads the model and returns immediately without generating tokens.
        # IMPORTANT: num_ctx must match chat requests exactly, otherwise Ollama
        # reloads the model on every chat call (causing 8-second cold-start delays).
        "options": {
            "num_ctx": 2048,
            "num_gpu": 99,
        },
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                preload_url,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=120),
            ) as resp:
                if resp.status == 200:
                    logger.info(f"[Warmup] ✓ {OLLAMA_MODEL} loaded into VRAM | keep_alive=forever")
                else:
                    text = await resp.text()
                    logger.warning(f"[Warmup] Ollama preload returned {resp.status}: {text[:120]}")
    except Exception as e:
        logger.warning(f"[Warmup] LLM preload failed (Ollama may not be running yet): {e}")


async def _warmup_xtts():
    """Background task: warm up the XTTS model and pre-render the Arabic
    acknowledgment phrase so it can be streamed instantly on the first Arabic query.
    """
    global _arabic_ack_pcm
    await asyncio.sleep(10)  # let the XTTS service finish initializing
    logger.info(f"[Warmup] Sending TTS warmup request to {XTTS_SERVICE_URL}...")
    try:
        async with aiohttp.ClientSession() as session:
            # -- English warmup (keeps existing behaviour) --
            async with session.post(
                f"{XTTS_SERVICE_URL}/synthesize",
                json={"text": "test", "speaker": XTTS_SPEAKER, "language": XTTS_LANGUAGE},
                timeout=aiohttp.ClientTimeout(total=60),
            ) as resp:
                if resp.status == 200:
                    await resp.read()
                    logger.info("[Warmup] ✓ XTTS model warmed up")
                else:
                    text = await resp.text()
                    logger.warning(f"[Warmup] XTTS warmup returned {resp.status}: {text[:120]}")

            # -- Arabic acknowledgment pre-render --
            # Synthesize a short phrase and cache the raw PCM (skip the 44-byte WAV header).
            # This audio will be streamed to the client immediately when any Arabic
            # query arrives, giving <1s perceived first-audio latency.
            _ACK_PHRASE = "حسناً"
            try:
                async with session.post(
                    f"{XTTS_SERVICE_URL}/synthesize",
                    json={"text": _ACK_PHRASE, "speaker": XTTS_SPEAKER, "language": "ar"},
                    timeout=aiohttp.ClientTimeout(total=60),
                ) as ar_resp:
                    if ar_resp.status == 200:
                        wav_bytes = await ar_resp.read()
                        # Strip the 44-byte WAV header to get raw PCM16
                        _arabic_ack_pcm = wav_bytes[44:] if len(wav_bytes) > 44 else wav_bytes
                        logger.info(f"[Warmup] ✓ Arabic acknowledgment audio cached ({len(_arabic_ack_pcm):,} bytes PCM)")
                    else:
                        logger.warning("[Warmup] Arabic ack pre-render failed — acknowledgment audio disabled")
            except Exception as e_ar:
                logger.warning(f"[Warmup] Arabic ack pre-render error: {e_ar}")
    except Exception as e:
        logger.warning(f"[Warmup] XTTS warmup failed (service may not be running): {e}")


@app.on_event("shutdown")
async def shutdown_event():
    global llm_session, tts_session
    if llm_session and not llm_session.closed:
        await llm_session.close()
        logger.info("✓ LLM session closed")
    if tts_session and not tts_session.closed:
        await tts_session.close()
        logger.info("✓ TTS session closed")

logger.info("Initializing Assistify RAG System with faster-whisper...")


async def _reindex_file_auto(filename: str):
    """Background helper to reindex a file by filename.

    Uses delete_documents_by_filename() to wipe ALL previous chunks for this
    file (including any orphaned chunks with a different doc_id prefix created
    during earlier buggy runs), then re-indexes with a stable doc_id.
    Verifies the new content is searchable after write.
    """
    try:
        save_path = ASSETS_DIR / filename
        if not save_path.exists():
            logger.warning(f"Assets watcher: file disappeared before reindex: {filename}")
            return
        content = save_path.read_bytes()
        try:
            text = content.decode("utf-8")
        except Exception:
            text = content.decode(errors="ignore")

        if not text.strip():
            logger.info(f"Assets watcher: skipping empty file: {filename}")
            return

        # ---- STEP 1: delete ALL existing chunks for this filename ----
        deleted = delete_documents_by_filename(filename)
        logger.info(f"Assets watcher [{filename}]: deleted {deleted} old chunk(s)")

        # ---- STEP 2: build a stable doc_id from the filename itself ----
        # We do NOT reuse a DB-derived doc_id because we just deleted everything.
        # Using a deterministic prefix based on the filename makes future deletes
        # reliable even across server restarts.
        import re as _re
        bare = _re.sub(r'^[0-9a-fA-F]{8}_', '', filename)  # strip UUID prefix if any
        safe = _re.sub(r'[^A-Za-z0-9._-]', '_', bare)
        doc_id = f"upload_{safe}"
        metadata = {"source": "upload", "filename": filename}

        added = chunk_and_add_document(doc_id=doc_id, text=text, metadata=metadata,
                                        kb_version=_kb_global_version + 1)
        logger.info(f"Assets watcher [{filename}]: indexed {added} new chunk(s) (doc_id={doc_id})")

        # ---- STEP 3: invalidate all caches + broadcast KB event ----
        await invalidate_all_caches(action="reindex", filename=filename,
                                     chunks_added=added, chunks_deleted=deleted,
                                     triggered_by="watcher")

        # ---- STEP 4: verify the new content is searchable ----
        first_line = text.strip().split('\n')[0][:80]
        verify = search_documents(first_line, top_k=1, distance_threshold=1.5)
        if verify:
            logger.info(f"Assets watcher [{filename}]: ✓ verification OK — search returns: {verify[0][:60]}...")
        else:
            logger.warning(f"Assets watcher [{filename}]: ✗ verification FAILED — search returned nothing for: {first_line}")
    except Exception as e:
        logger.exception(f"Assets watcher reindex failed for {filename}: {e}")


async def _assets_watcher(poll_interval: float = 5.0):
    """Simple polling watcher for the ASSETS_DIR; reindexes changed/new files.

    On the FIRST scan we only record mtimes — we do NOT reindex because the DB
    already contains the data from the original upload.  We only reindex when a
    file is genuinely modified AFTER the server started (mtime changed) or when
    a brand-new file appears that was not present during the first scan.
    """
    logger.info("Assets watcher started (polling every %.1fs)", poll_interval)
    seen: dict[str, float] = {}
    first_scan_done = False
    try:
        while True:
            try:
                if not ASSETS_DIR.exists():
                    await asyncio.sleep(poll_interval)
                    continue
                for p in ASSETS_DIR.iterdir():
                    if not p.is_file():
                        continue
                    if p.suffix.lower() not in (".txt", ".pdf"):
                        continue
                    mtime = p.stat().st_mtime
                    key = str(p.name)
                    prev = seen.get(key)

                    if not first_scan_done:
                        # First scan: just record mtime, don't reindex
                        seen[key] = mtime
                    elif prev is None:
                        # New file added after server started
                        seen[key] = mtime
                        logger.info("Assets watcher: new file detected: %s — reindexing", key)
                        asyncio.create_task(_reindex_file_auto(key))
                    elif mtime != prev:
                        # Existing file was modified
                        seen[key] = mtime
                        logger.info("Assets watcher: file modified: %s — reindexing", key)
                        asyncio.create_task(_reindex_file_auto(key))

                if not first_scan_done:
                    first_scan_done = True
                    logger.info("Assets watcher: initial scan done — tracking %d file(s)", len(seen))

                # Remove deleted files from seen
                for key in list(seen.keys()):
                    if not (ASSETS_DIR / key).exists():
                        logger.info("Assets watcher: file removed: %s", key)
                        del seen[key]

            except Exception as e:
                logger.exception(f"Assets watcher loop error: {e}")
            await asyncio.sleep(poll_interval)
    except asyncio.CancelledError:
        logger.info("Assets watcher cancelled; shutting down")


# The assets watcher will be started on application startup. We prefer
# using an OS-level watcher (watchdog) when available for instant events;
# otherwise the polling watcher `_assets_watcher` will be used as a fallback.

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET, https_only=(not DEVELOPMENT))
app.add_middleware(
    TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1"]
)
ASSETS_DIR = Path(ASSETS_DIR)
ASSETS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

# ========== AUTH DECORATOR ================
def require_login(role=None):
    def wrapper(request: Request):
        token = request.cookies.get(SESSION_COOKIE)
        if not token:
            raise HTTPException(status_code=401, detail="Authentication required.")
        try:
            user = serializer.loads(token)
        except Exception:
            raise HTTPException(status_code=401, detail="Invalid session.")
        if role and user.get("role") != role:
            raise HTTPException(status_code=403, detail="Forbidden.")
        return user
    return wrapper

# ========== CSRF VERIFICATION HELPER ==========
def verify_csrf(request: Request):
    csrf_header = request.headers.get("x-csrf-token")
    csrf_cookie = request.cookies.get("csrf_token")
    if not csrf_cookie or csrf_header != csrf_cookie:
        raise HTTPException(status_code=403, detail="CSRF token missing or invalid")

# ========== ARABIC LANGUAGE SUPPORT ==========

# Arabic refusal message for off-topic questions (outside Amazon/system scope)
ARABIC_OFF_TOPIC_RESPONSE = (
    "عذراً، لا أستطيع الإجابة على هذا السؤال. أنا مساعد Assistify ومتخصص فقط في خدمات Amazon "
    "والمعلومات المتعلقة بالنظام. يمكنني مساعدتك في الأسئلة المتعلقة بالخدمات والمنتجات الموجودة "
    "في قاعدة المعرفة."
)

ARABIC_GENERAL_TOPICS = frozenset([
    'مرحبا', 'مرحباً', 'أهلاً', 'اهلا', 'السلام عليكم', 'كيف حالك', 'شكراً', 'شكرا',
    'وداعاً', 'مع السلامة', 'صباح الخير', 'مساء الخير'
])

def _is_arabic_small_talk(text: str) -> bool:
    """Return True if the Arabic text is a greeting/farewell/small talk."""
    t = text.strip().lower()
    # Check against known greeting patterns
    for phrase in ARABIC_GENERAL_TOPICS:
        if phrase in t:
            return True
    # Very short messages (≤4 words) are likely greetings
    if len(t.split()) <= 4:
        return True
    return False


async def translate_with_llm(text: str, source_lang: str, target_lang: str) -> str:
    """Translate text between Arabic and English using the local LLM.

    Uses the same Ollama model already loaded in VRAM — no external API needed.
    Returns the translated text, or the original text if translation fails.
    """
    global llm_session
    lang_names = {"ar": "Arabic", "en": "English"}
    src = lang_names.get(source_lang, source_lang)
    tgt = lang_names.get(target_lang, target_lang)

    # Build a very directive prompt — small models like qwen2.5:3b need explicit task framing
    if target_lang == "ar":
        system_msg = (
            "أنت مترجم محترف. مهمتك الوحيدة هي ترجمة النص إلى اللغة العربية.\n"
            "القواعد الصارمة:\n"
            "- اكتب فقط النص العربي المترجم\n"
            "- لا تكتب أي كلمة بالإنجليزية\n"
            "- لا تضف شرحاً أو ملاحظات\n"
            "- لا تكرر النص الأصلي\n"
            "الإخراج يجب أن يكون بالعربية فقط."
        )
        user_msg = f"ترجم هذا النص إلى العربية:\n\n{text}"
    else:
        system_msg = (
            "You are a professional translator. Your only task is to translate text to English.\n"
            "Strict rules:\n"
            "- Output ONLY the English translation\n"
            "- Do NOT output any Arabic\n"
            "- Do NOT add explanations or notes\n"
            "- Do NOT repeat the original text"
        )
        user_msg = f"Translate this text to English:\n\n{text}"

    messages = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_msg},
    ]
    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        "keep_alive": -1,
        "options": {"num_ctx": 2048, "num_gpu": 99, "temperature": 0.05, "num_predict": 512},
    }
    try:
        timeout = aiohttp.ClientTimeout(total=30, connect=5, sock_read=25)
        _sess = llm_session
        if _sess is None or _sess.closed:
            _sess = aiohttp.ClientSession()
        async with _sess.post(LLM_URL, json=payload, timeout=timeout) as resp:
            if resp.status == 200:
                data = await resp.json()
                translated = data["choices"][0]["message"]["content"].strip()

                # Validate: if translating to Arabic, result must contain Arabic characters
                if target_lang == "ar":
                    arabic_char_count = sum(1 for c in translated if '\u0600' <= c <= '\u06FF')
                    if arabic_char_count < 3:
                        logger.warning(
                            f"Translation to Arabic failed — model returned non-Arabic output: '{translated[:80]}'. Retrying with stricter prompt."
                        )
                        # Retry once with an even simpler, purely Arabic system prompt
                        retry_messages = [
                            {"role": "system", "content": "مترجم. أجب بالعربية فقط. لا إنجليزية إطلاقاً."},
                            {"role": "user", "content": f"ترجم: {text}"},
                        ]
                        payload["messages"] = retry_messages
                        async with _sess.post(LLM_URL, json=payload, timeout=timeout) as resp2:
                            if resp2.status == 200:
                                data2 = await resp2.json()
                                translated = data2["choices"][0]["message"]["content"].strip()
                                arabic_char_count2 = sum(1 for c in translated if '\u0600' <= c <= '\u06FF')
                                if arabic_char_count2 < 3:
                                    logger.warning(f"Arabic translation retry also failed. Falling back to original.")
                                    return text

                logger.info(f"Translation ({src}→{tgt}): '{text[:60]}' → '{translated[:60]}'")
                return translated
    except Exception as e:
        logger.warning(f"Translation failed ({src}→{tgt}): {e}")
    return text  # Fallback: return original text


def _detect_language(text: str) -> str:
    """Heuristic language detection: returns 'ar' if Arabic chars dominate, else 'en'."""
    arabic_chars = sum(1 for c in text if '\u0600' <= c <= '\u06FF')
    return "ar" if arabic_chars > len(text) * 0.2 else "en"


# Arabic STT initial prompt — primes the Whisper decoder with domain-relevant
# vocabulary so it prefers "أبيع" (sell) over "أبي" (daddy), "يجب" over "أجب", etc.
_ARABIC_STT_INITIAL_PROMPT = (
    "لماذا يجب أن أبيع على أمازون؟ "
    "ما هو البيع على أمازون؟ "
    "كيف أبدأ البيع؟ "
    "ما الذي يمكنني بيعه في متجر أمازون؟ "
    "ما هي رسوم البيع على أمازون؟ "
    "كيف أسجل كبائع على أمازون؟"
)


# ========== HELPER: RAG+LLM ==========
async def call_llm_with_rag(text: str, connection_id: str, user):
    global llm_session
    import time
    start_time = time.time()
    
    user = user or {"username": "anon", "role": "user"}
    if not text or len(text.strip()) < 2:
        return ("I didn't catch that. Could you repeat?", [])
    
    # Update conversation timestamp for cleanup
    conversation_timestamps[connection_id] = time.time()
    
    # Cleanup old conversations periodically (every 100 requests)
    if len(conversation_history) % 100 == 0:
        cleanup_old_conversations()
    
    history = conversation_history[connection_id]
    
    # Skip RAG search for greetings only (optimization)
    greeting_patterns = ['hi', 'hello', 'hey', 'how are you', 'good morning', 'good afternoon', 'good evening', 'thanks', 'thank you']
    is_greeting = len(text.strip().split()) <= 3 and any(pattern in text.lower() for pattern in greeting_patterns)
    
    if is_greeting:
        logger.info(f"RAG: Skipping search for greeting: {text}")
        relevant_docs = []
    else:
        logger.info(f"RAG: Searching knowledge base for: {text}")
        relevant_docs = search_documents(text, top_k=3)
    
    # Build context using TOON format (40-60% token savings)
    context_block = ""
    if relevant_docs:
        doc_dicts = [
            {"page_content": doc_text, "metadata": {"doc_id": i, "type": "support_info"}}
            for i, doc_text in enumerate(relevant_docs)
        ]
        toon_context = format_rag_context_toon(doc_dicts)
        context_block = f"""

===== KNOWLEDGE BASE — OVERRIDE YOUR TRAINING DATA =====
{toon_context}
========================================================

CRITICAL RULES — YOU MUST FOLLOW THESE WITHOUT EXCEPTION:
1. Your answer MUST come ONLY from the KNOWLEDGE BASE above.
2. IGNORE everything you learned during training about this topic.
3. Even if the Knowledge Base contradicts popular knowledge, you MUST follow the Knowledge Base.
4. State the Knowledge Base facts directly and confidently as the correct answer.
5. Do NOT say "according to my knowledge" or "actually" — just state the KB facts.
6. If earlier messages in this conversation contradict the KNOWLEDGE BASE, IGNORE those earlier messages — the KNOWLEDGE BASE is always more recent and correct."""
        logger.info(f"RAG: Found {len(relevant_docs)} docs, injected as authoritative context")
    else:
        logger.info("RAG: No RAG context - using general knowledge")

    # Lower temperature when KB context is present to stop the LLM drifting
    # away from retrieved facts toward its own parametric knowledge.
    effective_temperature = 0.2 if relevant_docs else 0.6

    system_prompt = f"""You are Assistify, a helpful assistant. Keep responses under 80 words. Use short conversational sentences. Be concise — answer in 2-3 sentences maximum. Never cut off mid-sentence.{context_block}"""
    messages = [{"role": "system", "content": system_prompt}]
    # When KB context is present, skip conversation history to prevent stale
    # old answers from overriding fresh KB data.  Without KB context, keep
    # history for natural multi-turn conversation.
    if not relevant_docs:
        messages.extend(history[-10:])
    messages.append({"role": "user", "content": text.strip()})
    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "max_tokens": 180,
        "temperature": effective_temperature,
        "stream": False,
        "keep_alive": -1,       # keep model in VRAM — no cold-reload penalty
        "options": {
            "num_ctx": 2048,    # must match warmup and streaming path
            "num_gpu": 99,
            "num_predict": 180,
            "temperature": effective_temperature,
            "top_p": 0.9,
        },
    }
    username = user.get("username", "unknown")
    user_role = user.get("role", "unknown")
    query_length = len(text.strip())
    
    try:
        # Retry logic for connection errors
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # Use persistent global session with longer timeout
                timeout = aiohttp.ClientTimeout(total=60, connect=5, sock_read=45)  # Increased from 30/10
                async with llm_session.post(LLM_URL, json=payload, timeout=timeout) as response:
                    if response.status == 200:
                        data = await response.json()
                        # Check if LLM returned an error instead of a proper response
                        if "error" in data:
                            logger.error(f"LLM returned error: {data['error']}")
                            response_time = int((time.time() - start_time) * 1000)
                            log_usage(username, user_role, text, "error", f"LLM error: {data['error']}",
                                    response_time, len(relevant_docs), query_length, 0)
                            return ("I'm having trouble processing that request. Please try again.", [])
                        
                        ai_text = data["choices"][0]["message"]["content"].strip()

                        # Success - break retry loop
                        break
                    else:
                        logger.error(f"LLM HTTP {response.status}")
                        if attempt < max_retries - 1:
                            await asyncio.sleep(0.5 * (attempt + 1))
                            continue
                        return ("The AI service is temporarily unavailable. Please try again.", [])
            except (aiohttp.ClientOSError, ConnectionResetError, OSError, asyncio.TimeoutError) as conn_err:
                logger.warning(f"LLM connection error (attempt {attempt+1}/{max_retries}): {conn_err}")
                if attempt < max_retries - 1:
                    # Recreate session on connection error
                    try:
                        await llm_session.close()
                    except:
                        pass
                    connector = aiohttp.TCPConnector(
                        limit=10,
                        limit_per_host=5,
                        force_close=False
                    )
                    llm_session = aiohttp.ClientSession(
                        connector=connector,
                        headers={'Connection': 'keep-alive'}
                    )
                    await asyncio.sleep(1.0 * (attempt + 1))
                    continue
                else:
                    logger.error(f"LLM connection failed after {max_retries} attempts")
                    return ("The AI service is currently unavailable. Please try again in a moment.", [])
        
        # Validation runs after successful response
        # ========== RESPONSE VALIDATION ==========
        validation_result = validate_response(ai_text, text, relevant_docs)
        
        # If validation failed, use the safe fallback response
        if not validation_result.is_valid:
            logger.warning(f"Response validation FAILED - Severity: {validation_result.severity}")
            for issue in validation_result.issues:
                logger.warning(f"  - {issue['severity']}: {issue['message']}")
            
            # Use the modified safe response
            ai_text = validation_result.modified_response
            
            # Log validation failure
            response_time = int((time.time() - start_time) * 1000)
            log_usage(username, user_role, text, "validation_failed", 
                    f"{validation_result.severity}: {validation_result.issues[0]['message'] if validation_result.issues else 'unknown'}",
                    response_time, len(relevant_docs), query_length, len(ai_text))
        
        # If validation modified the response (e.g., added disclaimer), use modified version
        elif validation_result.modified_response:
            logger.info(f"Response modified by validation - added disclaimer")
            ai_text = validation_result.modified_response
        
        # ========== END VALIDATION ==========
        
        history.append({"role": "user", "content": text.strip()})
        history.append({"role": "assistant", "content": ai_text})
        
        response_time = int((time.time() - start_time) * 1000)
        response_length = len(ai_text)
        
        # Log TOON token savings
        if relevant_docs and len(doc_dicts) > 0:
            # Compare token efficiency (JSON vs TOON)
            sample_doc = doc_dicts[0]
            savings_stats = compare_token_efficiency(sample_doc)
            logger.info(f"TOON: Saved ~{savings_stats['token_savings_pct']}% tokens vs JSON in RAG context")
        
        # Only log success if validation passed
        if validation_result.is_valid:
            log_usage(username, user_role, text, "success", None,
                    response_time, len(relevant_docs), query_length, response_length)
        
        logger.info(f"RAG: Generated response ({len(ai_text)} chars) in {response_time}ms")
        return (ai_text, relevant_docs)
    
    except asyncio.TimeoutError:
        response_time = int((time.time() - start_time) * 1000)
        log_usage(username, user_role, text, "error", "TimeoutError",
                response_time, len(relevant_docs), query_length, 0)
        logger.error(f"LLM timeout for query: {text[:50]}")
        return ("I'm processing your question. Give me a moment.", [])
    except Exception as e:
        response_time = int((time.time() - start_time) * 1000)
        log_usage(username, user_role, text, "error", str(e),
                response_time, len(relevant_docs), query_length, 0)
        logger.exception(f"LLM error for query '{text[:50]}': {e}")
        return ("Sorry, I encountered an issue. Let's continue.", [])


# ========== STREAMING LLM FOR REAL-TIME SENTENCE TTS ==========
import re as _re
_sentence_end_pattern = _re.compile(r'(?<=[.!?])\s+')

# ---------------------------------------------------------------------------
# TTS text-quality helper: digit normalization only
# ---------------------------------------------------------------------------

def _normalize_digits_for_tts(text: str) -> str:
    """Merge space-separated single-digit tokens into whole numbers,
    reassemble spaced decimal points, and attach currency symbols.

    Examples::

        "4 6 7 goals"     → "467 goals"
        "$ 3 9 . 9 9"     → "$39.99"
        "$ 0 . 9 9"       → "$0.99"
        "3 9 . 9 9 /month" → "39.99 /month"
        "2 1 3"           → "213"

    Applied only to text sent to XTTS — NOT to the displayed chat response.
    """
    # 1) Merge isolated single-digit sequences: "3 9" → "39"
    text = _re.sub(
        r'\b(\d)\b(?: \b(\d)\b)+',
        lambda m: m.group(0).replace(' ', ''),
        text,
    )
    # 2) Merge spaced decimal points: "39 . 99" → "39.99"
    text = _re.sub(r'(\d) ?\. ?(\d)', r'\1.\2', text)
    # 3) Attach currency symbol to following number: "$ 39.99" → "$39.99"
    text = _re.sub(r'\$\s+(\d)', r'$\1', text)
    return text


# Adaptive TTS chunk sizing — adjusts words-per-chunk based on real-time perf
from backend.adaptive_chunk_manager import adaptive_manager, chunk_text_by_words


async def _tts_arabic_response(
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
    _lock = _ws_write_locks.get(connection_id) or asyncio.Lock()

    async def _ws_send_json(payload):
        async with _lock:
            await websocket.send_json(payload)

    async def _ws_send_bytes(data):
        async with _lock:
            await websocket.send_bytes(data)

    first_chunk_time: float = None
    chunk_count: int = 0
    total_time: float = 0.0

    try:
        _sess = tts_session
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


async def call_llm_streaming(websocket: WebSocket, text: str, connection_id: str, user, cancel_event: asyncio.Event = None, t_meta=None, language: str = "en"):
    """Stream LLM response with overlapping TTS via producer-consumer pipeline.

    Architecture:
    - LLM Producer: Streams tokens from Ollama, detects sentence boundaries,
      sends text chunks to browser for display, pushes sentences to TTS queue.
    - TTS Consumer: Reads sentences from queue, sends to XTTS microservice,
      streams PCM audio chunks back to browser via WebSocket binary frames.
    - Both run concurrently via asyncio.gather for maximum overlap.

    This eliminates the delay by starting TTS generation as soon as
    the first sentence is ready, while LLM continues generating more text.
    """
    import time
    start_time = time.time()
    perf_start = time.perf_counter()
    vram_llm_before = 0
    if torch.cuda.is_available():
        vram_llm_before = torch.cuda.memory_reserved(0) / 1024**2
    
    t_meta = t_meta or {}
    t_meta["llm_send"] = perf_start
    t_meta["vram_llm_before"] = vram_llm_before
    if not text or len(text.strip()) < 2:
        try:
            await websocket.send_json({"type": "aiResponse", "text": "I didn't catch that. Could you repeat?", "sources": 0})
        except Exception:
            pass
        return
    
    # Update conversation timestamp
    conversation_timestamps[connection_id] = time.time()
    if len(conversation_history) % 100 == 0:
        cleanup_old_conversations()
    
    history = conversation_history[connection_id]

    # ===== ARABIC LANGUAGE HANDLING =====
    # Auto-detect if caller passed "auto"
    if language == "auto":
        language = _detect_language(text)

    arabic_mode = (language == "ar")
    xtts_lang = "ar" if arabic_mode else XTTS_LANGUAGE
    original_arabic_text = text  # preserve for later use
    _prefetched_rag_docs = None  # cached from Arabic guard check to avoid double RAG search

    if arabic_mode:
        # ---- Fire instant Arabic acknowledgment audio (<1s perceived latency) ----
        if _arabic_ack_pcm:
            # Register the per-connection lock now (before any background task can race us).
            if connection_id not in _ws_write_locks:
                _ws_write_locks[connection_id] = asyncio.Lock()
            _ack_lock = _ws_write_locks[connection_id]
            try:
                async with _ack_lock:
                    await websocket.send_json({"type": "ttsAudioStart", "sampleRate": 24000})
                    await websocket.send_bytes(_arabic_ack_pcm)
                    await websocket.send_json({"type": "ttsAudioEnd"})
                t_meta["first_ack_sent"] = time.perf_counter()  # stamp for latency report
            except Exception:
                pass  # don't let ack failure block the actual answer

        # 1. Allow small talk in Arabic (greetings, thanks, etc.)
        if _is_arabic_small_talk(text):
            logger.info(f"{connection_id} Arabic small-talk detected — routing through normally")
            text_for_rag = text  # will be handled as greeting below
            arabic_small_talk = True
        else:
            arabic_small_talk = False
            # 2. Translate Arabic query → English for RAG search using fast translator
            logger.info(f"{connection_id} Arabic mode: translating query to English…")
            try:
                translated_query = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: __import__('deep_translator', fromlist=['GoogleTranslator'])
                               .GoogleTranslator(source='ar', target='en').translate(text)
                )
                text_for_rag = translated_query if translated_query else text
                logger.info(f"Translation (Arabic→English): '{text[:60]}' → '{text_for_rag[:60]}'")
            except Exception as _te:
                logger.warning(f"deep_translator AR→EN failed ({_te}) — falling back to LLM translation")
                try:
                    text_for_rag = await asyncio.wait_for(
                        translate_with_llm(text, "ar", "en"), timeout=20.0
                    )
                except Exception:
                    text_for_rag = text

            # 3. Search RAG with the translated English text (cache result to avoid double search below)
            rag_docs_check = search_documents(text_for_rag, top_k=3)
            _prefetched_rag_docs = rag_docs_check  # reuse in the main RAG block
            if not rag_docs_check:
                # Off-topic: no relevant docs in the knowledge base → Arabic refusal
                logger.info(f"{connection_id} Arabic off-topic guard triggered — no RAG docs found for: {text_for_rag[:60]}")
                try:
                    await websocket.send_json({
                        "type": "aiResponseChunk", "text": ARABIC_OFF_TOPIC_RESPONSE,
                        "index": 0, "done": True
                    })
                    await websocket.send_json({
                        "type": "aiResponseDone", "fullText": ARABIC_OFF_TOPIC_RESPONSE,
                        "sources": 0
                    })
                    # TTS for the Arabic refusal
                    asyncio.create_task(_tts_arabic_response(ARABIC_OFF_TOPIC_RESPONSE, websocket, connection_id))
                except Exception:
                    pass
                return
            # Use the English translation for RAG
            text = text_for_rag
    else:
        arabic_small_talk = False

    # RAG search (same as non-streaming)
    greeting_patterns = ['hi', 'hello', 'hey', 'how are you', 'good morning', 'good afternoon', 'good evening', 'thanks', 'thank you']
    # In Arabic small-talk mode, treat as greeting
    is_greeting = arabic_small_talk or (len(text.strip().split()) <= 3 and any(pattern in text.lower() for pattern in greeting_patterns))

    if is_greeting:
        relevant_docs = []
    elif _prefetched_rag_docs is not None:
        # Arabic path: reuse result from guard check — avoids a second identical RAG search
        relevant_docs = _prefetched_rag_docs
    else:
        relevant_docs = search_documents(text, top_k=3)
    
    context_block = ""
    if relevant_docs:
        doc_dicts = [
            {"page_content": doc_text, "metadata": {"doc_id": i, "type": "support_info"}}
            for i, doc_text in enumerate(relevant_docs)
        ]
        toon_context = format_rag_context_toon(doc_dicts)
        context_block = f"""

===== KNOWLEDGE BASE — OVERRIDE YOUR TRAINING DATA =====
{toon_context}
========================================================

CRITICAL RULES — YOU MUST FOLLOW THESE WITHOUT EXCEPTION:
1. Your answer MUST come ONLY from the KNOWLEDGE BASE above.
2. IGNORE everything you learned during training about this topic.
3. Even if the Knowledge Base contradicts popular knowledge, you MUST follow the Knowledge Base.
4. State the Knowledge Base facts directly and confidently as the correct answer.
5. Do NOT say "according to my knowledge" or "actually" — just state the KB facts.
6. If earlier messages in this conversation contradict the KNOWLEDGE BASE, IGNORE those earlier messages — the KNOWLEDGE BASE is always more recent and correct."""
        logger.info(f"{connection_id} RAG: {len(relevant_docs)} docs injected as authoritative context")
    
    if arabic_mode:
        if arabic_small_talk:
            system_prompt = (
                "You are a friendly assistant named Assistify. "
                "Reply ONLY in Arabic (العربية). Do NOT use Chinese, English, or Thai. "
                "Specifically DO NOT output the token 'ควร' or any ไทย/Thai text. "
                "Keep your greeting under 10 words.\n"
                "أنت مساعد ودود اسمه Assistify. رد بتحية عربية قصيرة وودية. أجب بالعربية فقط. "
                "لا تستخدم الصينية أو الإنجليزية أو التايلاندية. ولا تكتب 'ควร'."
            )
        else:
            system_prompt = (
                "You are Assistify, an Amazon services assistant. "
                "You MUST respond ONLY in Arabic (العربية). "
                "NEVER respond in Chinese (中文), English, or Thai (ไทย). "
                "Do NOT output the token 'ควร' or any Thai words. "
                "Use clear Arabic sentences. Keep your answer under 100 words. "
                "Do not cut off mid-sentence.\n"
                "أنت Assistify، مساعد متخصص في خدمات أمازون. أجب بالعربية فقط. "
                "لا تستخدم الصينية أو الإنجليزية أو التايلاندية. لا تكتب 'ควร'."
                f"{context_block}"
            )
    else:
        system_prompt = f"""You are Assistify, a helpful assistant. Keep responses under 80 words. Use short conversational sentences. Be concise — answer in 2-3 sentences maximum. Never cut off mid-sentence. Always respond in English.{context_block}"""
    messages = [{"role": "system", "content": system_prompt}]
    # When KB context is present, skip conversation history to prevent stale
    # old answers from overriding fresh KB data.
    if not relevant_docs:
        messages.extend(history[-10:])
    # In Arabic mode always send the original Arabic question so the model
    # sees an Arabic user turn and stays in Arabic. (text was replaced with
    # the English translation for RAG search — do NOT send that to the LLM.)
    user_message = original_arabic_text.strip() if arabic_mode else text.strip()
    messages.append({"role": "user", "content": user_message})
    
    username = user.get("username", "unknown")
    user_role = user.get("role", "unknown")
    query_length = len(text.strip())
    try:
        await websocket.send_json({"type": "thinking"})
    except Exception:
        return
    
    # Ollama streaming payload — optimized for speed on 8GB VRAM
    # Lower temperature when KB context is present to prevent the LLM drifting
    # away from retrieved facts toward its own parametric knowledge.
    effective_temperature = 0.2 if relevant_docs else 0.6

    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": True,
        "keep_alive": -1,        # keep model in VRAM between requests
        "options": {
            "num_ctx": 2048,
            "temperature": effective_temperature,
            "top_p": 0.9,
            "num_predict": 200 if arabic_mode else 180,  # Arabic: capped for latency
            "num_gpu": 99,
        }
    }
    
    full_response = ""
    sentence_index = 0

    logger.info(f"{connection_id} → Ollama ({OLLAMA_MODEL}) | query: {text[:60]}... | context_docs: {len(relevant_docs)}")

    first_token_time = None
    first_sentence_time = None
    first_tts_chunk_time = None
    vram_llm_active = 0

    # ---- Adaptive chunk sizing ----
    adaptive_words, adaptive_buffer = adaptive_manager.begin_query()
    logger.info(f"{connection_id} Adaptive TTS: words_per_chunk={adaptive_words} buffer={adaptive_buffer:.2f}s")
    tts_chunk_count = 0
    tts_total_time = 0.0

    # ---- Producer-Consumer Pipeline: LLM → Queue → TTS ----
    sentence_queue = asyncio.Queue()
    # Reuse the per-connection lock so _tts_arabic_response background tasks
    # and this function never write to the socket concurrently.
    _ws_send_lock = _ws_write_locks.get(connection_id) or asyncio.Lock()

    async def _safe_ws_json(data):
        async with _ws_send_lock:
            await websocket.send_json(data)

    async def _safe_ws_bytes(data):
        async with _ws_send_lock:
            await websocket.send_bytes(data)

    async def llm_producer():
        """Stream tokens from Ollama and dispatch to TTS queue using a
        timer + word-count state machine.

        FIRST CHUNK — fire as fast as possible:
          • 6-8 words accumulated  OR  700 ms since first LLM token
          • Punctuation is *ignored* for the first chunk.

        SUBSEQUENT CHUNKS — balance quality vs latency:
          • target words (tier-dependent)  OR  500 ms buffer timeout
          •   OR sentence end (preference, never a hard gate)
          • Hard-max to prevent runaway accumulation.
        """
        nonlocal full_response, sentence_index, first_token_time, first_sentence_time, vram_llm_active
        nonlocal adaptive_words
        word_buffer: list[str] = []
        first_chunk_sent = False
        first_token_wall: float | None = None    # wall-clock of first LLM token
        chunk_start_wall: float | None = None    # wall-clock when current chunk accumulation began

        # Pre-fetch policy values from adaptive manager
        fc_min   = adaptive_manager.first_chunk_min_words()
        fc_max   = adaptive_manager.first_chunk_max_words()
        fc_tmo   = adaptive_manager.first_chunk_timeout_s()
        sub_tmo  = adaptive_manager.subsequent_timeout_s()

        async def _flush_buffer():
            """Send accumulated words to WebSocket + TTS queue, reset state."""
            nonlocal word_buffer, sentence_index, first_sentence_time, chunk_start_wall, first_chunk_sent
            chunk_text = " ".join(word_buffer).strip()
            word_buffer = []
            chunk_start_wall = None  # reset timer for next chunk

            if not chunk_text or len(chunk_text) <= 3:
                return

            if first_sentence_time is None:
                first_sentence_time = time.perf_counter()
                t_meta["first_sentence_ready"] = first_sentence_time
                logger.info(f"LATENCY [First Sentence Ready]: {(first_sentence_time - perf_start)*1000:.0f}ms")

            # In Arabic mode, suppress English display — user will see Arabic at the end
            if not arabic_mode:
                try:
                    await _safe_ws_json({
                        "type": "aiResponseChunk",
                        "text": chunk_text,
                        "index": sentence_index,
                        "done": False,
                        "timing": t_meta if sentence_index == 0 else None
                    })
                    sentence_index += 1
                except Exception:
                    return

            # Always put on TTS queue (tts_consumer decides whether to process in arabic mode)
            await sentence_queue.put(_normalize_digits_for_tts(chunk_text))
            first_chunk_sent = True

        try:
            timeout = aiohttp.ClientTimeout(total=120, connect=5, sock_read=60)
            async with aiohttp.ClientSession(timeout=timeout) as stream_session:
                async with stream_session.post(OLLAMA_API_URL, json=payload) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        logger.error(f"Ollama streaming error {resp.status}: {error_text}")
                        try:
                            await _safe_ws_json({"type": "aiResponse", "text": "The AI service is temporarily unavailable.", "sources": 0})
                        except Exception:
                            pass
                        return

                    async for line in resp.content:
                        # Check for cancellation (barge-in)
                        if cancel_event and cancel_event.is_set():
                            logger.info(f"{connection_id} LLM streaming interrupted by user (barge-in)")
                            try:
                                async for _ in resp.content:
                                    pass
                            except Exception:
                                pass
                            break

                        line_str = line.decode('utf-8').strip()
                        if not line_str:
                            continue

                        try:
                            chunk_data = json.loads(line_str)
                        except json.JSONDecodeError:
                            continue

                        if chunk_data.get("done"):
                            break

                        token = chunk_data.get("message", {}).get("content", "")
                        if not token:
                            continue

                        now = time.perf_counter()

                        if first_token_time is None:
                            first_token_time = now
                            first_token_wall = now
                            t_meta["llm_first_token"] = first_token_time
                            logger.info(f"LATENCY [LLM First Token]: {(first_token_time - perf_start)*1000:.0f}ms")
                            if torch.cuda.is_available():
                                vram_llm_active = torch.cuda.memory_reserved(0) / 1024**2

                        full_response += token

                        # Tokenise new token(s) into words and accumulate.
                        # Sub-word joining: LLM tokenizers often split a word
                        # across tokens (e.g. "Sc" + "anning").  Tokens that
                        # continue the previous word arrive WITHOUT a leading
                        # space.  Detect that and concatenate instead of
                        # creating a new word in the buffer.
                        new_words = token.split()
                        if not new_words:
                            continue

                        if word_buffer and token and not token[0].isspace():
                            # Continuation token — join first part with last
                            # buffered word, then extend with any remaining.
                            word_buffer[-1] += new_words[0]
                            word_buffer.extend(new_words[1:])
                        else:
                            word_buffer.extend(new_words)

                        # Start the chunk timer when first word of this chunk arrives
                        if chunk_start_wall is None:
                            chunk_start_wall = now

                        elapsed = now - chunk_start_wall
                        n_words = len(word_buffer)

                        # ========== FIRST CHUNK — hard override ==========
                        # Completely isolated from adaptive tier logic.
                        # No tier switching, no sentence detection, no tier
                        # buffer timing.  Uses ONLY fixed word count + timer.
                        if not first_chunk_sent:
                            should_flush = (
                                n_words >= fc_max                               # hard cap 8 words
                                or n_words >= fc_min                             # min 6 words reached
                                or (first_token_wall is not None
                                    and (now - first_token_wall) >= fc_tmo)      # 700ms timeout
                            )
                            if should_flush and word_buffer:
                                time_since_first_ms = (
                                    (now - first_token_wall) * 1000
                                    if first_token_wall is not None else 0.0
                                )
                                logger.info(
                                    "FIRST CHUNK FLUSHED (override mode) "
                                    "words=%d time_since_first_token=%.0fms",
                                    len(word_buffer), time_since_first_ms,
                                )
                                await _flush_buffer()
                            # CRITICAL: skip subsequent-chunk / tier logic
                            # on every cycle until first chunk is sent.
                            continue

                        # ========== SUBSEQUENT CHUNKS — adaptive tier ==========
                        has_sentence_end = bool(_re.search(r'[.!?]$', word_buffer[-1]))
                        sub_target = adaptive_manager.subsequent_words()
                        sub_hard   = adaptive_manager.subsequent_hard_max()

                        should_flush = (
                            n_words >= sub_hard                              # hard cap
                            or (has_sentence_end and n_words >= sub_target)  # sentence end at target
                            or elapsed >= sub_tmo                            # 500ms timeout
                        )

                        if should_flush and word_buffer:
                            await _flush_buffer()

            # Flush any remaining buffered words
            if word_buffer:
                await _flush_buffer()

        except asyncio.TimeoutError:
            mem = _get_memory_snapshot()
            logger.error(f"LLM STREAMING TIMEOUT | GPU={mem['gpu_reserved_mb']:.0f}MB CPU={mem['cpu_rss_mb']:.0f}MB")
            try:
                await _safe_ws_json({"type": "aiResponse", "text": "I'm processing your question. Give me a moment.", "sources": 0})
            except Exception:
                pass
        except Exception as e:
            mem = _get_memory_snapshot()
            logger.exception(f"LLM producer error: {e} | GPU={mem['gpu_reserved_mb']:.0f}MB CPU={mem['cpu_rss_mb']:.0f}MB")
            try:
                await _safe_ws_json({"type": "aiResponse", "text": "Sorry, I encountered an issue.", "sources": 0})
            except Exception:
                pass
        finally:
            # Signal TTS consumer to stop
            await sentence_queue.put(None)

    async def tts_consumer():
        """Read chunks from queue, synthesize via XTTS, stream PCM audio over WebSocket.

        Measures first-chunk latency and feeds it back to the
        AdaptiveChunkManager so subsequent chunks (and future queries)
        use an optimised word count.  Applies an inter-chunk buffer delay
        when the system is classified as slow or medium.
        """
        nonlocal first_tts_chunk_time, adaptive_words, adaptive_buffer
        nonlocal tts_chunk_count, tts_total_time
        # Use the persistent global TTS session (avoids TCP setup cost per query).
        # Fall back to a local session if the global is unavailable (e.g. during
        # startup before startup_event has run).
        _local_tts_session = None
        _tts_sess = tts_session
        if _tts_sess is None or _tts_sess.closed:
            _local_tts_session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=None, sock_connect=5, sock_read=None)
            )
            _tts_sess = _local_tts_session
        try:
            while True:
                if cancel_event and cancel_event.is_set():
                    break

                sentence = await sentence_queue.get()
                if sentence is None:
                    break

                if cancel_event and cancel_event.is_set():
                    break

                # Clean text for TTS
                clean = _re.sub(r'[\U00010000-\U0010ffff]', '', sentence, flags=_re.UNICODE).strip()
                if not clean:
                    continue

                chunk_start = time.perf_counter()

                try:
                    await _safe_ws_json({"type": "ttsAudioStart", "sampleRate": 24000})

                    resp = await _tts_sess.post(
                        f"{XTTS_SERVICE_URL}/synthesize",
                        json={"text": clean, "speaker": XTTS_SPEAKER, "language": xtts_lang},
                    )

                    if resp.status == 200:
                        header_skipped = False
                        header_buf = b''
                        pcm_remainder = b''

                        async for chunk in resp.content.iter_chunked(4096):
                            if cancel_event and cancel_event.is_set():
                                break

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

                            # Handle PCM16 alignment (2 bytes per sample)
                            if pcm_remainder:
                                data = pcm_remainder + data
                                pcm_remainder = b''
                            if len(data) % 2 != 0:
                                pcm_remainder = data[-1:]
                                data = data[:-1]

                            if data:
                                await _safe_ws_bytes(data)
                                if first_tts_chunk_time is None:
                                    first_tts_chunk_time = time.perf_counter()
                                    t_meta["first_tts_chunk"] = first_tts_chunk_time
                                    first_chunk_latency_s = first_tts_chunk_time - perf_start
                                    _lang_tag = " (Arabic)" if arabic_mode else ""
                                    logger.info(f"LATENCY [First TTS Chunk{_lang_tag}]: {first_chunk_latency_s*1000:.0f}ms")

                                    # Feed latency into adaptive manager — may adjust mid-query
                                    adaptive_words, adaptive_buffer = (
                                        adaptive_manager.record_first_chunk_latency(first_chunk_latency_s)
                                    )

                        resp.close()

                        # Track per-chunk timing
                        chunk_elapsed = time.perf_counter() - chunk_start
                        tts_chunk_count += 1
                        tts_total_time += chunk_elapsed

                    else:
                        detail = await resp.text()
                        resp.close()
                        logger.warning(f"XTTS returned {resp.status}: {detail[:100]}")
                        await _safe_ws_json({"type": "ttsFallback", "text": clean})

                    await _safe_ws_json({"type": "ttsAudioEnd"})

                    # ---- Buffer strategy: inter-chunk delay for slower systems ----
                    if adaptive_buffer > 0:
                        await asyncio.sleep(adaptive_buffer)

                except aiohttp.ClientConnectorError:
                    logger.warning("XTTS microservice unavailable for TTS consumer")
                    try:
                        await _safe_ws_json({"type": "ttsFallback", "text": clean})
                        await _safe_ws_json({"type": "ttsAudioEnd"})
                    except Exception:
                        pass
                except Exception as e:
                    logger.warning(f"TTS consumer error for sentence: {e}")
                    try:
                        await _safe_ws_json({"type": "ttsAudioEnd"})
                    except Exception:
                        pass
        except Exception as e:
            logger.warning(f"TTS consumer session error: {e}")
        finally:
            if _local_tts_session is not None and not _local_tts_session.closed:
                await _local_tts_session.close()

    try:
        # Run LLM producer and TTS consumer concurrently — overlapping generation
        await asyncio.gather(llm_producer(), tts_consumer())

        # ===== ARABIC: Send full Arabic text as the final display chunk =====
        # (TTS was already streamed live by tts_consumer concurrently with LLM generation)
        if arabic_mode and full_response.strip():
            arabic_chars = sum(1 for c in full_response if '\u0600' <= c <= '\u06FF')
            logger.info(f"{connection_id} Arabic mode: direct response ({len(full_response.strip())} chars, {arabic_chars} Arabic chars)")
            try:
                await websocket.send_json({
                    "type": "aiResponseChunk",
                    "text": full_response.strip(),
                    "index": 0,
                    "done": True,
                })
            except Exception:
                pass
        # ===== END ARABIC =====

        # Validate the full response (skip for Arabic — validator is not Arabic-aware)
        if full_response.strip() and not arabic_mode:
            validation_result = validate_response(full_response.strip(), text, relevant_docs)
            if not validation_result.is_valid:
                logger.warning(f"Streaming response validation FAILED - Severity: {validation_result.severity}")
                full_response = validation_result.modified_response
            elif validation_result.modified_response:
                full_response = validation_result.modified_response

        if full_response.strip():
            # Store original Arabic question in history (not the English translation)
            history_user_text = original_arabic_text if arabic_mode else text.strip()
            history.append({"role": "user", "content": history_user_text})
            history.append({"role": "assistant", "content": full_response.strip()})

        # Send completion message with latency metrics (Phase 6)
        t_llm_done = time.perf_counter()
        t_meta["llm_first_token"] = first_token_time
        t_meta["llm_full_response"] = t_llm_done
        t_meta["vram_llm_active"] = vram_llm_active

        first_token_ms = ((first_token_time - perf_start) * 1000) if first_token_time else None
        first_sentence_ms = ((first_sentence_time - perf_start) * 1000) if first_sentence_time else None
        first_tts_ms = (first_tts_chunk_time - perf_start) * 1000 if first_tts_chunk_time else None
        total_ms = (t_llm_done - perf_start) * 1000

        # Finalise adaptive chunk stats for this query
        adaptive_manager.finish_query(tts_chunk_count, tts_total_time)
        adaptive_stats = adaptive_manager.get_stats()

        logger.info(f"=== LATENCY REPORT [{connection_id}] ===")
        logger.info(f"  LLM First Token:    {first_token_ms:.0f}ms" if first_token_ms else f"  LLM First Token:    N/A")
        logger.info(f"  First Sentence:     {first_sentence_ms:.0f}ms" if first_sentence_ms else f"  First Sentence:     N/A")
        logger.info(f"  First TTS Chunk:    {first_tts_ms:.0f}ms" if first_tts_ms else "  First TTS Chunk:    N/A")
        logger.info(f"  Total Pipeline:     {total_ms:.0f}ms")
        logger.info(f"  Adaptive Tier:      {adaptive_stats['current_tier']} | words={adaptive_stats['words_per_chunk']} buf={adaptive_stats['buffer_delay_s']:.2f}s")
        logger.info(f"  TTS Chunks:         {tts_chunk_count} (total TTS time: {tts_total_time:.2f}s)")
        logger.info(f"=== END LATENCY REPORT ===")

        try:
            await websocket.send_json({
                "type": "aiResponseDone",
                "fullText": full_response.strip(),
                "sources": len(relevant_docs),
                "arabic_mode": arabic_mode,
                "timing": t_meta,
                "latency": {
                    "first_token_ms": round(first_token_ms) if first_token_ms else None,
                    "first_sentence_ms": round(first_sentence_ms) if first_sentence_ms else None,
                    "first_tts_chunk_ms": round(first_tts_ms) if first_tts_ms else None,
                    "total_ms": round(total_ms),
                },
                "adaptive_chunk": {
                    "tier": adaptive_stats['current_tier'],
                    "words_per_chunk": adaptive_stats['words_per_chunk'],
                    "buffer_delay_s": adaptive_stats['buffer_delay_s'],
                    "tts_chunks_processed": tts_chunk_count,
                }
            })
        except Exception:
            pass

        # Analytics
        response_time = int((time.time() - start_time) * 1000)
        log_usage(username, user_role, text, "success", None,
                response_time, len(relevant_docs), query_length, len(full_response))
        logger.info(f"RAG: Streamed {sentence_index} sentences ({len(full_response)} chars) in {response_time}ms")

    except Exception as e:
        response_time = int((time.time() - start_time) * 1000)
        log_usage(username, user_role, text, "error", str(e), response_time, 0, query_length, 0)
        mem = _get_memory_snapshot()
        logger.exception(f"Streaming pipeline error: {e} | GPU={mem['gpu_reserved_mb']:.0f}MB CPU={mem['cpu_rss_mb']:.0f}MB")
        try:
            await websocket.send_json({"type": "aiResponse", "text": "Sorry, I encountered an issue. Let's continue.", "sources": 0})
        except Exception:
            pass


# ========== QUERY ENDPOINT ==========
class QueryRequest(BaseModel):
    text: str

@app.post("/query")
async def query_rag(data: QueryRequest, request: Request, user=Depends(require_login())):
    connection_id = "manual_" + str(uuid.uuid4())[:8]
    ai_response, retrieved_docs = await call_llm_with_rag(data.text, connection_id, user)
    return {"answer": ai_response}

# ========== ANALYTICS API ==========
@app.get("/admin/analytics", response_class=HTMLResponse)
def admin_analytics_page(request: Request, user=Depends(require_login("admin"))):
    html_path = Path(__file__).parent / "templates" / "admin_analytics.html"
    if not html_path.exists():
        raise HTTPException(status_code=404, detail="Admin analytics template not found.")
    content = html_path.read_text(encoding="utf-8")
    return HTMLResponse(content=content)

@app.get("/admin/errors", response_class=HTMLResponse)
def admin_errors_page(request: Request, user=Depends(require_login("admin"))):
    html_path = Path(__file__).parent / "templates" / "admin_errors.html"
    if not html_path.exists():
        raise HTTPException(status_code=404, detail="Admin errors template not found.")
    content = html_path.read_text(encoding="utf-8")
    return HTMLResponse(content=content)


@app.get("/admin/knowledge", response_class=HTMLResponse)
def admin_knowledge_page(request: Request, user=Depends(require_login("admin"))):
    html_path = Path(__file__).parent / "templates" / "admin_knowledge.html"
    if not html_path.exists():
        raise HTTPException(status_code=404, detail="Admin knowledge template not found.")
    content = html_path.read_text(encoding="utf-8")
    return HTMLResponse(content=content)


@app.get("/rag/files")
def get_rag_files(user=Depends(require_login("admin"))):
    """Return uploaded files indexed in the RAG collection."""
    try:
        from backend.knowledge_base import list_uploaded_files
        files = list_uploaded_files()
        return {"files": files}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/rag/debug")
def rag_debug(user=Depends(require_login("admin"))):
    """Return ALL entries in ChromaDB for debugging — shows ids, filenames, and text previews."""
    try:
        from backend.knowledge_base import get_or_create_collection
        collection = get_or_create_collection()
        if not collection:
            return {"count": 0, "entries": []}
        result = collection.get(include=["metadatas", "documents"]) or {}
        ids = result.get("ids", [])
        metadatas = result.get("metadatas", [])
        documents = result.get("documents", [])
        entries = []
        for i, (doc_id, meta, doc) in enumerate(zip(ids, metadatas, documents)):
            entries.append({
                "id": doc_id,
                "filename": meta.get("filename", "") if isinstance(meta, dict) else "",
                "source": meta.get("source", "") if isinstance(meta, dict) else "",
                "chunk_index": meta.get("chunk_index", "") if isinstance(meta, dict) else "",
                "text_preview": (doc or "")[:120],
            })
        return {"count": len(entries), "entries": entries}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/analytics/summary")
def get_analytics_summary(user=Depends(require_login("admin"))):
    """Legacy endpoint - returns basic summary"""
    conn = sqlite3.connect(ANALYTICS_DB)
    c = conn.cursor()
    c.execute("""
        SELECT user_role, COUNT(*) FROM usage_stats GROUP BY user_role
    """)
    data = c.fetchall()
    conn.close()
    return {"summary": data}

@app.get("/analytics/comprehensive")
def get_comprehensive_analytics_endpoint(days: int = 30, user=Depends(require_login("admin"))):
    """New comprehensive analytics endpoint"""
    from backend.analytics import get_comprehensive_analytics
    return get_comprehensive_analytics(days)

@app.get("/analytics/tts-performance")
def tts_performance_stats(user=Depends(require_login("admin"))):
    """Real-time adaptive TTS chunk-size performance dashboard.

    Returns current tier, rolling-average first-chunk latency, recent
    per-query snapshots, and the recommended words-per-chunk / buffer.
    """
    return adaptive_manager.get_stats()

@app.get("/analytics/errors")
def get_recent_errors(user=Depends(require_login("admin"))):
    conn = sqlite3.connect(ANALYTICS_DB)
    c = conn.cursor()
    c.execute("""
        SELECT timestamp, username, error_message, response_time_ms FROM usage_stats
        WHERE response_status != 'success' ORDER BY timestamp DESC LIMIT 50
    """)
    errors = c.fetchall()
    conn.close()
    return {"errors": [{"timestamp": e[0], "username": e[1], "error": e[2], "response_time": e[3]} for e in errors]}

@app.post("/analytics/feedback")
async def submit_feedback(request: Request, user=Depends(require_login())):
    """Allow users to submit satisfaction ratings"""
    from backend.analytics import log_satisfaction
    data = await request.json()
    rating = data.get("rating")
    feedback_text = data.get("feedback")
    
    if not rating or rating < 1 or rating > 5:
        raise HTTPException(status_code=400, detail="Rating must be between 1 and 5")
    
    log_satisfaction(
        username=user.get("username"),
        user_role=user.get("role"),
        rating=rating,
        feedback_text=feedback_text
    )
    return {"message": "Feedback submitted successfully"}

@app.get("/logout")
def logout_redirect():
    """Redirect logout requests on the RAG server to the central auth server.
    Prevents 404s when users hit /logout on the wrong origin.
    """
    from config import BASE_URL
    return RedirectResponse(f"{BASE_URL}/logout", status_code=302)

@app.get('/favicon.ico')
def favicon():
    ico = Path(__file__).resolve().parent / 'assets' / 'favicon.ico'
    if ico.exists():
        return FileResponse(str(ico))
    return Response(status_code=204)

# ========== ROOT & STATUS PAGES ==========
@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    error = request.query_params.get("error")
    if error == "login":
        return HTMLResponse("""
            <html>
              <head>
                <title>Access Restricted</title>
                <style>
                  body { background:#232323;color:#fff;font-family:sans-serif;text-align:center;padding:8vw;}
                  h1 { color:#10a37f; }
                  .box { background:#2b2b2b;padding:2em 3em;border-radius:16px;display:inline-block; }
                  a {color:#10a37f;}
                </style>
              </head>
              <body>
                <div class="box">
                  <h1>Access Restricted</h1>
                  <p>You must be logged in to access this page.</p>
                  <a href="http://localhost:8000/">Go to login</a>
                </div>
              </body>
            </html>
        """, status_code=401)
    stats = get_stats()
    return HTMLResponse(f"""
        <html>
          <head>
            <title>Assistify RAG Status</title>
            <style>
              body {{ background:#232323;color:#fff;font-family:sans-serif;padding:8vw; }}
              .info-box {{ background:#2b2b2b;padding:2em 3em;border-radius:16px;display:inline-block; }}
              h2 {{ color:#10a37f; }}
            </style>
          </head>
          <body>
            <div class="info-box">
              <h2>Assistify RAG Voice Engine Running</h2>
              <p>Status: active</p>
              <p>Features: RAG, Conversation Memory, Knowledge Base</p>
              <p>For API access, please login.</p>
            </div>
          </body>
        </html>
    """)

@app.get("/health")
async def health():
    stats = get_stats()
    return {
        "status": "healthy",
        "services": {
            "asr": whisper_model is not None,
            "tts": xtts_model is not None,
            "llm": "connected",
            "database": True,
            "knowledge_base": True,
            "assets": ASSETS_DIR.exists()
        },
        "stats": stats
    }

@app.get("/stats")
async def statistics():
    stats = get_stats()
    return {
        "database": stats,
        "active_connections": len(conversation_history),
        "knowledge_base": "ChromaDB"
    }


# ========== ARABIC LANGUAGE SUPPORT ENDPOINTS ==========

# Track ongoing Arabic model download
_arabic_download_task: asyncio.Task | None = None
_arabic_download_status: dict = {"state": "idle", "message": ""}


def _arabic_multilingual_model_ready() -> bool:
    """Return True if a multilingual Whisper model is loaded or on-disk (direct folder or HF cache)."""
    if whisper_model_multilingual is not None:
        return True
    if _MULTILINGUAL_MODEL_PATH.exists() and any(_MULTILINGUAL_MODEL_PATH.iterdir()):
        return True
    # Also check HF cache format: models--Systran--faster-whisper-small/snapshots/<hash>/
    _hf_snaps = _MULTILINGUAL_MODEL_PATH.parent / "models--Systran--faster-whisper-small" / "snapshots"
    return _hf_snaps.exists() and any(_hf_snaps.iterdir())


@app.get("/arabic/status")
async def arabic_status(user=Depends(require_login())):
    """Return whether the multilingual Whisper model (for Arabic STT) is ready."""
    model_on_disk = _MULTILINGUAL_MODEL_PATH.exists() and any(_MULTILINGUAL_MODEL_PATH.iterdir())
    model_loaded  = whisper_model_multilingual is not None
    xtts_arabic_ok = xtts_model is not None  # XTTS v2 supports Arabic natively
    return {
        "multilingual_model_ready": model_on_disk or model_loaded,
        "multilingual_model_loaded": model_loaded,
        "multilingual_model_on_disk": model_on_disk,
        "xtts_arabic_ready": xtts_arabic_ok,
        "download_state": _arabic_download_status.get("state", "idle"),
        "download_message": _arabic_download_status.get("message", ""),
        "model_path": str(_MULTILINGUAL_MODEL_PATH),
    }


@app.post("/arabic/download")
async def arabic_download_models(user=Depends(require_login())):
    """Download the multilingual faster-whisper model for Arabic STT support.

    Downloads to: backend/Models/faster-whisper-small/
    Returns immediately; actual download runs in background.
    """
    global _arabic_download_task, _arabic_download_status

    if _arabic_multilingual_model_ready():
        return {"status": "already_ready", "message": "Multilingual model already present."}

    if _arabic_download_task and not _arabic_download_task.done():
        return {"status": "downloading", "message": "Download already in progress."}

    async def _do_download():
        global _arabic_download_status, whisper_model_multilingual
        _arabic_download_status = {"state": "downloading", "message": "Downloading faster-whisper small (multilingual)…"}
        dest = _MULTILINGUAL_MODEL_PATH
        dest.mkdir(parents=True, exist_ok=True)
        try:
            from faster_whisper import WhisperModel as _WM
            # Load on GPU if available — cuts Arabic STT from ~6s to ~0.3s
            _dl_device  = "cuda" if torch.cuda.is_available() else "cpu"
            _dl_compute = "float16" if _dl_device == "cuda" else "int8"
            _dl_kwargs: dict = {"device": _dl_device, "compute_type": _dl_compute, "download_root": str(dest.parent)}
            if _dl_device == "cpu":
                import os as _os
                _cpu_threads = int(_os.getenv("WHISPER_CPU_THREADS", str(min(_os.cpu_count() or 4, 8))))
                _dl_kwargs.update({"cpu_threads": _cpu_threads, "num_workers": 1})
            logger.info(f"[Arabic Setup] Downloading multilingual small model to: {dest} (device={_dl_device}, compute={_dl_compute})")
            _model = _WM("small", **_dl_kwargs)
            # Keep the loaded model global so it's immediately usable without restart
            whisper_model_multilingual = _model
            _arabic_download_status = {"state": "ready", "message": f"Multilingual small model ready (device={_dl_device})."}
            logger.info(f"[Arabic Setup] ✓ Multilingual small model downloaded and loaded (device={_dl_device}, compute={_dl_compute}).")
        except Exception as e:
            _arabic_download_status = {"state": "error", "message": str(e)}
            logger.error(f"[Arabic Setup] Download failed: {e}")

    _arabic_download_task = asyncio.create_task(_do_download())
    return {"status": "downloading", "message": "Download started in background."}


@app.get("/assets/{filename}")
async def get_audio(filename: str):
    file_path = ASSETS_DIR / filename
    if file_path.exists():
        return FileResponse(str(file_path), media_type="audio/wav")
    return {"error": "File not found"}

# ========== FILE UPLOAD ENDPOINT ==========
@app.post("/upload_rag")
async def upload_rag(request: Request, file: UploadFile = File(...), user=Depends(require_login("admin"))):
    verify_csrf(request)

    filename = f"{uuid.uuid4().hex[:8]}_{Path(file.filename).name}"
    file_ext = filename.split('.')[-1].lower()
    if file_ext not in ["pdf", "txt"]:
        return {"message": "Unsupported file type."}

    save_path = ASSETS_DIR / filename
    content = await file.read()
    save_path.write_bytes(content)

    text = ""
    if file_ext == "txt":
        try:
            text = content.decode("utf-8")
        except Exception:
            text = content.decode(errors="ignore")
    else:
        try:
            from PyPDF2 import PdfReader
            reader = PdfReader(save_path)
            pages = []
            for p in reader.pages:
                try:
                    pages.append(p.extract_text() or "")
                except Exception:
                    pages.append("")
            text = "\n\n".join(pages)
        except Exception:
            return {"message": "Uploaded but could not parse PDF (PyPDF2 missing or parsing failed). Install PyPDF2 to enable PDF ingestion."}

    doc_id = f"upload_{uuid.uuid4().hex[:8]}_{filename}"
    metadata = {"source": "upload", "filename": filename}

    # Use chunk-based indexing so each line/paragraph gets its own embedding.
    # Storing the whole file as one doc would average all facts into one vector
    # and make individual fact lookups unreliable.
    chunks_indexed = chunk_and_add_document(doc_id=doc_id, text=text, metadata=metadata,
                                             kb_version=_kb_global_version + 1)

    if chunks_indexed > 0:
        await invalidate_all_caches(action="upload", filename=filename,
                                     chunks_added=chunks_indexed, triggered_by="admin")
        return {"message": f"File '{filename}' uploaded and indexed as {chunks_indexed} chunk(s)."}
    else:
        raise HTTPException(status_code=500, detail="Failed to index uploaded document.")


@app.post("/rag/delete")
async def rag_delete(doc_prefix: str, user=Depends(require_login("admin"))):
    """Delete documents by prefix and also by filename match, then remove the
    physical file from ASSETS_DIR so it can never be re-indexed on restart.

    Example: pass `upload_Best_player.txt` or just `Best_player.txt`
    to remove all chunks associated with that file.
    """
    if not doc_prefix:
        raise HTTPException(status_code=400, detail="doc_prefix is required")

    # ---- 1. Remove all ChromaDB chunks ----
    deleted = delete_documents_with_prefix(doc_prefix)
    deleted += delete_documents_by_filename(doc_prefix)

    # ---- 2. Delete the physical asset file so it cannot be re-indexed ----
    import re as _re
    # Candidate filenames: the prefix itself, and the bare name after stripping
    # the "upload_XXXXXXXX_" UUID prefix that the server prepends to doc_ids.
    _bare = _re.sub(r'^upload_(?:[0-9a-fA-F]{8}_)?', '', doc_prefix)
    asset_candidates = {doc_prefix, _bare}
    # Also strip a leading "upload_" with no UUID (legacy naming)
    if doc_prefix.startswith("upload_"):
        asset_candidates.add(doc_prefix[len("upload_"):])

    deleted_files = []
    for candidate in asset_candidates:
        candidate = candidate.strip()
        if not candidate:
            continue
        asset_path = ASSETS_DIR / candidate
        if asset_path.exists() and asset_path.is_file():
            try:
                asset_path.unlink()
                deleted_files.append(candidate)
                logger.info(f"rag_delete: removed asset file '{candidate}'")
            except Exception as e:
                logger.warning(f"rag_delete: could not remove asset file '{candidate}': {e}")

    await invalidate_all_caches(action="delete", filename=doc_prefix,
                                 chunks_deleted=deleted, triggered_by="admin")
    return {"deleted": deleted, "files_removed": deleted_files}


@app.post("/rag/update")
async def rag_update(req: dict, user=Depends(require_login("admin"))):
    """Update an existing uploaded document (replace and re-chunk).

    JSON body: {"doc_id": "upload_xxx_filename", "text": "...", "metadata": {...}}
    """
    doc_id = req.get("doc_id")
    text = req.get("text")
    metadata = req.get("metadata")
    if not doc_id or text is None:
        raise HTTPException(status_code=400, detail="doc_id and text are required")
    chunks = update_document(doc_id=doc_id, text=text, metadata=metadata)
    if chunks:
        await invalidate_all_caches(action="update", filename=doc_id,
                                     chunks_added=chunks, triggered_by="admin")
        return {"updated_chunks": chunks}
    else:
        raise HTTPException(status_code=500, detail="Update failed")


@app.post("/rag/reindex-file")
async def rag_reindex_file(filename: str, user=Depends(require_login("admin"))):
    """Reindex an uploaded file by filename (uploads are saved to assets dir).

    Clears all existing chunks associated with this filename (including any
    orphans from a previous broken run), then re-indexes fresh from disk.
    """
    if not filename:
        raise HTTPException(status_code=400, detail="filename is required")
    save_path = ASSETS_DIR / filename
    if not save_path.exists():
        raise HTTPException(status_code=404, detail="file not found")

    try:
        content = save_path.read_bytes()
        try:
            text = content.decode("utf-8")
        except Exception:
            text = content.decode(errors="ignore")

        # Wipe ALL old chunks for this filename regardless of doc_id prefix
        deleted = delete_documents_by_filename(filename)

        # Deterministic doc_id based on filename (stable across restarts)
        import re as _re
        bare = _re.sub(r'^[0-9a-fA-F]{8}_', '', filename)
        safe = _re.sub(r'[^A-Za-z0-9._-]', '_', bare)
        doc_id = f"upload_{safe}"
        metadata = {"source": "upload", "filename": filename}
        chunks = chunk_and_add_document(doc_id=doc_id, text=text, metadata=metadata,
                                        kb_version=_kb_global_version + 1)
        if chunks:
            await invalidate_all_caches(action="reindex", filename=filename,
                                         chunks_added=chunks, chunks_deleted=deleted,
                                         triggered_by="admin")
            return {"reindexed_chunks": chunks, "deleted_old": deleted}
        else:
            raise HTTPException(status_code=500, detail="Reindex produced no chunks")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/rag/reindex-all")
async def rag_reindex_all(user=Depends(require_login("admin"))):
    """Reindex every .txt and .pdf file currently in the ASSETS_DIR.

    This is the recovery operation — it clears ALL existing chunks for each
    file and rebuilds them fresh, fixing any duplicate/orphan chunks that
    accumulated during a previous buggy run.
    """
    if not ASSETS_DIR.exists():
        return {"message": "Assets directory not found", "files": []}
    results = []
    for p in ASSETS_DIR.iterdir():
        if not p.is_file():
            continue
        if p.suffix.lower() not in (".txt", ".pdf"):
            continue
        filename = p.name
        try:
            content = p.read_bytes()
            try:
                text = content.decode("utf-8")
            except Exception:
                text = content.decode(errors="ignore")
            deleted = delete_documents_by_filename(filename)
            # Deterministic doc_id based on filename
            import re as _re
            bare = _re.sub(r'^[0-9a-fA-F]{8}_', '', filename)
            safe = _re.sub(r'[^A-Za-z0-9._-]', '_', bare)
            doc_id = f"upload_{safe}"
            metadata = {"source": "upload", "filename": filename}
            chunks = chunk_and_add_document(doc_id=doc_id, text=text, metadata=metadata,
                                            kb_version=_kb_global_version + 1)
            results.append({"filename": filename, "chunks": chunks, "deleted_old": deleted, "status": "ok"})
        except Exception as e:
            results.append({"filename": filename, "status": "error", "error": str(e)})
    total_added = sum(r.get("chunks", 0) for r in results if r.get("status") == "ok")
    total_deleted = sum(r.get("deleted_old", 0) for r in results if r.get("status") == "ok")
    await invalidate_all_caches(action="reindex_all", filename="*",
                                 chunks_added=total_added, chunks_deleted=total_deleted,
                                 triggered_by="admin")
    return {"reindexed": len([r for r in results if r.get("status") == "ok"]), "files": results}


@app.post("/rag/clear-cache")
async def rag_clear_cache(user=Depends(require_login("admin"))):
    """Manually flush all caches so the next query uses fully fresh KB data.

    Clears:
      - All in-memory conversation histories (prevents stale Q&A reuse)
      - Ollama model KV cache (forces model reload so no cached completions)

    Use this when the LLM keeps returning old/wrong answers after a KB edit.
    """
    await invalidate_all_caches(action="clear_cache", filename="*", triggered_by="admin")
    return {
        "status": "ok",
        "message": "All caches cleared — conversations wiped and LLM model cache flushed. Next query will use fresh KB data."
    }


# ========== TEXT-TO-SPEECH ENDPOINT (proxies to XTTS v2 microservice) ==========
class TTSRequest(BaseModel):
    text: str
    speaker: str = XTTS_SPEAKER
    language: str = XTTS_LANGUAGE

@app.post("/tts")
async def tts_endpoint(req: TTSRequest, request: Request):
    """
    Streaming proxy for TTS — forwards chunks from XTTS v2 microservice
    without buffering the full WAV in memory.
    """
    text = req.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Empty text")

    # Remove emojis to avoid synthesis artefacts
    import re
    text = re.sub(r'[\U00010000-\U0010ffff]', '', text, flags=re.UNICODE).strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text empty after cleaning")

    # Open session and initial response OUTSIDE the generator so we can
    # check the status code before committing to a StreamingResponse.
    # The generator's finally-block owns cleanup.
    session = aiohttp.ClientSession()
    try:
        resp = await session.post(
            f"{XTTS_SERVICE_URL}/synthesize",
            json={"text": text, "speaker": req.speaker, "language": req.language},
            # STABILIZATION Part 3: Hard 30s XTTS timeout
            # No sock_read timeout — XTTS may pause between PCM chunks during generation
            timeout=aiohttp.ClientTimeout(total=None, sock_connect=5, sock_read=None),
        )
    except aiohttp.ClientConnectorError:
        await session.close()
        raise HTTPException(
            status_code=503,
            detail=f"XTTS microservice unavailable at {XTTS_SERVICE_URL}. Run: start_xtts_service.bat"
        )
    except (asyncio.TimeoutError, TimeoutError):
        await session.close()
        logger.warning("TTS synthesis timed out (XTTS may still be warming up)")
        raise HTTPException(
            status_code=504,
            detail="TTS synthesis timed out. The XTTS model may still be loading — please try again in a few seconds."
        )
    except Exception as e:
        await session.close()
        logger.error(f"TTS proxy error: {e}")
        raise HTTPException(status_code=500, detail=f"TTS proxy failed: {e}")

    # Check upstream status before starting the stream
    if resp.status != 200:
        detail = await resp.text()
        resp.close()
        await session.close()
        if resp.status == 503:
            raise HTTPException(status_code=503, detail="XTTS microservice not ready")
        elif resp.status == 400:
            raise HTTPException(status_code=400, detail=detail)
        else:
            raise HTTPException(status_code=502, detail=f"XTTS service error: {detail}")

    logger.info("TTS streaming proxy started | chunks=%s", resp.headers.get("X-Chunks", "?"))

    # Stream XTTS audio through without buffering.
    # Generator owns resp + session cleanup via finally.
    async def stream_xtts():
        try:
            async for chunk in resp.content.iter_chunked(4096):
                yield chunk
        finally:
            resp.close()
            await session.close()

    return StreamingResponse(
        stream_xtts(),
        media_type="audio/wav",
        headers={
            "Cache-Control": "no-cache",
            "X-Chunks": resp.headers.get("X-Chunks", "0"),
        },
    )


# ========== WEBSOCKET: Real-time audio -> faster-whisper -> LLM bridge ==========
@app.websocket("/ws")
async def rag_ws_endpoint(websocket: WebSocket):
    global _active_voice_task, _active_voice_conn_id
    await websocket.accept()
    connection_id = f"conn_{uuid.uuid4().hex[:8]}"
    logger.info(f"New websocket connection {connection_id}")
    # Register for KB broadcast notifications
    _active_ws_connections[connection_id] = websocket

    # Create cancel event for barge-in support
    cancel_event = asyncio.Event()
    interrupt_events[connection_id] = cancel_event
    # Per-connection write lock — shared with _tts_arabic_response background tasks
    _ws_write_locks[connection_id] = asyncio.Lock()

    user = None
    try:
        token = websocket.cookies.get(SESSION_COOKIE)
        if token:
            user = serializer.loads(token)
    except Exception:
        user = None

    if not user:
        logger.debug(f"Websocket {connection_id}: no valid session cookie found; continuing as anonymous")

    # Buffer for accumulating audio chunks
    audio_buffer = bytearray()
    first_audio_arrival = None  # Timestamp of when the first chunk of a speech segment arrived
    speech_start_time = None    # When VAD (energy) first detected speech
    silence_counter = 0  # Count consecutive silent chunks
    # STABILIZATION Part 6: Silence detection tuned via benchmark.
    # STT is ultra-fast (32ms on CPU) so we can afford to wait a bit longer
    # for true silence to avoid splitting multi-word phrases.
    # 10 chunks × ~50ms each = ~500ms — bridges natural inter-word pauses.
    silence_chunks_needed = 10           # ~500ms true silence before transcription fires
    silence_threshold_energy = 0.008    # Strict: only truly quiet audio counts as silence
    # Per-connection language setting (can be updated by set_language control message)
    session_language = "en"

    # ========== STABILIZED auto_transcribe ==========
    # Defined here (not inside the conditional) so it is always in scope when
    # stop_recording or any other handler calls it.
    async def auto_transcribe(data_bytes: bytes, ws, conn_id, t_meta=None, lang="en"):
        nonlocal user
        global _active_voice_task, _active_voice_conn_id
        global _pipeline_run_count, _last_gpu_reserved_mb
        global _consecutive_gpu_growth, _consecutive_cpu_growth, _sessions_blocked
        import time as _time

        # ---- Memory-leak gate ----
        if _sessions_blocked:
            logger.error(f"MEMORY LEAK SUSPECTED — refusing new voice session [{conn_id}]")
            try:
                await ws.send_json({"type": "aiResponse", "text": "System paused for safety. Please restart the server.", "sources": 0})
            except Exception:
                pass
            return

        session_start = _time.perf_counter()
        mem_before = _get_memory_snapshot()
        logger.info(f"===== VOICE SESSION START  [{conn_id}] =====")
        logger.info(f"  GPU before: reserved={mem_before['gpu_reserved_mb']:.0f}MB  alloc={mem_before['gpu_allocated_mb']:.0f}MB  |  CPU RSS={mem_before['cpu_rss_mb']:.0f}MB")

        # Cancel any previously-active voice task (Part 1 — only 1 at a time)
        if _active_voice_task and not _active_voice_task.done():
            logger.warning(f"Cancelling previous voice session [{_active_voice_conn_id}]")
            _active_voice_task.cancel()
            try:
                await _active_voice_task
            except (asyncio.CancelledError, Exception):
                pass
        _active_voice_conn_id = conn_id

        try:
            # Part 2 — only 1 pipeline at a time
            async with voice_semaphore:
                t_stt_start = _time.perf_counter()

                if t_meta and "speech_end" in t_meta:
                    latency_vad_to_stt = t_stt_start - t_meta["speech_end"]
                    logger.info(f"VOICE LATENCY [Speech End -> STT Start]: {latency_vad_to_stt*1000:.2f}ms")

                pcm16 = np.frombuffer(data_bytes, dtype=np.int16).astype(np.float32) / 32768.0

                if len(pcm16) < 8000:
                    logger.debug(f"{conn_id} Audio too short ({len(pcm16)} samples), skipping")
                    return

                vram_stt_before = 0
                if torch.cuda.is_available():
                    vram_stt_before = torch.cuda.memory_reserved(0) / 1024**2

                # Part 3 — STT timeout
                def _run_stt(audio_data):
                    """Run faster-whisper transcribe in a thread. Returns (segments_list, info)."""
                    # Pass language explicitly — never use None (auto-detect) to avoid per-call detection overhead
                    stt_lang = "ar" if lang == "ar" else "en"
                    # Pick the best available model for the language
                    _model = whisper_model_multilingual if (
                        lang == "ar" and whisper_model_multilingual is not None
                    ) else whisper_model
                    # Arabic on GPU: beam_size=5 for accuracy; English: greedy (beam=1)
                    _beam = 5 if lang == "ar" else WHISPER_BEAM_SIZE
                    # Arabic: initial_prompt primes decoder with domain vocabulary
                    # (prevents "أبيع"→"أبي", "يجب"→"أجب", etc.)
                    _initial_prompt = _ARABIC_STT_INITIAL_PROMPT if lang == "ar" else None
                    segs_gen, info = _model.transcribe(
                        audio_data,
                        language=stt_lang,
                        beam_size=_beam,
                        temperature=0.0,
                        vad_filter=WHISPER_VAD_FILTER,
                        vad_parameters=dict(min_silence_duration_ms=300, threshold=0.3),
                        condition_on_previous_text=False,
                        compression_ratio_threshold=2.4,
                        log_prob_threshold=-1.0,
                        no_speech_threshold=0.8,
                        word_timestamps=False,
                        without_timestamps=True,
                        initial_prompt=_initial_prompt,
                    )
                    return list(segs_gen), info

                # Timeout: small model on GPU ~0.3s, on CPU ~2s — 10s is safe headroom for both
                _stt_timeout = 10.0
                try:
                    loop = asyncio.get_event_loop()
                    segments_list, _stt_info = await asyncio.wait_for(
                        loop.run_in_executor(None, _run_stt, pcm16),
                        timeout=_stt_timeout,
                    )
                except asyncio.TimeoutError:
                    logger.error(f"{conn_id} STT TIMEOUT (>{_stt_timeout:.0f} s) — dropping audio")
                    return

                full_text = " ".join([seg.text.strip() for seg in segments_list]).strip()
                t_stt_end = _time.perf_counter()
                stt_duration = t_stt_end - t_stt_start

                vram_stt_after = 0
                if torch.cuda.is_available():
                    vram_stt_after = torch.cuda.memory_reserved(0) / 1024**2

                if not full_text or len(full_text) <= 2:
                    logger.debug(f"{conn_id} whisper returned empty text, skipping")
                    return

                audio_len = len(data_bytes) / (SAMPLE_RATE * 2)  # seconds
                logger.info(f"{conn_id} WHISPER RESULT: '{full_text}' ({len(segments_list)} segments, {audio_len:.2f}s audio, STT took {stt_duration*1000:.0f}ms)")

                t_meta = t_meta or {}
                t_meta.update({
                    "stt_start": t_stt_start,
                    "stt_end": t_stt_end,
                    "vram_stt_before": vram_stt_before,
                    "vram_stt_after": vram_stt_after,
                })

                try:
                    await ws.send_json({
                        "type": "transcript",
                        "text": full_text,
                        "final": True,
                        "timing": t_meta,
                    })

                    cancel_evt = interrupt_events.get(conn_id)
                    if cancel_evt:
                        cancel_evt.clear()

                    await call_llm_streaming(
                        ws, full_text, conn_id,
                        user or {"username": "anon", "role": "user"},
                        cancel_evt,
                        t_meta,
                        language=lang,
                    )
                except RuntimeError as re:
                    logger.debug(f"{conn_id} WebSocket closed: {re}")
        except asyncio.CancelledError:
            logger.warning(f"{conn_id} Voice pipeline cancelled (superseded)")
        except Exception as e:
            logger.exception(f"Auto-transcription error: {e}")
        finally:
            # Part 7 + 9 — memory + session-end logging
            mem_after = _get_memory_snapshot()
            duration = (_time.perf_counter() - session_start) * 1000
            _pipeline_run_count += 1
            logger.info(f"===== VOICE SESSION END    [{conn_id}] =====")
            logger.info(f"  SESSION DURATION: {duration:.0f}ms")
            logger.info(f"  GPU after : reserved={mem_after['gpu_reserved_mb']:.0f}MB  alloc={mem_after['gpu_allocated_mb']:.0f}MB  |  CPU RSS={mem_after['cpu_rss_mb']:.0f}MB")
            delta_gpu = mem_after["gpu_reserved_mb"] - mem_before["gpu_reserved_mb"]
            delta_cpu = mem_after["cpu_rss_mb"] - mem_before["cpu_rss_mb"]

            # Track consecutive growth
            if delta_gpu > 50:
                _consecutive_gpu_growth += 1
                logger.warning(f"  ⚠ GPU memory grew by {delta_gpu:.0f}MB (consecutive: {_consecutive_gpu_growth}/{MEMORY_GROWTH_LIMIT})")
            else:
                _consecutive_gpu_growth = 0

            if delta_cpu > 100:
                _consecutive_cpu_growth += 1
                logger.warning(f"  ⚠ CPU RSS grew by {delta_cpu:.0f}MB (consecutive: {_consecutive_cpu_growth}/{MEMORY_GROWTH_LIMIT})")
            else:
                _consecutive_cpu_growth = 0

            # Cross-run GPU growth check
            if _pipeline_run_count > 1 and mem_after["gpu_reserved_mb"] > _last_gpu_reserved_mb + 100:
                logger.warning(f"  ⚠ CONTINUOUS GPU GROWTH across runs (prev={_last_gpu_reserved_mb:.0f} now={mem_after['gpu_reserved_mb']:.0f})")
            _last_gpu_reserved_mb = mem_after["gpu_reserved_mb"]

            # Block new sessions after MEMORY_GROWTH_LIMIT consecutive growth events
            if _consecutive_gpu_growth >= MEMORY_GROWTH_LIMIT or _consecutive_cpu_growth >= MEMORY_GROWTH_LIMIT:
                _sessions_blocked = True
                logger.critical(f"  🛑 MEMORY LEAK SUSPECTED — blocking all new voice sessions")
                logger.critical(f"     GPU consecutive growth: {_consecutive_gpu_growth}  |  CPU consecutive growth: {_consecutive_cpu_growth}")

            _active_voice_task = None
            _active_voice_conn_id = None

    try:
        while True:
            msg = await websocket.receive()
            if msg["type"] == "websocket.receive":
                if "bytes" in msg and msg["bytes"] is not None:
                    audio = msg["bytes"]
                    current_time = time.perf_counter()
                    
                    if not first_audio_arrival and len(audio_buffer) == 0:
                        first_audio_arrival = current_time

                    if whisper_model is None:
                        logger.warning(f"{connection_id} received audio but faster-whisper not loaded")
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
                    
                    # If we've had enough consecutive silent chunks AND we have audio buffered
                    # AND we actually detected speech at some point (prevents noise-only transcriptions)
                    if silence_counter >= silence_chunks_needed and len(audio_buffer) > 48000 and speech_start_time is not None:
                        # Transcribe everything we've accumulated
                        # 48000 bytes = 1.5s minimum audio — prevents firing on short single words
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

                        logger.info(f"{connection_id} ✓ TRANSCRIBE TRIGGERED: {len(chunk)} bytes ({audio_duration_sec:.2f}s audio) after {triggered_after} silent chunks")
                        task = asyncio.create_task(auto_transcribe(chunk, websocket, connection_id, timing_meta, lang=session_language))
                        _active_voice_task = task
                    elif silence_counter >= silence_chunks_needed and len(audio_buffer) <= 48000 and speech_start_time is not None:
                        # Buffer too small to be a real utterance — drain it
                        logger.debug(f"{connection_id} Buffer too small ({len(audio_buffer)} bytes < 48000 min), discarding")
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
                                # User stopped recording - NOW transcribe the full audio buffer
                                if len(audio_buffer) > 0:
                                    chunk = bytes(audio_buffer)
                                    audio_duration_sec = len(chunk) / (SAMPLE_RATE * 2)
                                    audio_buffer.clear()
                                    silence_counter = 0
                                    logger.info(f"{connection_id} ⏹ MANUAL STOP: transcribing {len(chunk)} bytes ({audio_duration_sec:.2f}s audio)")
                                    task = asyncio.create_task(auto_transcribe(chunk, websocket, connection_id, lang=session_language))
                                    _active_voice_task = task
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
                                cancel_evt = interrupt_events.get(connection_id)
                                if cancel_evt:
                                    cancel_evt.set()
                                audio_buffer.clear()
                                silence_counter = 0
                                logger.info(f"{connection_id} User barge-in - LLM generation interrupted")

                            elif action == "set_language":
                                # Frontend informed us of language selection (en/ar/auto)
                                new_lang = payload.get("language", "en")
                                if new_lang in ("en", "ar", "auto"):
                                    session_language = new_lang
                                    logger.info(f"{connection_id} Language set to: {session_language}")
                        
                        elif "text" in payload:
                            # Handle typed text queries with streaming
                            text = payload["text"].strip()
                            # Allow per-message language override; fall back to session setting
                            msg_lang = payload.get("language", session_language)
                            if msg_lang in ("en", "ar", "auto"):
                                session_language = msg_lang  # update session preference
                            if text:
                                logger.info(f"{connection_id} text query [{msg_lang}]: {text}")
                                cancel_evt = interrupt_events.get(connection_id)
                                if cancel_evt:
                                    cancel_evt.clear()
                                await call_llm_streaming(
                                    websocket, text, connection_id,
                                    user or {"username": "anon", "role": "user"},
                                    cancel_evt,
                                    language=msg_lang,
                                )
            
            elif msg["type"] == "websocket.disconnect":
                logger.info(f"Websocket {connection_id} disconnected")
                break
    except WebSocketDisconnect:
        logger.info(f"Websocket {connection_id} closed by client")
    except Exception as e:
        # FAILURE RESPONSE MODE: log diagnostic summary on unexpected error
        mem = _get_memory_snapshot()
        logger.exception(f"Websocket {connection_id} error: {e}")
        logger.error(f"  DIAGNOSTIC: GPU={mem['gpu_reserved_mb']:.0f}MB  CPU={mem['cpu_rss_mb']:.0f}MB  "
                     f"pipeline_runs={_pipeline_run_count}  sessions_blocked={_sessions_blocked}")
        try:
            await websocket.close()
        except Exception:
            pass
    finally:
        # Cleanup interrupt event and write lock
        if connection_id in interrupt_events:
            del interrupt_events[connection_id]
        _ws_write_locks.pop(connection_id, None)
        # Cancel dangling voice task on disconnect
        if _active_voice_task and not _active_voice_task.done() and _active_voice_conn_id == connection_id:
            logger.info(f"Cancelling dangling voice task for {connection_id}")
            _active_voice_task.cancel()
            try:
                await _active_voice_task
            except (asyncio.CancelledError, Exception):
                pass
        # Clean up conversation memory for this connection
        if connection_id in conversation_history:
            del conversation_history[connection_id]
        if connection_id in conversation_timestamps:
            del conversation_timestamps[connection_id]
        # Deregister from KB broadcast pool
        _active_ws_connections.pop(connection_id, None)
        mem_final = _get_memory_snapshot()
        logger.info(f"Websocket {connection_id} fully cleaned up | GPU={mem_final['gpu_reserved_mb']:.0f}MB CPU={mem_final['cpu_rss_mb']:.0f}MB")


# ========== WEBSOCKET: Admin KB-events real-time feed ==========
@app.websocket("/ws/kb-events")
async def kb_events_ws(websocket: WebSocket):
    """Admin-only WebSocket that streams real-time KB mutation events.

    The admin monitoring page subscribes here to receive a live event feed.
    """
    await websocket.accept()
    try:
        token = websocket.cookies.get(SESSION_COOKIE)
        user = serializer.loads(token) if token else None
    except Exception:
        user = None
    if not user or user.get("role") not in ("admin", "superadmin"):
        await websocket.send_json({"type": "error", "message": "Unauthorized"})
        await websocket.close(code=4003)
        return

    _kb_event_subscribers.add(websocket)
    logger.info(f"KB-events subscriber connected ({len(_kb_event_subscribers)} total)")
    await websocket.send_json({
        "type": "connected",
        "kb_version": _kb_global_version,
        "active_sessions": len(_active_ws_connections),
        "message": "Subscribed to live KB events",
    })
    try:
        while True:
            msg = await websocket.receive()
            if msg.get("type") == "websocket.disconnect":
                break
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        _kb_event_subscribers.discard(websocket)
        logger.info(f"KB-events subscriber disconnected ({len(_kb_event_subscribers)} remaining)")


# ========== KB MONITORING DASHBOARD ==========
@app.get("/admin/kb-monitor", response_class=HTMLResponse)
def admin_kb_monitor_page(request: Request, user=Depends(require_login("admin"))):
    """Serve the KB monitoring dashboard HTML page."""
    html_path = Path(__file__).parent / "templates" / "admin_kb_monitor.html"
    if not html_path.exists():
        raise HTTPException(status_code=404, detail="KB monitor template not found.")
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))


@app.get("/api/kb-stats")
def api_kb_stats(days: int = 30, user=Depends(require_login("admin"))):
    """Return KB performance and mutation metrics for the monitoring dashboard."""
    stats = get_kb_stats(days=days)
    stats["kb_version"] = _kb_global_version
    stats["active_sessions"] = len(_active_ws_connections)
    stats["kb_event_subscribers"] = len(_kb_event_subscribers)
    return stats


@app.get("/api/kb-events")
def api_kb_events(limit: int = 100, user=Depends(require_login("admin"))):
    """Return recent KB mutation events for the monitoring dashboard."""
    return {"events": get_kb_events(limit=limit), "kb_version": _kb_global_version}


@app.get("/internal/asr-status")
def asr_status():
    """Return current ASR configuration and status"""
    return {
        "engine": "faster-whisper",
        "model_size": WHISPER_MODEL_SIZE,
        "device": WHISPER_DEVICE,
        "compute_type": WHISPER_COMPUTE_TYPE,
        "beam_size": WHISPER_BEAM_SIZE,
        "vad_enabled": WHISPER_VAD_FILTER,
        "sample_rate": 16000,
        "model_loaded": whisper_model is not None,
        "gpu_available": torch.cuda.is_available() if WHISPER_AVAILABLE else False
    }

@app.get("/internal/preflight")
def preflight_check():
    """System preflight check — verifies strict stability config."""
    checks = _system_preflight()
    mem = _get_memory_snapshot()
    checks["memory"] = mem
    checks["sessions_blocked"] = _sessions_blocked
    checks["consecutive_gpu_growth"] = _consecutive_gpu_growth
    checks["pipeline_runs"] = _pipeline_run_count
    return checks

if __name__ == "__main__":
    import uvicorn
    # STABILIZATION: Never use --reload with GPU models (spawns duplicate processes)
    uvicorn.run("assistify_rag_server:app", host="0.0.0.0", port=7000, reload=False)
        