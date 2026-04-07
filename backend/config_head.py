import os
import sys
import warnings
import uuid
import json
import asyncio
import logging
import sqlite3
from pathlib import Path
from collections import defaultdict

# Silence a known third-party warning (ctranslate2 imports pkg_resources).
# This is non-fatal and otherwise spams logs on startup.
warnings.filterwarnings(
    "ignore",
    message=r"pkg_resources is deprecated as an API\..*",
    category=UserWarning,
)

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
import random
import numpy as np
import psutil
import traceback
import gc

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
    LLM_URL = "http://127.0.0.1:11434/api/chat"
    ASSETS_DIR = _P(__file__).resolve().parent / "assets"
    SESSION_SECRET = "X!3p7#9v@Yqe*rQ6CwZ8l&FbM%tUJdfPsoH1XEaN"
    SESSION_COOKIE = "session"
    ANALYTICS_DB = _P(__file__).resolve().parent / "analytics.db"
    DEVELOPMENT = True
    OLLAMA_HOST = "127.0.0.1"
    OLLAMA_PORT = 11434
    OLLAMA_MODEL = "qwen2.5:3b"

from backend.knowledge_base import search_documents, add_document, chunk_and_add_document, delete_document, delete_documents_with_prefix, delete_documents_by_filename, update_document, find_base_doc_id_by_filename, list_uploaded_files, count_documents
from backend.database import init_database, save_conversation, start_session, end_session, get_stats
from backend.analytics import init_analytics_db, log_usage, log_kb_event, get_kb_stats, get_kb_events
from backend.response_validator import validate_response

RAG_STRICT_DISTANCE_THRESHOLD = float(os.getenv("RAG_STRICT_DISTANCE_THRESHOLD", "0.70"))
RAG_NO_MATCH_RESPONSE = "Not found in the document."
RAG_GUARD_MODE_VERSION = "two-stage-mild-v3"
RAG_OLD_STRICT_07_ACTIVE = False

# ========== CONFIGURATION ==========
SAMPLE_RATE = 16000

# Ollama direct URL â€” all LLM calls go here, main_llm_server.py is NOT used
OLLAMA_API_URL = f"http://{OLLAMA_HOST}:{OLLAMA_PORT}/api/chat"

# Track interrupt events per connection for barge-in support
interrupt_events = {}
# Per-connection WebSocket write lock â€” prevents concurrent send() calls from
# call_llm_streaming and _tts_arabic_response background tasks crashing the socket.
_ws_write_locks: dict[str, asyncio.Lock] = {}

# ========== STABILIZATION: Concurrency + Resource Guards ==========
# Semaphore(1) = only ONE voice pipeline at a time (Part 2)
voice_semaphore = asyncio.Semaphore(1)
# Track the currently-active voice task so we can cancel it on new session
_active_voice_task: asyncio.Task | None = None
