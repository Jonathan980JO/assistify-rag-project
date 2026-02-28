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
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from passlib.context import CryptContext
from itsdangerous import URLSafeSerializer
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel

import io
import wave
import aiohttp
import torch
import numpy as np

# Import TOON for token-efficient RAG context
from backend.toon import format_rag_context_toon, compare_token_efficiency

# ========== SPEECH RECOGNITION: faster-whisper (GPU required) ==========
try:
    from faster_whisper import WhisperModel
    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False
    WhisperModel = None

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
    LLM_URL = "http://localhost:8000/v1/chat/completions"
    ASSETS_DIR = _P(__file__).resolve().parent / "assets"
    SESSION_SECRET = "X!3p7#9v@Yqe*rQ6CwZ8l&FbM%tUJdfPsoH1XEaN"
    SESSION_COOKIE = "session"
    ANALYTICS_DB = _P(__file__).resolve().parent / "analytics.db"
    DEVELOPMENT = True
    OLLAMA_HOST = "127.0.0.1"
    OLLAMA_PORT = 11434
    OLLAMA_MODEL = "qwen2.5:3b"

from backend.knowledge_base import search_documents, add_document
from backend.database import init_database, save_conversation, start_session, end_session, get_stats
from backend.analytics import init_analytics_db, log_usage
from backend.response_validator import validate_response

# ========== CONFIGURATION ==========
SAMPLE_RATE = 16000

# Ollama direct streaming URL (bypasses main_llm_server for streaming)
OLLAMA_API_URL = f"http://{OLLAMA_HOST}:{OLLAMA_PORT}/api/chat"

# Track interrupt events per connection for barge-in support
interrupt_events = {}

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
    
    # If still too many conversations, remove oldest ones
    if len(conversation_history) > MAX_CONVERSATIONS:
        sorted_conversations = sorted(
            conversation_timestamps.items(),
            key=lambda x: x[1]
        )
        to_remove = len(conversation_history) - MAX_CONVERSATIONS
        for conn_id, _ in sorted_conversations[:to_remove]:
            if conn_id in conversation_history:
                del conversation_history[conn_id]
            if conn_id in conversation_timestamps:
                del conversation_timestamps[conn_id]

# ========== ANALYTICS DB ==========
ANALYTICS_DB = str(ANALYTICS_DB)

# ========== FASTAPI APP INSTANCE (must come before decorators) ==========
app = FastAPI(title="Assistify RAG Voice Engine")

# Global aiohttp session for LLM requests (reuse connections)
llm_session: aiohttp.ClientSession = None

# Global faster-whisper model
whisper_model: WhisperModel = None

# XTTS v2 is now a separate microservice — no local model held in this process
xtts_model = None  # kept for status endpoint backward compat

@app.on_event("startup")
async def startup_event():
    global llm_session, whisper_model, xtts_model, WHISPER_DEVICE, WHISPER_COMPUTE_TYPE
    
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
    logger.info("✓ Databases ready")
    logger.info("✓ Persistent LLM session created with connection pooling")
    
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

    # Fire-and-forget warmup — runs in the background, invisible to users
    asyncio.create_task(_warmup_llm())

async def _warmup_llm():
    """
    Background task: silently sends a tiny prompt to Ollama right after startup
    so the model weights are fully loaded into VRAM before the first real user
    request arrives.  Nothing is stored; the response is discarded.
    """
    await asyncio.sleep(5)          # let the server finish binding / XTTS check
    logger.info(f"[Warmup] Sending warmup prompt to {OLLAMA_MODEL} ...")
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [{"role": "user", "content": "hi"}],
        "stream": False,
        "options": {
            "num_ctx": 512,
            "temperature": 0.0,
            "num_predict": 1,   # we only need 1 token — enough to load weights
        },
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                OLLAMA_API_URL,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=120),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    tok = data.get("message", {}).get("content", "").strip()
                    logger.info(f"[Warmup] ✓ LLM warm — first token: {tok!r}")
                else:
                    text = await resp.text()
                    logger.warning(f"[Warmup] Ollama returned {resp.status}: {text[:120]}")
    except Exception as e:
        logger.warning(f"[Warmup] Warmup failed (model may not be running yet): {e}")


@app.on_event("shutdown")
async def shutdown_event():
    global llm_session
    if llm_session and not llm_session.closed:
        await llm_session.close()
        logger.info("✓ LLM session closed")

logger.info("Initializing Assistify RAG System with faster-whisper...")

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
        relevant_docs = search_documents(text, top_k=1)  # Only 1 doc for speed
    
    # Build context using TOON format (40-60% token savings)
    context = ""
    if relevant_docs:
        # Convert docs to TOON format for token efficiency
        doc_dicts = []
        for i, doc_text in enumerate(relevant_docs):
            doc_dicts.append({
                "page_content": doc_text,
                "metadata": {"doc_id": i, "type": "support_info"}
            })
        
        # Use TOON format instead of plain text
        toon_context = format_rag_context_toon(doc_dicts)
        context = f"\n{toon_context}\n"
        
        logger.info(f"RAG: Found {len(relevant_docs)} docs, formatted as TOON (token optimized)")
    else:
        logger.info("RAG: No RAG context - using general knowledge")
    
    system_prompt = f"""You are Assistify, a helpful voice assistant. Keep responses under 80 words. Use short conversational sentences. Be concise — answer in 2-3 sentences maximum. Never cut off mid-sentence. Avoid long lists or unnecessary explanations.{context}"""
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history[-10:])  # Last 5 exchanges (sliding window)
    messages.append({"role": "user", "content": text.strip()})
    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "max_tokens": 180,
        "temperature": 0.6,
        "stop": None
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

async def call_llm_streaming(websocket: WebSocket, text: str, connection_id: str, user, cancel_event: asyncio.Event = None):
    """Stream LLM response sentence-by-sentence via WebSocket for real-time TTS.
    
    Instead of waiting for the full LLM response, this streams tokens from Ollama,
    detects sentence boundaries, and sends each completed sentence to the client
    immediately so TTS can start playing while the next sentence generates.
    """
    import time
    start_time = time.time()
    
    user = user or {"username": "anon", "role": "user"}
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
    
    # RAG search (same as non-streaming)
    greeting_patterns = ['hi', 'hello', 'hey', 'how are you', 'good morning', 'good afternoon', 'good evening', 'thanks', 'thank you']
    is_greeting = len(text.strip().split()) <= 3 and any(pattern in text.lower() for pattern in greeting_patterns)
    
    if is_greeting:
        relevant_docs = []
    else:
        relevant_docs = search_documents(text, top_k=1)
    
    context = ""
    if relevant_docs:
        doc_dicts = []
        for i, doc_text in enumerate(relevant_docs):
            doc_dicts.append({"page_content": doc_text, "metadata": {"doc_id": i, "type": "support_info"}})
        toon_context = format_rag_context_toon(doc_dicts)
        context = f"\n{toon_context}\n"
    
    system_prompt = f"""You are Assistify, a helpful voice assistant. Keep responses under 80 words. Use short conversational sentences. Be concise — answer in 2-3 sentences maximum. Never cut off mid-sentence. Avoid long lists or unnecessary explanations.{context}"""
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history[-10:])  # Last 5 exchanges (sliding window)
    messages.append({"role": "user", "content": text.strip()})
    
    username = user.get("username", "unknown")
    user_role = user.get("role", "unknown")
    query_length = len(text.strip())
    
    # Send "thinking" status to client
    try:
        await websocket.send_json({"type": "thinking"})
    except Exception:
        return
    
    # Ollama streaming payload — optimized for speed on 8GB VRAM
    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": True,
        "options": {
            "num_ctx": 2048,
            "temperature": 0.6,
            "top_p": 0.9,
            "num_predict": 180,
            "num_gpu": 99,
        }
    }
    
    full_response = ""
    sentence_buffer = ""
    sentence_index = 0
    
    logger.info(f"{connection_id} → Ollama ({OLLAMA_MODEL}) | query: {text[:60]}... | context_docs: {len(relevant_docs)}")
    
    try:
        # Generous timeouts: Ollama may reload the model (~6s) between requests.
        # first-token can take ~30s on cold GPU; total ~5min for long responses
        timeout = aiohttp.ClientTimeout(total=300, connect=15, sock_read=180)
        async with aiohttp.ClientSession(timeout=timeout) as stream_session:
            async with stream_session.post(OLLAMA_API_URL, json=payload) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    logger.error(f"Ollama streaming error {resp.status}: {error_text}")
                    try:
                        await websocket.send_json({"type": "aiResponse", "text": "The AI service is temporarily unavailable.", "sources": 0})
                    except Exception:
                        pass
                    return
                
                async for line in resp.content:
                    # Check for cancellation (barge-in)
                    if cancel_event and cancel_event.is_set():
                        logger.info(f"{connection_id} LLM streaming interrupted by user (barge-in)")
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
                    
                    full_response += token
                    sentence_buffer += token
                    
                    # Detect sentence boundaries (split on .!? followed by space)
                    parts = _sentence_end_pattern.split(sentence_buffer)
                    
                    if len(parts) > 1:
                        # We have at least one complete sentence
                        for i in range(len(parts) - 1):
                            sentence = parts[i].strip()
                            if sentence and len(sentence) > 3:
                                try:
                                    await websocket.send_json({
                                        "type": "aiResponseChunk",
                                        "text": sentence,
                                        "index": sentence_index,
                                        "done": False
                                    })
                                    sentence_index += 1
                                except Exception:
                                    return
                        # Keep the last (incomplete) part as buffer
                        sentence_buffer = parts[-1]
        
        # Send any remaining buffered text
        remaining = sentence_buffer.strip()
        if remaining and len(remaining) > 2:
            try:
                await websocket.send_json({
                    "type": "aiResponseChunk",
                    "text": remaining,
                    "index": sentence_index,
                    "done": False
                })
                sentence_index += 1
            except Exception:
                pass
        
        # Validate the full response
        if full_response.strip():
            validation_result = validate_response(full_response.strip(), text, relevant_docs)
            if not validation_result.is_valid:
                logger.warning(f"Streaming response validation FAILED - Severity: {validation_result.severity}")
                full_response = validation_result.modified_response
            elif validation_result.modified_response:
                full_response = validation_result.modified_response
            
            # Update conversation history
            history.append({"role": "user", "content": text.strip()})
            history.append({"role": "assistant", "content": full_response.strip()})
        
        # Send completion message
        try:
            await websocket.send_json({
                "type": "aiResponseDone",
                "fullText": full_response.strip(),
                "sources": len(relevant_docs)
            })
        except Exception:
            pass
        
        # Analytics
        response_time = int((time.time() - start_time) * 1000)
        log_usage(username, user_role, text, "success", None,
                response_time, len(relevant_docs), query_length, len(full_response))
        logger.info(f"RAG: Streamed {sentence_index} sentences ({len(full_response)} chars) in {response_time}ms")
        
    except asyncio.TimeoutError:
        response_time = int((time.time() - start_time) * 1000)
        log_usage(username, user_role, text, "error", "TimeoutError", response_time, 0, query_length, 0)
        try:
            await websocket.send_json({"type": "aiResponse", "text": "I'm processing your question. Give me a moment.", "sources": 0})
        except Exception:
            pass
    except Exception as e:
        response_time = int((time.time() - start_time) * 1000)
        log_usage(username, user_role, text, "error", str(e), response_time, 0, query_length, 0)
        logger.exception(f"Streaming LLM error: {e}")
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
    success = add_document(doc_id=doc_id, text=text, metadata=metadata)

    if success:
        return {"message": f"File {filename} uploaded and indexed as {doc_id}."}
    else:
        raise HTTPException(status_code=500, detail="Failed to index uploaded document.")

# ========== TEXT-TO-SPEECH ENDPOINT (proxies to XTTS v2 microservice) ==========
class TTSRequest(BaseModel):
    text: str
    speaker: str = XTTS_SPEAKER
    language: str = XTTS_LANGUAGE

@app.post("/tts")
async def tts_endpoint(req: TTSRequest, request: Request):
    """
    Proxy TTS request to the XTTS v2 microservice (assistify_xtts conda env).
    The microservice must be running: start_xtts_service.bat
    """
    text = req.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Empty text")

    # Remove emojis to avoid synthesis artefacts
    import re
    text = re.sub(r'[\U00010000-\U0010ffff]', '', text, flags=re.UNICODE).strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text empty after cleaning")

    try:
        # Forward to the XTTS microservice
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{XTTS_SERVICE_URL}/synthesize",
                json={"text": text, "speaker": req.speaker, "language": req.language},
                timeout=aiohttp.ClientTimeout(total=120, sock_connect=10, sock_read=110),
            ) as resp:
                if resp.status == 503:
                    raise HTTPException(status_code=503, detail="XTTS microservice not ready")
                if resp.status == 400:
                    detail = await resp.text()
                    raise HTTPException(status_code=400, detail=detail)
                if resp.status != 200:
                    detail = await resp.text()
                    raise HTTPException(status_code=502, detail=f"XTTS service error: {detail}")

                wav_bytes = await resp.read()
                lat = resp.headers.get("X-Latency-Ms", "?")
                vram = resp.headers.get("X-VRAM-MB", "?")
                logger.info(f"TTS synthesized via microservice | latency={lat}ms | VRAM={vram}MB | {len(wav_bytes)//1024}KB")

                return Response(
                    content=wav_bytes,
                    media_type="audio/wav",
                    headers={"Cache-Control": "no-cache"},
                )

    except aiohttp.ClientConnectorError:
        raise HTTPException(
            status_code=503,
            detail=f"XTTS microservice unavailable at {XTTS_SERVICE_URL}. Run: start_xtts_service.bat"
        )
    except (asyncio.TimeoutError, TimeoutError):
        logger.warning("TTS synthesis timed out (XTTS may still be warming up)")
        raise HTTPException(
            status_code=504,
            detail="TTS synthesis timed out. The XTTS model may still be loading — please try again in a few seconds."
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"TTS proxy error: {e}")
        raise HTTPException(status_code=500, detail=f"TTS proxy failed: {e}")


# ========== WEBSOCKET: Real-time audio -> faster-whisper -> LLM bridge ==========
@app.websocket("/ws")
async def rag_ws_endpoint(websocket: WebSocket):
    await websocket.accept()
    connection_id = f"conn_{uuid.uuid4().hex[:8]}"
    logger.info(f"New websocket connection {connection_id}")

    # Create cancel event for barge-in support
    cancel_event = asyncio.Event()
    interrupt_events[connection_id] = cancel_event

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
    silence_counter = 0  # Count consecutive silent chunks
    silence_chunks_needed = 40  # 2.5 seconds at ~16 chunks/sec (reduced from 60 for faster response)
    silence_threshold_energy = 0.015  # Increased threshold to reduce false positives

    try:
        while True:
            msg = await websocket.receive()
            if msg["type"] == "websocket.receive":
                if "bytes" in msg and msg["bytes"] is not None:
                    audio = msg["bytes"]
                    
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
                        silence_counter = 0
                    
                    # Always accumulate audio
                    audio_buffer.extend(audio)
                    
                    # If we've had enough consecutive silent chunks AND we have audio buffered
                    if silence_counter >= silence_chunks_needed and len(audio_buffer) > 64000:  # Increased minimum from 32000
                        # Transcribe everything we've accumulated
                        chunk = bytes(audio_buffer)
                        audio_buffer.clear()
                        silence_counter = 0
                        
                        logger.info(f"{connection_id} Auto-transcribing after silence ({len(chunk)} bytes)")
                        
                        # Transcribe in background
                        async def auto_transcribe(data_bytes: bytes, ws, conn_id):
                            try:
                                # Convert to float32 PCM
                                pcm16 = np.frombuffer(data_bytes, dtype=np.int16).astype(np.float32) / 32768.0
                                
                                # Check minimum audio length (at least 0.5 seconds)
                                if len(pcm16) < 8000:  # 16000 samples/sec * 0.5 sec
                                    logger.debug(f"{conn_id} Audio too short ({len(pcm16)} samples), skipping")
                                    return
                                
                                segments, info = whisper_model.transcribe(
                                    pcm16,
                                    language="en",
                                    beam_size=5,  # Good balance of speed/accuracy
                                    temperature=0.0,  # Deterministic output
                                    vad_filter=True,  # Enable VAD to filter silence
                                    vad_parameters=dict(
                                        min_silence_duration_ms=500,  # Minimum silence to split
                                        threshold=0.5  # Voice activity threshold
                                    ),
                                    condition_on_previous_text=False,  # Fresh context each time
                                    compression_ratio_threshold=2.4,  # Reject repetitive output
                                    log_prob_threshold=-1.0,  # Reject low confidence
                                    no_speech_threshold=0.8  # Reject if mostly silence (increased from 0.6)
                                )
                                
                                full_text = " ".join([seg.text.strip() for seg in segments]).strip()
                                
                                # Only process if we have meaningful text
                                if full_text and len(full_text) > 2:
                                    logger.info(f"{conn_id} whisper AUTO: {full_text}")
                                    
                                    try:
                                        await ws.send_json({"type": "transcript", "text": full_text, "final": True})
                                        
                                        # Use streaming LLM for real-time sentence-by-sentence TTS
                                        cancel_evt = interrupt_events.get(conn_id)
                                        if cancel_evt:
                                            cancel_evt.clear()  # Reset for new generation
                                        await call_llm_streaming(
                                            ws, full_text, conn_id,
                                            user or {"username": "anon", "role": "user"},
                                            cancel_evt
                                        )
                                    except RuntimeError as re:
                                        logger.debug(f"{conn_id} WebSocket closed: {re}")
                            except Exception as e:
                                logger.exception(f"Auto-transcription error: {e}")
                        
                        asyncio.create_task(auto_transcribe(chunk, websocket, connection_id))
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
                                    audio_buffer.clear()
                                    silence_counter = 0
                                    logger.info(f"{connection_id} Manual stop - transcribing {len(chunk)} bytes")
                                    asyncio.create_task(auto_transcribe(chunk, websocket, connection_id))
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
                        
                        elif "text" in payload:
                            # Handle typed text queries with streaming
                            text = payload["text"].strip()
                            if text:
                                logger.info(f"{connection_id} text query: {text}")
                                cancel_evt = interrupt_events.get(connection_id)
                                if cancel_evt:
                                    cancel_evt.clear()
                                await call_llm_streaming(
                                    websocket, text, connection_id,
                                    user or {"username": "anon", "role": "user"},
                                    cancel_evt
                                )
            
            elif msg["type"] == "websocket.disconnect":
                logger.info(f"Websocket {connection_id} disconnected")
                break
    except WebSocketDisconnect:
        logger.info(f"Websocket {connection_id} closed by client")
    except Exception as e:
        logger.exception(f"Websocket {connection_id} error: {e}")
        try:
            await websocket.close()
        except Exception:
            pass
    finally:
        # Cleanup interrupt event
        if connection_id in interrupt_events:
            del interrupt_events[connection_id]

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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("assistify_rag_server:app", host="0.0.0.0", port=7000, reload=DEVELOPMENT)
        