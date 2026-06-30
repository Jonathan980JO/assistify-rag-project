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
        OLLAMA_HOST, OLLAMA_PORT, OLLAMA_MODEL,
        DEFAULT_TENANT_ID, tenant_collection_base, tenant_collection_name,
        tenant_assets_dir, kb_asset_search_dirs, CHROMA_DB_PATH,
    )
except Exception:
    # Fallbacks if config isn't importable
    from pathlib import Path as _P
    WHISPER_MODEL_PATH = _P(__file__).resolve().parent / "Models" / "faster-whisper-medium.en"
    WHISPER_MODEL_SIZE = "medium.en"
    WHISPER_DEVICE = "cpu"
    WHISPER_COMPUTE_TYPE = "int8"
    WHISPER_BEAM_SIZE = 5
    WHISPER_VAD_FILTER = True
    LLM_URL = "http://127.0.0.1:11434/api/chat"
    ASSETS_DIR = _P(__file__).resolve().parent / "assets"
    SESSION_SECRET = os.getenv(
        "SESSION_SECRET",
        "development-only-secret",
    )
    SESSION_COOKIE = "session"
    ANALYTICS_DB = _P(__file__).resolve().parent / "analytics.db"
    CHROMA_DB_PATH = _P(__file__).resolve().parent / "chroma_db_v3"
    DEVELOPMENT = True
    OLLAMA_HOST = "127.0.0.1"
    OLLAMA_PORT = 11434
    OLLAMA_MODEL = "qwen2.5:3b"
    # Multi-tenancy fallbacks (mirror config.py semantics: tenant 1 keeps
    # historical collection / asset names; other tenants are namespaced).
    DEFAULT_TENANT_ID = 1

    def tenant_collection_base(tenant_id):
        try:
            tid = int(tenant_id)
        except (TypeError, ValueError):
            tid = DEFAULT_TENANT_ID
        if tid <= 0:
            tid = DEFAULT_TENANT_ID
        return "support_docs_v3" if tid == DEFAULT_TENANT_ID else f"t{tid}_support_docs_v3"

    def tenant_collection_name(tenant_id):
        return f"{tenant_collection_base(tenant_id)}_latest"

    def tenant_assets_dir(tenant_id):
        try:
            tid = int(tenant_id)
        except (TypeError, ValueError):
            tid = DEFAULT_TENANT_ID
        if tid <= 0:
            tid = DEFAULT_TENANT_ID
        directory = ASSETS_DIR / f"tenant_{tid}"
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        return directory

    def kb_asset_search_dirs(scope_tid):
        if scope_tid is None:
            return [tenant_assets_dir(DEFAULT_TENANT_ID), ASSETS_DIR]
        return [tenant_assets_dir(scope_tid)]

from backend.knowledge_base import search_documents, add_document, chunk_and_add_document, delete_document, delete_documents_with_prefix, delete_documents_by_filename, update_document, find_base_doc_id_by_filename, list_uploaded_files, count_documents
from backend.database import init_database, save_conversation, start_session, end_session, get_stats
from backend.analytics import init_analytics_db, log_usage, log_kb_event, get_kb_stats, get_kb_events
from backend.response_validator import validate_response

# Voice runtime state (after ML stack imports above)
from backend.voice_audio.state import (
    voice_semaphore,
    interrupt_events,
    ws_write_locks,
    SAMPLE_RATE,
)
from backend.voice_audio import memory_guard

_ws_write_locks = ws_write_locks
_active_voice_task = memory_guard.active_voice_task

RAG_STRICT_DISTANCE_THRESHOLD = float(os.getenv("RAG_STRICT_DISTANCE_THRESHOLD", "1.0"))
RAG_NO_MATCH_RESPONSE = "Not found in the document."
CS_NO_MATCH_RESPONSE_EN = (
    "Thanks for reaching out! I couldn't find that specific detail in our help materials just yet. "
    "Could you rephrase your question, or ask about another topic covered in our knowledge base? "
    "I'm happy to help."
)
CS_NO_MATCH_RESPONSE_AR = (
    "شكراً لتواصلك! لم أجد هذا التفصيل المحدد في مواد المساعدة لدينا بعد. "
    "هل يمكنك إعادة صياغة سؤالك، أو السؤال عن موضوع آخر مشمول في قاعدة المعرفة؟ "
    "يسعدني مساعدتك."
)
CUSTOMER_SUPPORT_AGENT_SYSTEM_PROMPT = (
    "You are Assistify, a friendly customer support agent for this business.\n"
    "Answer using ONLY the provided context from our help materials.\n"
    "Use clear, professional, conversational language.\n"
    "If the answer is not in the context, say warmly that the detail is not in the uploaded materials.\n"
    "Never invent formulas, coefficient weights, diagnostic codes, quotes, or historical links not present in context.\n"
)
RAG_GROUNDING_REFUSAL_RULE = (
    "If the retrieved documents do not contain the requested formula, coefficient weights, "
    "diagnostic code, or historical connection, say so clearly and do not invent one."
)
ENGLISH_WARM_REFUSAL_INSTRUCTION = (
    "If the answer is NOT in the provided context, respond warmly that the detail is not in the "
    "uploaded help materials. Do NOT use robotic internal placeholder phrases."
)
ENGLISH_LIST_EXTRACTION_RULES = (
    "When the user asks for structured list output (including figure/table-adjacent content):\n"
    "- Extract and reconstruct list items from noisy OCR, captions, or semi-structured paragraphs when clearly grounded.\n"
    "- Clean obvious OCR artifacts but do NOT invent facts.\n"
    "- Return a structured list only when items are clearly supported by context; otherwise give a warm "
    "brief note that the detail is not in the help materials.\n"
    "- Ignore headings like 'Figure' or 'Table' when they are merely labels.\n"
)


def build_english_support_system_prompt(extra_rules: str = "") -> str:
    """Active English LLM persona: friendly support agent + strict grounding."""
    parts = [
        CUSTOMER_SUPPORT_AGENT_SYSTEM_PROMPT.strip(),
        RAG_GROUNDING_REFUSAL_RULE,
        "Never use outside knowledge. Respond in clear, friendly English.",
        ENGLISH_WARM_REFUSAL_INSTRUCTION,
        ENGLISH_LIST_EXTRACTION_RULES.strip(),
    ]
    if extra_rules.strip():
        parts.append(extra_rules.strip())
    return "\n".join(parts)


def build_english_stream_context_block(
    toon_context: str,
    doc_router_context_rules: str = "",
    format_rules: str = "",
) -> str:
    """WebSocket context block with friendly support persona in CORE RULES."""
    return f"""
===== KNOWLEDGE BASE CONTEXT =====
{toon_context}
==================================

CORE RULES:
1. You are Assistify, a friendly customer support agent for this business.
2. You MUST answer ONLY using the provided KNOWLEDGE BASE CONTEXT.
3. {ENGLISH_WARM_REFUSAL_INSTRUCTION}
4. {RAG_GROUNDING_REFUSAL_RULE}
5. NEVER use outside knowledge or fabricate statistics, quotes, or codes.
6. Keep answers clear, conversational, and helpful—like a real support agent.
{doc_router_context_rules}
{format_rules}

LIST HANDLING (VERY IMPORTANT):
{ENGLISH_LIST_EXTRACTION_RULES}
- Return clean lists, one item per line, when the context supports them.

DEFINITION / PERSON QUESTIONS:
For "what is" or "who is": return 1–2 short, friendly sentences ONLY.

If the question is a greeting, respond naturally and warmly.
"""
CONVERSATIONAL_REDIRECT_EN = (
    "Thank you for reaching out. I'm here and ready to help with your support questions "
    "based on our knowledge base—for example, password reset, returns, or shipping. "
    "What can I help you with today?"
)
CONVERSATIONAL_REDIRECT_AR = (
    "شكراً لتواصلك معنا. أنا هنا وجاهز للمساعدة في أسئلة الدعم وفق قاعدة المعرفة—"
    "مثل إعادة تعيين كلمة المرور، الإرجاع، أو الشحن. بماذا يمكنني مساعدتك اليوم؟"
)
CONVERSATIONAL_LISTENING_EN = (
    "Yes, I can hear you loud and clear. I'm your support assistant and I'm here to help. "
    "What would you like to ask about today?"
)
CONVERSATIONAL_LISTENING_AR = (
    "نعم، أسمعك بوضوح. أنا مساعد الدعم الخاص بك وأنا هنا للمساعدة. "
    "ماذا تود أن تسأل عنه اليوم؟"
)
CONVERSATIONAL_PRESENCE_EN = (
    "Yes, I'm here with you and I received your message. How can I help you today?"
)
CONVERSATIONAL_PRESENCE_AR = (
    "نعم، أنا معك واستلمت رسالتك. كيف يمكنني مساعدتك اليوم؟"
)
CONVERSATIONAL_UNDERSTANDING_EN = (
    "Yes, I understand you. Please tell me what you need help with, and I'll do my best "
    "to assist using our support knowledge base."
)
CONVERSATIONAL_UNDERSTANDING_AR = (
    "نعم، أفهمك. من فضلك أخبرني بما تحتاج المساعدة فيه، وسأبذل قصارى جهدي "
    "للمساعدة باستخدام قاعدة معرفة الدعم."
)
CONVERSATIONAL_ONLINE_EN = (
    "Yes, I'm online and available to help. What support question can I answer for you?"
)
CONVERSATIONAL_ONLINE_AR = (
    "نعم، أنا متصل ومتاح للمساعدة. ما سؤال الدعم الذي يمكنني الإجابة عنه؟"
)
ASSISTANT_META_RESPONSE_EN = (
    "Hello! I'm your Assistify support assistant. I answer questions using your uploaded "
    "support documents and knowledge base—for example, account help, returns, or shipping. "
    "What would you like help with?"
)
ASSISTANT_META_RESPONSE_AR = (
    "مرحباً! أنا مساعد دعم Assistify. أجيب على الأسئلة باستخدام مستندات الدعم وقاعدة "
    "المعرفة المرفوعة—مثل مساعدة الحساب، الإرجاع، أو الشحن. بماذا تود المساعدة؟"
)
ASSISTANT_META_DOCUMENT_ONLY_EN = (
    "I'm happy to explain. I answer from your uploaded support documents and knowledge base "
    "so information stays accurate. Ask me about a topic in those materials—for example, "
    "password reset or returns—and I'll help right away."
)
ASSISTANT_META_DOCUMENT_ONLY_AR = (
    "يسعدني أن أوضح. أجيب من مستندات الدعم وقاعدة المعرفة المرفوعة لضمان دقة المعلومات. "
    "اسألني عن موضوع موجود فيها—مثل إعادة تعيين كلمة المرور أو الإرجاع—وسأساعدك فوراً."
)
ASSISTANT_META_NOT_FOUND_BEHAVIOR_EN = (
    "I understand that response can feel unhelpful. When something isn't in our knowledge base "
    "documents, I have to say so rather than guess. Try rephrasing your question or ask about "
    "a topic in your support materials—I'm here to help."
)
ASSISTANT_META_NOT_FOUND_BEHAVIOR_AR = (
    "أتفهم أن هذا الرد قد يبدو غير مفيد. عندما لا يكون الموضوع في مستندات قاعدة المعرفة، "
    "يجب أن أخبرك بذلك بدلاً من التخمين. جرّب إعادة صياغة سؤالك أو اسأل عن موضوع في "
    "مواد الدعم—أنا هنا للمساعدة."
)
RAG_GUARD_MODE_VERSION = "two-stage-mild-v3"
RAG_OLD_STRICT_07_ACTIVE = False

# Ollama direct URL â€” all LLM calls go here, main_llm_server.py is NOT used
OLLAMA_API_URL = f"http://{OLLAMA_HOST}:{OLLAMA_PORT}/api/chat"

