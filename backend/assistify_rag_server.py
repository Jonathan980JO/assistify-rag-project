import os
import warnings
import uuid
import json
import asyncio
import logging
import backend.sqlite_compat  # noqa: F401 — patches sys.modules["sqlite3"] if needed
import sqlite3
import math
from datetime import datetime, timezone
from urllib.parse import urlsplit
from pathlib import Path
from collections import defaultdict, Counter
from contextlib import asynccontextmanager, contextmanager
from threading import RLock

# Force UTF-8 on the Windows console so Unicode chars in retrieved chunks
# never crash a debug print statement.
import sys as _sys
if hasattr(_sys.stdout, "reconfigure"):
    try:
        _sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(_sys.stderr, "reconfigure"):
    try:
        _sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

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
# --- Phase 8H refactor: block extracted to backend.retrieval.generation, bound to this live
# module via bind_server so extracted helpers reach shared state/engine fns.
from backend.retrieval import generation as _ext_mod_generation
_ext_mod_generation.bind_server(_sys.modules[__name__])
from backend.retrieval.generation import (
    ARABIC_GENERAL_TOPICS,
    RAG_DOC_MODE,
    _AR_EN_CACHE_MAX,
    _AR_NON_LLM_QUERY_CACHE_MAX,
    _LATIN_PROPER_NAME_RE,
    _PROTECTED_QUOTED_TERM_RE,
    _SIMPLE_RAG_CACHE_MAX,
    _SIMPLE_RAG_CACHE_TTL_S,
    os,
    _ar_non_llm_query_cache_get,
    _ar_non_llm_query_cache_key,
    _ar_non_llm_query_cache_put,
    _ar_non_llm_query_cache_update_strength,
    _assess_native_arabic_retrieval,
    _best_doc_rank_score,
    _classify_arabic_query_type,
    _current_doc_context_key,
    _doc_contains_exact_query_term,
    _doc_text_for_exact_match,
    _docs_contain_all_protected_terms,
    _extract_protected_exact_query_terms,
    _filter_docs_by_protected_terms,
    _format_generation_answer_by_query,
    _has_arabic_latin_token_mix,
    _has_exact_phrase_and_grounding,
    _is_arabic_small_talk,
    _is_clean_cached_arabic_translation,
    _is_generation_bypass_query,
    _is_llm_generation_query,
    _looks_like_arabic_list_query,
    _native_arabic_retrieval_queries,
    _normalize_arabic_query_surface,
    _resolve_grounded_answer_route,
    _rewrite_generation_query_for_grounded_llm,
    _select_generation_context_docs,
    _select_list_context_docs,
    _set_last_latency_breakdown,
    _simple_rag_cache_get,
    _simple_rag_cache_put,
    _translation_cache_get,
    _translation_cache_put,
)
# --- Phase 8H refactor: block extracted to backend.core.startup, bound to this live
# module via bind_server so extracted helpers reach shared state/engine fns.
from backend.core import startup as _ext_mod_startup
_ext_mod_startup.bind_server(_sys.modules[__name__])
from backend.core.startup import (
    ASSETS_DIR,
    INGEST_INDEX_TIMEOUT_S,
    _RECENTLY_DELETED_TTL_S,
    _assets_reindex_locks,
    os,
    _assets_reindex_skip_reason,
    _assets_watcher,
    _bootstrap_assets_index_if_needed,
    _debounced_reindex,
    _extract_text_from_asset,
    _is_recently_deleted,
    _is_upload_pipeline_owned,
    _log_assets_reindex_skip,
    _mark_assets_recently_indexed,
    _mark_recently_deleted,
    _mark_upload_pipeline_owned,
    _normalize_filename_for_tombstone,
    _ownership_keys_for_filename,
    _pick_verification_snippet,
    _queue_assets_reindex,
    _rebuild_active_sources_from_collection,
    _reindex_file_auto,
    _should_skip_assets_reindex,
)
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
    sys.modules['posthog'] = _PosthogStub()  # type: ignore[assignment]
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException, status, Request, UploadFile, File, Body
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse, Response, StreamingResponse
from passlib.context import CryptContext
from itsdangerous import URLSafeSerializer
from pydantic import BaseModel
from typing import Optional, TYPE_CHECKING, List, Set, Dict, Tuple, Any, Union, Callable, Awaitable, cast
###############################
###############################
# MCP/Undefined Symbol Fixes  #
###############################
# Timeouts and memory guard constants (tune as needed)
# --- Phase 8H refactor: block extracted to backend.services.streaming_service, bound to this live
# module via bind_server so extracted helpers reach shared state/engine fns.
from backend.services import streaming_service as _ext_mod_streaming_service
_ext_mod_streaming_service.bind_server(_sys.modules[__name__])
from backend.services.streaming_service import (
    ARABIC_OFF_TOPIC_RESPONSE,
    LLM_FALLBACK_TOTAL_TIMEOUT_S,
    STREAM_TOTAL_TIMEOUT_S,
    WS_FINALIZE_TIMEOUT_S,
    _ARABIC_OPENER_PHRASE,
    _ARABIC_OPENER_PHRASES,
    _DETERMINISTIC_DEFINITION_ANSWER_TYPES,
    _DETERMINISTIC_LIST_ANSWER_TYPES,
    _emit_perf_report,
    _normalize_digits_for_tts,
    call_llm_streaming,
    send_final_response,
)
SAFE_UNBLOCK_CPU_MB = 2000
SAFE_UNBLOCK_GPU_MB = 2000
GPU_GROWTH_DELTA_MB = 200
GPU_HIGH_WATER_MB = 4000
MEMORY_GROWTH_LIMIT = 3
CPU_GROWTH_DELTA_MB = 500
CPU_HIGH_WATER_MB = 4000
COLLECTION_MUTATION_LOCK_TIMEOUT_S = float(os.environ.get("COLLECTION_MUTATION_LOCK_TIMEOUT_S", "120"))
KB_PIPELINE_STALE_TIMEOUT_S = float(os.environ.get("KB_PIPELINE_STALE_TIMEOUT_S", "600"))

# Memory snapshot helpers (stub: return dummy values, real impl should use psutil/torch)
def _get_memory_snapshot():
    return {
        'gpu_reserved_mb': 0,
        'gpu_allocated_mb': 0,
        'cpu_rss_mb': 0
    }

async def _get_stable_memory_snapshot():
    # In real code, wait for memory to stabilize, here just return snapshot
    return _get_memory_snapshot()

def _focus_doc_to_query_window(query: str, text: str, window: int = 700) -> str:
    if not text:
        return text

    logger = logging.getLogger(__name__)
    q = re.sub(r"\s+", " ", str(query or "").strip().lower())
    t = text
    original_len = len(t)

    intro_heading_re = re.compile(
        r"(?im)^\s*(?:introduction|overview|summary|contents?|table\s+of\s+contents|chapter\s+\d+|unit\s+\d+|learning\s+objectives?|key\s+terms?)\s*[:\-–—]?\s*$"
    )
    is_definition_query = bool(re.match(r"^\s*(?:what\s+is|what\s+are|define|who\s+is|who\s+was|who\s+introduced)\b", q))

    stopwords = {
        "a", "an", "the", "is", "are", "was", "were", "be", "being", "been", "to", "of", "in", "on", "at", "for", "from", "by", "and", "or", "as", "with", "about", "this", "that", "these", "those", "what", "which", "who", "whom", "whose", "when", "where", "why", "how", "do", "does", "did", "can", "could", "would", "should", "tell", "me", "explain", "describe"
    }

    def _query_tokens(qs: str) -> list[str]:
        toks = [tok for tok in re.findall(r"[a-z0-9]{2,}", qs) if tok not in stopwords]
        out: list[str] = []
        seen: set[str] = set()
        for tok in toks:
            if tok in seen:
                continue
            seen.add(tok)
            out.append(tok)
        return out

    q_tokens = _query_tokens(q)
    q_token_set = set(q_tokens)

    def _line_overlap(line: str) -> int:
        if not q_token_set:
            return 0
        ll = str(line or "").lower()
        return sum(1 for tok in q_token_set if re.search(rf"\b{re.escape(tok)}\b", ll))

    def _is_structured_line(line: str) -> bool:
        if not line:
            return False
        if re.search(r"^\s*(?:[-•*]|\d+[.)])\s+", line):
            return True
        if re.search(r"\|\s*[^|]+\s*\|", line):
            return True
        if re.search(r"(?:\b[A-Z][\w\-]{2,}\b\s*,\s*){2,}\b[A-Z][\w\-]{2,}\b", line):
            return True
        return False

    line_entries: list[Tuple[int, int, str]] = []
    pos = 0
    for ln in t.splitlines():
        start = pos
        end = start + len(ln)
        line_entries.append((start, end, ln))
        pos = end + 1
    if not line_entries:
        line_entries = [(0, len(t), t)]

    min_window = max(int(window), 700)
    list_detected = False
    trimming_applied = False
    used_full_chunk = False

    def _structured_density(start_idx: int, end_idx: int) -> float:
        seg = line_entries[max(0, start_idx): min(len(line_entries), end_idx)]
        non_empty = [ln for _s, _e, ln in seg if ln.strip()]
        if not non_empty:
            return 0.0
        structured = sum(1 for _s, _e, ln in seg if _is_structured_line(ln))
        return structured / max(1, len(non_empty))

    def _ensure_min_bounds(start: int, end: int, desired: int) -> Tuple[int, int]:
        cur_len = end - start
        if cur_len >= desired:
            return start, end
        need = desired - cur_len
        expand_left = need // 2
        expand_right = need - expand_left
        new_start = max(0, start - expand_left)
        new_end = min(len(t), end + expand_right)
        return new_start, new_end

    figure_match_found = False
    figure_match_position = None
    focus_override_used = False
    try:
        caption_re = re.compile(r"^\s*(?:fig(?:ure)?|table)\s*(?:\d+[A-Za-z]?)?\s*[:.\-]?", re.IGNORECASE)
        best_caption: tuple[float, int, int] | None = None
        for idx, (s, e, ln) in enumerate(line_entries):
            if not caption_re.match(ln):
                continue
            overlap = _line_overlap(ln)
            density = _structured_density(idx + 1, idx + 14)
            local_overlap = 0
            for _s2, _e2, ln2 in line_entries[idx + 1: idx + 8]:
                local_overlap += _line_overlap(ln2)
            score = (2.0 * overlap) + (1.25 * local_overlap) + (3.0 * density)
            if best_caption is None or score > best_caption[0]:
                best_caption = (score, idx, s)

        if best_caption and best_caption[0] > 1.0:
            figure_match_found = True
            figure_match_position = best_caption[2]
            start = best_caption[2]
            seen_structured = False
            non_struct_run = 0
            end = min(len(t), start + max(min_window, 1400))
            for _idx2 in range(best_caption[1] + 1, min(len(line_entries), best_caption[1] + 90)):
                _s2, _e2, ln2 = line_entries[_idx2]
                if _is_structured_line(ln2):
                    seen_structured = True
                    non_struct_run = 0
                    end = _e2
                    continue
                if not ln2.strip():
                    non_struct_run += 1
                elif len(ln2.strip()) <= 90 and re.match(r"^[A-Z][A-Za-z0-9\- ,:]{2,90}$", ln2.strip()):
                    non_struct_run += 1
                    end = _e2
                else:
                    non_struct_run += 1
                    if not seen_structured:
                        end = _e2
                if seen_structured and non_struct_run >= 3:
                    break
                if (_e2 - start) > max(min_window, 4200):
                    break
            start, end = _ensure_min_bounds(start, end, min_window)
            focus_override_used = True
            final_preview = t[start:end]
            logger.info(
                "figure_match_found=%s figure_match_position=%s focus_override_used=%s final_focus_preview=%s",
                figure_match_found,
                figure_match_position,
                focus_override_used,
                (final_preview[:200] + "...") if len(final_preview) > 200 else final_preview,
            )
            return final_preview
    except Exception:
        figure_match_found = False
        figure_match_position = None
        focus_override_used = False

    line_scores: list[tuple[float, int, int, int]] = []
    for idx, (s, e, ln) in enumerate(line_entries):
        stripped = ln.strip()
        if not stripped:
            continue
        overlap = _line_overlap(ln)
        structure_bonus = 1.2 if _is_structured_line(ln) else 0.0
        neighborhood_overlap = 0
        for _s2, _e2, ln2 in line_entries[max(0, idx - 2): min(len(line_entries), idx + 3)]:
            neighborhood_overlap += _line_overlap(ln2)
        density_bonus = 1.0 * _structured_density(idx - 2, idx + 6)
        junk_penalty = 1.2 if intro_heading_re.search(ln) else 0.0
        if is_definition_query and intro_heading_re.search(ln):
            junk_penalty += 0.8
        score = (2.3 * overlap) + (0.9 * neighborhood_overlap) + structure_bonus + density_bonus - junk_penalty
        line_scores.append((score, idx, s, e))

    if line_scores:
        line_scores.sort(key=lambda x: x[0], reverse=True)
        best_score, anchor_idx, anchor_start, anchor_end = line_scores[0]
        if best_score <= 0.0:
            anchor_idx, anchor_start, anchor_end = 0, 0, min(len(t), window)
            for idx, (s, e, ln) in enumerate(line_entries):
                if ln.strip() and not intro_heading_re.search(ln):
                    anchor_idx, anchor_start, anchor_end = idx, s, e
                    break
        start = max(0, anchor_start - 220)
        end = min(len(t), anchor_end + max(window, 900))

        anchor_structured = _is_structured_line(line_entries[anchor_idx][2])
        if _is_list_query(q) or anchor_structured or _structured_density(anchor_idx - 2, anchor_idx + 10) >= 0.35:
            list_detected = True
            non_struct_run = 0
            for _idx2 in range(anchor_idx, min(len(line_entries), anchor_idx + 100)):
                _s2, _e2, ln2 = line_entries[_idx2]
                if _is_structured_line(ln2):
                    end = max(end, _e2)
                    non_struct_run = 0
                elif not ln2.strip():
                    non_struct_run += 1
                else:
                    non_struct_run += 1
                    if _line_overlap(ln2) > 0:
                        end = max(end, _e2)
                if non_struct_run >= 3 and (_e2 - anchor_start) > 800:
                    break
                if (_e2 - anchor_start) > max(min_window, 4200):
                    break
            start, end = _ensure_min_bounds(start, end, min_window)

        focused = t[start:end]
        trimming_applied = True
        logger.info("FOCUS: original_len=%d focused_len=%d fallback=false (generic-anchor)", original_len, len(focused))
        logger.info("FOCUS DEBUG: list_detected=%s trimming_applied=%s used_full_chunk=%s", list_detected, trimming_applied, used_full_chunk)
        return focused

    final_window = max(window, min_window)
    focused = t[:final_window]
    if len(focused) < 1200 and len(t) > len(focused):
        used_full_chunk = False
        logger.warning("FOCUS WINDOW TOO SMALL → FALLBACK USED (original=%d focused=%d)", original_len, len(focused))
        logger.info("FOCUS DEBUG: list_detected=%s trimming_applied=%s used_full_chunk=%s (last-resort fallback)", list_detected, trimming_applied, used_full_chunk)
        return focused
    trimming_applied = True
    logger.info("FOCUS: original_len=%d focused_len=%d fallback=false (last-resort)", original_len, len(focused))
    logger.info("FOCUS DEBUG: list_detected=%s trimming_applied=%s used_full_chunk=%s", list_detected, trimming_applied, used_full_chunk)
    return focused

import io
import wave
import aiohttp
import torch
import time
import re
import random
import numpy as np
import psutil
import traceback
import backend.config_head as _config_head
from backend.config_head import *
from backend.voice_audio import register_voice_routes, init_voice_audio, shutdown_voice_audio, memory_guard
from backend.voice_audio import state as voice_state
from backend.voice_audio.ws.handler import create_rag_ws_handler
from backend.voice_audio.deps import VoiceWebSocketDeps
from backend.rag_middleware import rag_allowed_origins, verify_csrf
from config import BASE_URL, assert_production_config
from Login_system.session_validation import load_and_validate_session_token
from backend.voice_audio.tts.streaming import (
    cancel_active_ws_tts,
    tts_progressive_response,
    remember_ws_tts_task,
    client_tts_allowed as _client_tts_allowed,
)
# Names prefixed with '_' are not imported by `from ... import *`.
_ws_write_locks = getattr(_config_head, '_ws_write_locks', {}) or {}
import traceback

# --- Phase 8A refactor: config flags / Ollama URLs / preflight moved to
# backend.core.config. Re-imported here to preserve module-level names and
# behavior. These come after the `from backend.config_head import *` above so
# the LLM_URL override (= OLLAMA_CHAT_URL) matches the monolith's prior order.
from backend.core.config import (
    RAG_HYBRID_SEMANTIC_THRESHOLD,
    FACT_MAX_TOP_K,
    MAX_FACT_RETRIES,
    FACT_MAX_RESCUE_QUERIES,
    FACT_CONTEXT_MAX_SNIPPETS,
    FACT_CONTEXT_MAX_CHARS,
    _env_flag_enabled,
    _build_ollama_url,
    OLLAMA_CHAT_URL,
    OLLAMA_GENERATE_URL,
    OLLAMA_TAGS_URL,
    LLM_URL,
    OLLAMA_API_URL,
    ASSISTIFY_SAFE_MODE,
    ASSISTIFY_DISABLE_TTS,
    ASSISTIFY_DISABLE_RERANKER,
    ASSISTIFY_DISABLE_WHISPER,
    ASSISTIFY_DISABLE_WARMUP,
    ASSISTIFY_ENABLE_ENGLISH_TTS_WARMUP,
    ASSISTIFY_ENABLE_ARABIC_TTS_WARMUP,
    ASSISTIFY_ENABLE_TTS_OPENER_WARMUP,
    EFFECTIVE_DISABLE_TTS,
    EFFECTIVE_DISABLE_RERANKER,
    EFFECTIVE_DISABLE_WHISPER,
    EFFECTIVE_DISABLE_WARMUP,
    _system_preflight,
)

serializer = URLSafeSerializer(SESSION_SECRET)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Assistify")

# ========== MULTI-TENANCY: request tenant resolution ==========
# --- Phase 8B refactor: tenant context moved to backend.core.tenant_context.
# Re-imported here (after `from backend.config_head import *`) so the tenant-
# aware log_usage/log_kb_event wrappers keep shadowing the plain analytics
# functions, and all module-level names/behavior are preserved.
from backend.core.tenant_context import (
    _request_tenant_id,
    _current_user_query,
    _user_has_explicit_tenant,
    resolve_request_tenant,
    require_request_tenant,
    _TenantScope,
    current_tenant_id,
    log_usage,  # noqa: F811 (intentional shadow of config_head wildcard)
    log_kb_event,  # noqa: F811 (intentional shadow of config_head wildcard)
    analytics_scope_tenant,
)

# ========== CONVERSATION MEMORY ==========
conversation_history = defaultdict(list)
MAX_CONVERSATIONS = 1000  # Maximum number of conversations to keep in memory
MAX_CONVERSATION_AGE = 3600  # Maximum age of conversation in seconds (1 hour)
conversation_timestamps = {}  # Track last activity time for cleanup

# --- Phase 8C refactor: CONVERSATIONS_FILE / _conversation_store_lock and the
# conversation store + CRUD helpers moved to
# backend.services.conversation_service. Re-imported below to preserve names.

from backend import chat_store as _chat_store
from backend.tenant_access import (
    assert_chat_tenant_allowed,
    get_tenant_name,
    resolve_active_chat_tenant,
)


# --- Phase 1 refactor: pure text/time helpers moved to backend.utils.text ---
# _utc_now_iso, _dedup_preserve_order and _is_arabic_text now live in
# backend/utils/text.py. Re-imported here to preserve module-level names/behavior.
from backend.utils.text import _utc_now_iso, _dedup_preserve_order, _is_arabic_text


# --- Phase 8C refactor: conversation store + CRUD helpers moved to
# backend.services.conversation_service. Re-imported here to preserve all
# module-level names and behavior. The in-memory runtime maps and the
# follow-up/websocket-coupled memory helpers (delete_conversation,
# bind_conversation_memory, ...) stay below in this module.
from backend.services.conversation_service import (
    CONVERSATIONS_FILE,
    _conversation_store_lock,
    _empty_conversation_store,
    _ensure_conversation_store_file_unlocked,
    _ensure_conversation_store_file,
    _load_conversation_store_unlocked,
    _save_conversation_store_unlocked,
    _mutating_conversation_store,
    _load_conversation_store,
    _save_conversation_store,
    _find_conversation,
    _coerce_owner,
    _conv_tenant_of,
    _conversation_in_scope,
    _resolve_chat_tenant_id,
    set_conversation_active_tenant,
    _try_claim_ownerless_conversation,
    _stamp_conversation_scope,
    _conversation_title_from_text,
    _create_conversation_unlocked,
    create_conversation,
    get_or_create_conversation,
    list_conversations_summary,
    load_conversation_messages,
    append_conversation_message,
    _conversation_summary,
    rename_conversation,
    _history_from_conversation_messages,
)


def delete_conversation(conversation_id: str, tenant_id=None, owner: str | None = None) -> None:
    _chat_store.delete_conversation(conversation_id, owner=owner)
    conversation_history.pop(conversation_id, None)
    last_answer_state.pop(conversation_id, None)
    recent_grounded_definition_concepts.pop(conversation_id, None)
    conversation_timestamps.pop(conversation_id, None)
    logger.info("[CONV] deleted id=%s", conversation_id)


def delete_all_conversations(tenant_id=None, owner: str | None = None) -> int:
    """Delete every persisted conversation for the current owner."""
    deleted_ids: list[str] = []
    summaries = _chat_store.list_conversations_summary(owner=owner)
    deleted_ids = [str(s["id"]) for s in summaries if s.get("id")]
    count = _chat_store.delete_all_conversations(owner=owner)
    if not count:
        return 0
    for conv_id in deleted_ids:
        conversation_history.pop(conv_id, None)
        last_answer_state.pop(conv_id, None)
        recent_grounded_definition_concepts.pop(conv_id, None)
        conversation_timestamps.pop(conv_id, None)
        try:
            _last_good_answer_state.pop(conv_id, None)
        except Exception:
            pass
        try:
            _last_list_state.pop(conv_id, None)
        except Exception:
            pass
    logger.info("[CONV] deleted_all count=%s owner=%s", len(deleted_ids), owner)
    return len(deleted_ids)


def bind_conversation_memory(runtime_id: str, conversation_id: str) -> None:
    if not runtime_id or not conversation_id:
        return
    if conversation_id not in conversation_history:
        conversation_history[conversation_id] = _history_from_conversation_messages(conversation_id)
    conversation_history[runtime_id] = conversation_history[conversation_id]
    conversation_timestamps[runtime_id] = time.time()
    conversation_timestamps[conversation_id] = time.time()
    if conversation_id in last_answer_state:
        last_answer_state[runtime_id] = last_answer_state[conversation_id]
    else:
        last_answer_state.pop(runtime_id, None)
    if conversation_id in recent_grounded_definition_concepts:
        recent_grounded_definition_concepts[runtime_id] = recent_grounded_definition_concepts[conversation_id]
    else:
        recent_grounded_definition_concepts.pop(runtime_id, None)


def persist_runtime_memory(runtime_id: str, conversation_id: str) -> None:
    if not runtime_id or not conversation_id:
        return
    if runtime_id in conversation_history:
        conversation_history[conversation_id] = conversation_history[runtime_id]
    if runtime_id in last_answer_state:
        last_answer_state[conversation_id] = last_answer_state[runtime_id]
    else:
        last_answer_state.pop(conversation_id, None)
    if runtime_id in recent_grounded_definition_concepts:
        recent_grounded_definition_concepts[conversation_id] = recent_grounded_definition_concepts[runtime_id]
    else:
        recent_grounded_definition_concepts.pop(conversation_id, None)
    conversation_timestamps[conversation_id] = time.time()



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
        if conn_id in recent_grounded_definition_concepts:
            del recent_grounded_definition_concepts[conn_id]
        del conversation_timestamps[conn_id]


def clear_all_conversation_history(tenant_id: int | None = None):
    """Wipe in-memory conversation state so stale KB answers are never reused.

    When tenant_id is given, only connections bound to that business are cleared.
    Called automatically after a KB reindex to prevent the LLM from seeing
    old Q&A pairs that contradict the updated knowledge base.
    """
    if tenant_id is None:
        count = len(conversation_history)
        conversation_history.clear()
        conversation_timestamps.clear()
        try:
            last_answer_state.clear()
        except Exception:
            pass
        try:
            recent_grounded_definition_concepts.clear()
        except Exception:
            pass
        if count:
            logger.info(f"Cleared {count} conversation(s) after KB reindex")
        return

    conn_ids = [
        cid for cid, tid in _active_ws_tenants.items()
        if int(tid) == int(tenant_id)
    ]
    cleared = 0
    for conn_id in conn_ids:
        if conversation_history.pop(conn_id, None) is not None:
            cleared += 1
        conversation_timestamps.pop(conn_id, None)
        last_answer_state.pop(conn_id, None)
        try:
            _last_good_answer_state.pop(conn_id, None)
        except Exception:
            pass
        try:
            _last_list_state.pop(conn_id, None)
        except Exception:
            pass
        try:
            _ar_resolved_followup_queries.pop(conn_id, None)
        except Exception:
            pass
        try:
            if conn_id in recent_grounded_definition_concepts:
                del recent_grounded_definition_concepts[conn_id]
        except Exception:
            pass
    if cleared:
        logger.info(
            "Cleared %s in-memory conversation(s) for tenant=%s after KB reindex",
            cleared,
            tenant_id,
        )


# ========== FOLLOW-UP / EXPLANATION MODE ==========
# Per-connection cache of the most recently grounded answer so that
# follow-up clarifications ("what do you mean?", "explain more",
# "simplify that") can be answered locally WITHOUT re-running heavy
# retrieval. The system stays strictly grounded in the previously
# retrieved chunks + the previous answer text — no open-domain leakage.
last_answer_state: dict = {}
# P12C-1: separate stores that survive a single follow-up failure /
# not-found turn so Arabic memory-rewrite ("طيب اختصر أكثر") can still
# work on the previous useful grounded answer. Updated only by GROUNDED
# answers (never by the RAG_NO_MATCH_RESPONSE path), so a not-found does
# not destroy them. Cleared explicitly on a clear topic shift via the
# normal save path when a NEW grounded answer overwrites the entry.
_last_good_answer_state: dict = {}
_last_list_state: dict = {}
_ar_resolved_followup_queries: dict = {}
recent_grounded_definition_concepts = defaultdict(list)
# --- Phase 8H-1 refactor: follow-up / Arabic / memory-rewrite helpers moved
# to backend.retrieval.followup, bound to this live module via bind_server so
# the extracted helpers reach shared state and engine functions at call time.
from backend.retrieval import followup as _followup_mod
_followup_mod.bind_server(_sys.modules[__name__])
from backend.retrieval.followup import (
    _ABOUT_ENTITY_AR_PATTERNS,
    _ABOUT_ENTITY_EN_PATTERNS,
    _ABOUT_ENTITY_STOPWORDS,
    _ABOUT_ENTITY_VAGUE_TOKENS,
    _ARABIC_CHAR_RE,
    _AR_ANAPHOR_RE,
    _AR_FOLLOWUP_CONTEXT_RE,
    _AR_FOLLOWUP_STRONG_RE,
    _AR_ORDINAL_TO_INDEX,
    _AR_QUERY_STOPWORDS,
    _CONV_DEF_RE_ASK_PATTERNS,
    _CONV_LEAD_STRIP,
    _CONV_TRAIL_STRIP,
    _EVIDENCE_STOPWORDS,
    _EXPLAIN_VERB_RE,
    _FOLLOWUP_CHUNK_CHAR_BUDGET,
    _FOLLOWUP_CONTEXT_PATTERNS,
    _FOLLOWUP_COPYRIGHT_PREFIX_RE,
    _FOLLOWUP_COURSE_HEADER_RE,
    _FOLLOWUP_EXPLANATORY_CUE_RE,
    _FOLLOWUP_EXPL_GROUND_THRESHOLD,
    _FOLLOWUP_FRAGMENT_CLAUSE_RE,
    _FOLLOWUP_FRAGMENT_START_RE,
    _FOLLOWUP_GROUND_RATIO_MIN,
    _FOLLOWUP_INFERRED_SUFFIX,
    _FOLLOWUP_KEEP_TOP_K,
    _FOLLOWUP_LEADING_CONJUNCTION_RE,
    _FOLLOWUP_MAX_QUERY_LEN,
    _FOLLOWUP_NEW_QUESTION_PATTERNS,
    _FOLLOWUP_OCR_SPLIT_WORD_RE,
    _FOLLOWUP_ORDINAL_RE,
    _FOLLOWUP_ORDINAL_WORDS,
    _FOLLOWUP_ORPHAN_HEADER_TOKEN_RE,
    _FOLLOWUP_PAGE_PREFIX_RE,
    _FOLLOWUP_PATTERNS,
    _FOLLOWUP_SAVED_CHUNK_CHAR_LIMIT,
    _FOLLOWUP_SHORT_WORD_LIMIT,
    _FOLLOWUP_STATE_TTL,
    _FOLLOWUP_TARGET_STOPWORDS,
    _MEMORY_REFERENCE_WORDS_RE,
    _NEW_QUESTION_HEAD_RE,
    _OCR_MERGED_PREFIX_WORD_RE,
    _OCR_PREFIX_REMAINDER_SUFFIX_RE,
    _WEAK_GENERIC_REQUEST_RE,
    _append_conversation_turn,
    _build_arabic_item_explain_query,
    _build_consolidated_grounded_explanation,
    _build_followup_excerpts,
    _build_followup_list_context_mini_explanation,
    _build_followup_targeted_evidence_answer,
    _build_grounded_explanation,
    _build_grounded_explanations_for_items,
    _classify_followup_intent,
    _classify_memory_rewrite_intent,
    _cleanup_followup_extracted_answer,
    _compute_explanation_grounding_score,
    _evidence_has_explicit_explanation,
    _extract_about_entity_question,
    _extract_arabic_concept_from_query_surface,
    _extract_definition_concept_from_query_surface,
    _extract_focus_concept_from_explain_query_surface,
    _extract_focus_concept_from_explanatory_query_surface,
    _extract_followup_context_window,
    _extract_followup_items_from_answer,
    _extract_followup_strong_explanation,
    _extract_last_grounded_entities,
    _extract_recent_definition_concepts_from_history,
    _followup_capitalize_sentence_start,
    _followup_content_tokens,
    _followup_controlled_explanation,
    _followup_doc_chunk_index,
    _followup_doc_source,
    _followup_doc_text,
    _followup_expand_adjacent_chunks,
    _followup_explanation_candidate_score,
    _followup_fetch_adjacent_chunk,
    _followup_item_head,
    _followup_items_anchored,
    _followup_lexical_explanation_rescue,
    _followup_list_chunk_support_score,
    _followup_merge_safe_ocr_split_words,
    _followup_query_focus_phrase,
    _followup_query_surface_focus_phrase,
    _followup_salvage_fragment_clause,
    _followup_strip_header_prefix,
    _followup_text_has_item_head_anchor,
    _followup_text_mentions_item,
    _format_compare_memory_concepts,
    _get_last_answer_state,
    _get_marked_arabic_resolved_followup_reason,
    _handle_followup_query,
    _handle_memory_rewrite_query,
    _has_recent_followup_state,
    _infer_followup_answer_type,
    _infer_previous_list_relation_phrase,
    _is_arabic_followup_context,
    _is_arabic_followup_strong,
    _is_bare_comparison_followup_query,
    _is_followup_query,
    _is_marked_arabic_resolved_followup,
    _is_memory_rewrite_query,
    _is_undirected_explain_more,
    _is_weak_generic_request,
    _join_memory_items,
    _join_short_item_names,
    _limit_memory_lines,
    _limit_memory_rewrite_text,
    _mark_arabic_resolved_followup,
    _maybe_resolve_arabic_followup_reference,
    _maybe_rewrite_about_entity_question,
    _memory_item_summary_label,
    _normalize_conversational_definition_query,
    _resolve_and_mark_arabic_followup_for_ws,
    _resolve_arabic_ordinal_target_from_items,
    _resolve_followup_ordinal,
    _rewrite_bare_comparison_query_from_history,
    _rewrite_previous_answer_from_memory,
    _save_last_answer_state,
    _select_followup_target_item,
    _sentence_mentions_many_followup_items,
    _split_followup_explanation_sentences,
    _split_followup_sentences,
    _split_memory_answer_units,
    _split_safe_ocr_merged_prefix_words,
)
# Loose grounding ratio: paraphrased explanations legitimately use connector
# words and synonyms, so we only require a modest overlap with the saved
# prior-answer + saved chunks. Open-domain hallucinations still fall well
# below this floor in practice.

import re as _re_followup
# Generic, domain-agnostic intent patterns. They describe a request FOR
# clarification of a prior answer, not document content.
#
# Two tiers:
#  * STRONG: explicit clarification phrases that are unmistakable
#    follow-ups regardless of conversation history (e.g. "what do you
#    mean", "explain more", "rephrase that"). Always route as follow-up.
#  * CONTEXTUAL: clarification-shaped phrases that need an OBJECT and
#    only make sense as a follow-up when there IS a recent grounded
#    answer to clarify (e.g. "explain Money", "what does X mean",
#    "what about that", "tell me more about Y"). Routed as follow-up
#    ONLY when prior state exists for the connection.
#  * SHORT-CONTEXTUAL FALLBACK: a very short utterance (≤ 7 words) that
#    does NOT look like a brand-new question is treated as a follow-up
#    ONLY when prior state exists. Brand-new question shapes
#    ("what is X", "how", "why", "list ...", "define ...") are excluded
#    so a short standalone question still goes through full RAG.

# Contextual follow-up patterns. Match a clarification verb/phrase that
# carries an OBJECT referring back to the prior answer. They are only
# applied when the connection has a recent saved answer state.

# Brand-new question shapes — used to EXCLUDE from the short-utterance
# contextual fallback so a standalone short question still gets full
# retrieval. Domain-agnostic.


# ---- P12C-1: Arabic follow-up detection & pronoun/ordinal resolution ----
# Strong Arabic follow-up patterns: do not need prior state to qualify
# as a follow-up *intent*, but the actual handler still requires a saved
# answer to ground the response (so spurious matches without context
# return Not found, never fabricate). Strictly generic — no domain
# vocabulary, only pronouns / deictic / clarification verbs.

# Contextual Arabic follow-up patterns: only count as follow-up when
# there is a recent saved answer state (caller checks). These cover
# relationship/ordinal references back to the previous answer.

# Arabic anaphora/deictic words used by the short-utterance fallback so
# very short Arabic clarifications ("ها؟", "وهذا؟", "ذلك؟") do not get
# rejected when there is a real saved answer to refer to.
































# _dedup_preserve_order moved to backend/utils/text.py (Phase 1 refactor); imported above.




























# ---- Conversational definition normalization ----
# Rewrites natural conversational definition re-asks into the canonical
# "what is X?" form so the strong definition pipeline picks them up
# instead of the weak generic prose path. Strictly generic — no domain
# words, no entity allowlists.
# "what about (the )?(definition|meaning|concept|idea) of X"
# "what is the (definition|meaning|...) of X"
# "(definition|meaning|...) of X"
# "tell me (about )?the (definition|meaning) of X"




# ---- About-entity standalone-question rewrite ----
# Detects "what about X / how about X / and X / tell me about X / explain X"
# (and Arabic equivalents) where X clearly introduces a NEW content phrase
# rather than referring back to the previous answer. When detected, the
# query is rewritten into a canonical standalone form ("What is X?" / "ما
# هي X؟") so it goes through normal RAG retrieval instead of being
# inherited by the contextual follow-up router.
#
# Strictly generic — no domain word lists, no document-specific terms.


































# --------------- weak-evidence anti-inference guard helper ---------------
# Compiled once; used by _evidence_has_explicit_explanation.




# ---- controlled-explanation mode (follow-up only) -----------------------
# Suffix appended to LLM-inferred explanations so the user can tell the
# explanation was reconstructed from context rather than quoted from the
# document verbatim.

# Minimum fraction of content words in an LLM-generated explanation that
# must appear (whole-word) in the retrieved chunks or previous answer.
# Below this threshold the explanation is considered ungrounded and is
# replaced by a cautious placeholder.  Generic — no domain vocabulary.


























# "previous one" is ambiguous (could mean prior turn, not prior list item);
# "next one" is also ambiguous on a static list. We resolve only the
# unambiguous ordinals plus "last/final" -> tail of the list.






























































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
        ollama_url = _build_ollama_url("/api/chat")
        payload = {
            "model": OLLAMA_MODEL,
            "messages": [],
            "keep_alive": "0"
        }
        logger.info("[OLLAMA CALL] endpoint=%s model=%s query_type=cache_flush", ollama_url, OLLAMA_MODEL)
        async with _aiohttp.ClientSession() as _sess:
            async with _sess.post(ollama_url, json=payload, timeout=_aiohttp.ClientTimeout(total=10)) as resp:
                logger.info("[OLLAMA CALL RESULT] status=%s endpoint=%s", resp.status, ollama_url)
                logger.info(f"Ollama cache flush: status={resp.status} (model will reload on next query)")
    except Exception as e:
        logger.warning(f"Ollama cache flush failed (non-fatal): {e}")


async def _check_ollama_connectivity() -> None:
    tags_url = _build_ollama_url("/api/tags")
    local_session_created = False
    _sess = llm_session
    if _sess is None or getattr(_sess, "closed", False):
        local_session_created = True
        _sess = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8, connect=3, sock_read=5))

    try:
        async with _sess.get(tags_url) as resp:
            body_preview = (await resp.text())[:160]
            if resp.status == 200:
                logger.info("[OLLAMA CONNECTIVITY] success url=%s status=%s", tags_url, resp.status)
            else:
                logger.warning("[OLLAMA CONNECTIVITY] failed url=%s status=%s body=%s", tags_url, resp.status, body_preview)
    except Exception as exc:
        logger.warning("[OLLAMA CONNECTIVITY] failed url=%s reason=%s", tags_url, exc)
    finally:
        if local_session_created and _sess and not _sess.closed:
            await _sess.close()


# ========== IN-MEMORY RATE LIMITER ==========
# --- Phase 8D refactor: rate limiter and _kb_admin_scope_tenant moved to
# backend.services.kb_service. Re-imported here to preserve module-level names.
from backend.services.kb_service import (
    _rate_buckets,
    _rate_lock,
    _check_rate_limit,
    _kb_admin_scope_tenant,
)


# ========== REAL-TIME KB EVENT BROADCAST ==========
# All active user WebSocket connections (keyed by connection_id → WebSocket)
_active_ws_connections: dict = {}
# Tenant bound to each active WebSocket (connection_id → tenant_id)
_active_ws_tenants: dict[str, int] = {}
# Admin KB-events subscribers (WebSocket → tenant_id)
_kb_event_subscribers: dict = {}
# Global KB version counter — incremented on every mutation
_kb_global_version: int = 0


async def broadcast_kb_event(action: str, filename: str = "*",
                              chunks_added: int = 0, chunks_deleted: int = 0,
                              triggered_by: str = "admin", tenant_id: int | None = None):
    """Broadcast a KB mutation event to sockets for the same business only.

    Sends:
      - A ``kb_updated`` message to every active user chat session for this tenant
      - The full event payload to admin KB-events subscribers for this tenant
    """
    global _kb_global_version
    _kb_global_version += 1
    tid = int(tenant_id if tenant_id is not None else current_tenant_id())
    event = {
        "type": "kb_updated",
        "action": action,
        "filename": filename,
        "chunks_added": chunks_added,
        "chunks_deleted": chunks_deleted,
        "kb_version": _kb_global_version,
        "triggered_by": triggered_by,
        "tenant_id": tid,
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
        tenant_id=tid,
    )

    # Notify user chat WebSockets for this tenant only
    dead_conns = []
    for conn_id, ws in list(_active_ws_connections.items()):
        if int(_active_ws_tenants.get(conn_id, DEFAULT_TENANT_ID)) != tid:
            continue
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
        _active_ws_tenants.pop(conn_id, None)

    # Broadcast full event to admin KB-events subscribers for this tenant
    dead_subs = []
    for ws, sub_tid in list(_kb_event_subscribers.items()):
        if int(sub_tid) != tid:
            continue
        try:
            await ws.send_json(event)
        except Exception:
            dead_subs.append(ws)
    for ws in dead_subs:
        _kb_event_subscribers.pop(ws, None)

    logger.info(f"KB broadcast: action={action} file={filename} v{_kb_global_version} tenant={tid} "
                f"→ user sessions + admin subscribers for this tenant")


async def invalidate_all_caches(action: str = "cache_clear", filename: str = "*",
                                 chunks_added: int = 0, chunks_deleted: int = 0,
                                 triggered_by: str = "admin", tenant_id: int | None = None):
    """Nuclear option: clear conversation history + flush Ollama KV cache + broadcast.

    Call this after any KB mutation (upload, edit, delete, reindex) to
    guarantee the next user query gets a fully fresh answer.
    """
    tid = int(tenant_id if tenant_id is not None else current_tenant_id())
    clear_all_conversation_history(tenant_id=tid)
    await flush_ollama_cache()
    await broadcast_kb_event(action=action, filename=filename,
                              chunks_added=chunks_added, chunks_deleted=chunks_deleted,
                              triggered_by=triggered_by, tenant_id=tid)

_active_doc_registry: dict = {
    "mode": RAG_DOC_MODE,
    "active_sources": set(),
}

# Phase 13C: active sources are tracked per tenant. Retrieval is already
# collection-per-tenant isolated, so the anti-leak source filter must validate
# retrieved chunks against the SAME tenant's active-source set, never a global
# set shared across businesses (which previously caused one tenant's freshly
# uploaded document to be filtered out against another tenant's source list).
# The legacy `_active_doc_registry["active_sources"]` field is kept in sync for
# the default tenant for backward compatibility with any external reader.
_tenant_active_sources: "dict[int, set]" = {}

# Explicit ID of the single currently active document (normalized filename).
# Set to "" at startup; updated whenever a document is successfully indexed.
# Used as the single source of truth for the anti-leak source guard.
_current_active_doc_id: str = ""

_kb_pipeline_state: dict = {
    "state": "ready",  # uploading | processing | ready | failed
    "stage": "ready",  # uploading | extracting | chunking | embedding | writing | activating | ready | failed
    "message": "ready",
    "filename": None,
    "updated_at": time.time(),
    "started_at": None,
    "ready_at": None,
    "stage_timings": {},  # name -> seconds since started_at
    "last_total_seconds": None,
    "last_bottleneck": None,
    "indexed_chunks": 0,
    "total_chunks": 0,
    "percent": 100,
}


def _set_kb_pipeline_state(state: str, message: str = "", filename: Optional[str] = None) -> None:
    normalized = str(state or "").strip().lower()
    if normalized not in {"uploading", "processing", "ready", "failed"}:
        normalized = "processing"
    _kb_pipeline_state["state"] = normalized
    _kb_pipeline_state["stage"] = "uploading" if normalized == "uploading" else ("ready" if normalized == "ready" else ("failed" if normalized == "failed" else _kb_pipeline_state.get("stage", "processing")))
    _kb_pipeline_state["message"] = str(message or normalized)
    _kb_pipeline_state["filename"] = filename
    _kb_pipeline_state["updated_at"] = time.time()
    if normalized == "uploading":
        # Reset per-upload timing on a fresh upload start.
        _kb_pipeline_state["started_at"] = time.time()
        _kb_pipeline_state["ready_at"] = None
        _kb_pipeline_state["stage_timings"] = {}
        _kb_pipeline_state["last_total_seconds"] = None
        _kb_pipeline_state["last_bottleneck"] = None
        _kb_pipeline_state["indexed_chunks"] = 0
        _kb_pipeline_state["total_chunks"] = 0
        _kb_pipeline_state["percent"] = 0
    elif normalized == "ready":
        now = time.time()
        _kb_pipeline_state["ready_at"] = now
        _kb_pipeline_state["percent"] = 100
        started = _kb_pipeline_state.get("started_at") or now
        _kb_pipeline_state["last_total_seconds"] = round(now - started, 3)
        timings = _kb_pipeline_state.get("stage_timings") or {}
        if timings:
            # Largest per-stage delta is the bottleneck.
            ordered = sorted(timings.items(), key=lambda kv: kv[1])
            deltas = []
            prev = 0.0
            for name, t in ordered:
                deltas.append((name, round(t - prev, 3)))
                prev = t
            if deltas:
                _kb_pipeline_state["last_bottleneck"] = max(deltas, key=lambda kv: kv[1])
    logger.info(
        "KB pipeline state | state=%s filename=%s message=%s",
        normalized,
        filename,
        _kb_pipeline_state["message"],
    )


def _record_kb_stage(stage: str) -> None:
    """Record a named pipeline stage timestamp (seconds since 'uploading' start)."""
    started = _kb_pipeline_state.get("started_at")
    if not started:
        return
    timings = _kb_pipeline_state.setdefault("stage_timings", {})
    timings[str(stage)] = round(time.time() - float(started), 3)


def _set_kb_pipeline_stage(
    stage: str,
    message: str = "",
    filename: Optional[str] = None,
    indexed: Optional[int] = None,
    total: Optional[int] = None,
    percent: Optional[int] = None,
) -> None:
    normalized_stage = str(stage or "").strip().lower()
    if normalized_stage not in {"uploading", "extracting", "chunking", "embedding", "writing", "activating", "ready", "failed"}:
        normalized_stage = "processing"
    if normalized_stage == "ready":
        _set_kb_pipeline_state("ready", message=message or "ready", filename=filename)
    elif normalized_stage == "failed":
        _set_kb_pipeline_state("failed", message=message or "failed", filename=filename)
    elif normalized_stage == "uploading":
        _set_kb_pipeline_state("uploading", message=message or "uploading", filename=filename)
    else:
        _kb_pipeline_state["state"] = "processing"
        _kb_pipeline_state["stage"] = normalized_stage
        _kb_pipeline_state["message"] = str(message or normalized_stage)
        if filename is not None:
            _kb_pipeline_state["filename"] = filename
        _kb_pipeline_state["updated_at"] = time.time()
    if indexed is not None:
        _kb_pipeline_state["indexed_chunks"] = int(indexed)
    if total is not None:
        _kb_pipeline_state["total_chunks"] = int(total)
    # Keep progress counters consistent during ingestion.
    _idx = _kb_pipeline_state.get("indexed_chunks")
    _tot = _kb_pipeline_state.get("total_chunks")
    if isinstance(_idx, int) and isinstance(_tot, int) and _tot > 0 and _idx > _tot:
        _kb_pipeline_state["indexed_chunks"] = _tot
    if percent is not None:
        _kb_pipeline_state["percent"] = max(0, min(100, int(percent)))
    _record_kb_stage(normalized_stage)


# --- Phase 8E refactor: _on_ingest_progress moved to
# backend.services.ingestion_service (re-imported to preserve the name).
from backend.services.ingestion_service import _on_ingest_progress


def _kb_is_ready_for_queries() -> Tuple[bool, str]:
    state = str(_kb_pipeline_state.get("state") or "ready").lower()
    if state == "ready":
        return True, "ready"
    return False, str(_kb_pipeline_state.get("message") or state)


def _normalize_source_label(value: str) -> str:
    import re as _re
    cleaned = str(value or "").strip()
    if not cleaned:
        return ""
    cleaned = _re.sub(r"^[0-9a-fA-F]{8}_", "", cleaned)
    return cleaned.lower()


def _resolve_active_source_tenant(tenant_id=None) -> int:
    """Resolve the tenant id whose active-source bucket a call should touch.

    Defaults to the tenant bound to the current request context so the
    anti-leak filter always validates against the same business whose
    collection was queried."""
    try:
        return int(tenant_id if tenant_id is not None else current_tenant_id())
    except (TypeError, ValueError):
        return int(DEFAULT_TENANT_ID)


def _set_active_sources(sources: List[str], mode: Optional[str] = None, tenant_id=None) -> None:
    if mode:
        normalized_mode = (mode or "").strip().lower()
        if normalized_mode in {"single", "multi"}:
            _active_doc_registry["mode"] = normalized_mode
    tid = _resolve_active_source_tenant(tenant_id)
    normalized = {_normalize_source_label(s) for s in (sources or []) if _normalize_source_label(s)}
    _tenant_active_sources[tid] = normalized
    if tid == int(DEFAULT_TENANT_ID):
        _active_doc_registry["active_sources"] = normalized
    logger.info(
        "RAG active docs updated | tenant=%s mode=%s active_sources=%s",
        tid,
        _active_doc_registry.get("mode"),
        sorted(normalized),
    )


def _source_aliases_from_metadata(metadata: Optional[Dict[Any, Any]], *fallbacks: str) -> Set[str]:
    aliases = set(_metadata_source_keys(metadata or {}))
    for fallback in fallbacks:
        normalized = _normalize_source_label(fallback)
        if normalized:
            aliases.add(normalized)
    return aliases


def _register_active_source_aliases(sources: List[str], tenant_id=None) -> None:
    normalized = {_normalize_source_label(s) for s in (sources or []) if _normalize_source_label(s)}
    if not normalized:
        return
    tid = _resolve_active_source_tenant(tenant_id)
    mode = _active_doc_registry.get("mode", RAG_DOC_MODE)
    current = set(_tenant_active_sources.get(tid) or set())
    if mode == "single":
        current = normalized
    else:
        current.update(normalized)
    _tenant_active_sources[tid] = current
    if tid == int(DEFAULT_TENANT_ID):
        _active_doc_registry["active_sources"] = current
    logger.info(
        "RAG active source aliases registered | tenant=%s mode=%s aliases=%s active_sources=%s",
        tid,
        mode,
        sorted(normalized),
        sorted(current),
    )


def _register_active_source(source_name: str, tenant_id=None) -> None:
    normalized = _normalize_source_label(source_name)
    if not normalized:
        return
    _register_active_source_aliases([normalized], tenant_id=tenant_id)


def _get_active_sources(tenant_id=None) -> Set[str]:
    tid = _resolve_active_source_tenant(tenant_id)
    return set(_tenant_active_sources.get(tid) or set())


def _metadata_source_keys(metadata: Optional[Dict[Any, Any]]) -> Set[str]:
    md = metadata or {}
    candidates = {
        str(md.get("source_doc_id") or "").strip(),
        str(md.get("source_name") or "").strip(),
        str(md.get("original_filename") or "").strip(),
        str(md.get("stored_filename") or "").strip(),
        str(md.get("normalized_filename") or "").strip(),
        str(md.get("source") or "").strip(),
        str(md.get("filename") or "").strip(),
        str(md.get("source_filename") or "").strip(),
        str(md.get("file") or "").strip(),
        str(md.get("doc_id") or "").strip(),
        str(md.get("document_id") or "").strip(),
        str(md.get("base_doc_id") or "").strip(),
    }
    keys = set()
    for c in candidates:
        n = _normalize_source_label(c)
        if n:
            keys.add(n)
    return keys


# #region agent log
def _dbg7d3bbb(location, message, data=None, hypothesis=None):
    try:
        import json as _json, time as _time
        _rec = {
            "sessionId": "7d3bbb",
            "runId": "run1",
            "hypothesisId": hypothesis,
            "location": location,
            "message": message,
            "data": data or {},
            "timestamp": int(_time.time() * 1000),
        }
        _log_path = Path(__file__).resolve().parent.parent / "logs" / "debug-7d3bbb.log"
        _log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(
            _log_path,
            "a",
            encoding="utf-8",
        ) as _f:
            _f.write(_json.dumps(_rec, default=str) + "\n")
    except Exception:
        pass
# #endregion


def _filter_results_to_active_sources(results: List[Dict[Any, Any]]) -> List[Dict[Any, Any]]:
    _diag_tenant = _resolve_active_source_tenant()
    active_sources = _get_active_sources()
    if not active_sources:
        # Attempt to recover active sources from the (current tenant's) collection
        # before failing closed.
        try:
            _rebuild_active_sources_from_collection(tenant_id=_diag_tenant)
            active_sources = _get_active_sources()
        except Exception:
            pass
        if not active_sources:
            logger.warning(
                "No active sources configured — failing closed to prevent cross-document leakage. tenant=%s in_count=%s",
                _diag_tenant,
                len(results or []),
            )
            _dbg7d3bbb("assistify_rag_server.py:_filter_results_to_active_sources", "no active_sources -> fail closed",
                       {"in_count": len(results or []), "active_sources_count": 0}, "H-C")
            return []
    filtered = []
    items_without_source_keys = 0
    retrieved_keys: Set[str] = set()
    removed_keys: Set[str] = set()
    for item in results or []:
        md = (item or {}).get("metadata") or {}
        item_keys = _metadata_source_keys(md)
        retrieved_keys |= item_keys
        if not item_keys:
            # Chunks without any source identity are orphans — never pass them through.
            items_without_source_keys += 1
            continue
        if item_keys & active_sources:
            filtered.append(item)
        else:
            removed_keys |= item_keys
    # Phase 13C temporary diagnostic: surface every set involved in the filter so
    # a fail-closed event can be traced to a tenant/source mismatch immediately.
    remaining_keys = {k for d in filtered for k in _metadata_source_keys((d or {}).get("metadata") or {})}
    logger.info(
        "[ACTIVE-SOURCE DIAG] tenant=%s retrieved=%s active=%s remaining=%s "
        "retrieved_sources=%s active_sources=%s filtered_sources=%s "
        "removed_sources=%s remaining_sources=%s",
        _diag_tenant,
        len(results or []),
        len(active_sources),
        len(filtered),
        sorted(retrieved_keys)[:12],
        sorted(active_sources)[:12],
        sorted(remaining_keys)[:12],
        sorted(removed_keys)[:12],
        sorted(remaining_keys)[:12],
    )
    _dbg7d3bbb("assistify_rag_server.py:_filter_results_to_active_sources", "active-source filter result",
               {"in_count": len(results or []), "kept": len(filtered),
                "active_sources_count": len(active_sources),
                "active_sources": sorted(active_sources)[:8],
                "no_key_items": items_without_source_keys}, "H-C")
    if items_without_source_keys:
        logger.warning(
            "Active-source filter dropped orphan chunks (no source keys): active_sources=%s orphans=%s",
            sorted(active_sources),
            items_without_source_keys,
        )
    if not filtered:
        logger.warning(
            "Active-source filter returned nothing — failing closed. tenant=%s active_sources=%s total=%s removed_sources=%s",
            _diag_tenant,
            sorted(active_sources),
            len(results or []),
            sorted(removed_keys)[:12],
        )
    return filtered
    logger.info("All caches invalidated (conversations + Ollama KV cache)")


# --- Phase 8H refactor: block extracted to backend.retrieval.lists, bound to this live
# module via bind_server so extracted helpers reach shared state/engine fns.
from backend.retrieval import lists as _ext_mod_lists
_ext_mod_lists.bind_server(_sys.modules[__name__])
from backend.retrieval.lists import (
    _DOC_ROUTER_COMPARISON_OPERATORS,
    _DOC_ROUTER_STOPWORDS,
    _DOC_ROUTER_VAGUE_TERMS,
    _SPOKEN_SINGLE_LETTER_NAMES,
    _SYMBOLIC_LIST_CATEGORY_WORDS,
    _build_counted_list_rescue_context,
    _classify_response_format_intent,
    _clean_counted_list_label_item,
    _detect_short_symbolic_list_query,
    _doc_router_concept_hit,
    _doc_router_cross_corpus_bridge,
    _doc_router_explicit_multi_source_request,
    _doc_router_implies_comparison,
    _doc_router_interleave_docs,
    _doc_router_normalized_query_tokens,
    _doc_router_query_is_ambiguous,
    _enforce_unanswerable_detail_refusal,
    _ensure_bridge_source_signals,
    _extract_counted_list_labels_from_context,
    _extract_doc_router_query_concepts,
    _extract_symbolic_list_lexical_rescue_answer,
    _find_counted_list_anchor_spans,
    _is_clean_counted_label_item,
    _is_counted_category_list_query_info,
    _is_kb_unanswerable_detail_query,
    _lexical_rescue_symbolic_list_chunk,
    _normalize_symbolic_count_letter_list_query_before_retrieval,
    _normalize_symbolic_list_surface,
    _prepare_counted_list_rescue_text,
    _route_multi_document_evidence,
    _score_symbolic_list_candidate,
    _shape_counted_list_items,
    _skip_deterministic_rag_shortcuts,
    _split_counted_inline_clause_items,
    _symbolic_list_active_allowed_sources,
    _symbolic_list_candidate_item_count,
    _symbolic_list_count_value,
    _symbolic_list_label_variants,
    _use_early_generation_shortcut,
)




def _doc_router_text(doc: Dict[str, Any]) -> str:
    return str(
        (doc or {}).get("page_content")
        or (doc or {}).get("text")
        or (doc or {}).get("content")
        or ""
    )


def _doc_router_score(doc: Dict[str, Any]) -> float:
    for key in ("score", "final_score", "similarity", "_boosted_score"):
        if key in (doc or {}):
            try:
                return float((doc or {}).get(key) or 0.0)
            except Exception:
                return 0.0
    md = dict((doc or {}).get("metadata") or {})
    try:
        return float(md.get("_score") or 0.0)
    except Exception:
        return 0.0


def _doc_router_source_key(doc: Dict[str, Any]) -> str:
    md = dict((doc or {}).get("metadata") or {})
    active_sources = _get_active_sources()
    keys = _metadata_source_keys(md)
    active_hits = sorted(keys & active_sources)
    if active_hits:
        return active_hits[0]
    for field in ("filename", "source_filename", "file", "doc_id", "source", "id"):
        raw = str(md.get(field) or "").strip()
        normalized = _normalize_source_label(raw)
        if normalized:
            return normalized
    return "unknown"


def _doc_router_display_source(doc: Dict[str, Any], source_key: str) -> str:
    md = dict((doc or {}).get("metadata") or {})
    for field in ("filename", "source_filename", "file", "doc_id", "source", "title"):
        raw = str(md.get(field) or "").strip()
        if raw and _normalize_source_label(raw) not in {"upload", "watcher"}:
            return raw
    return source_key or "unknown"


def _filter_doc_dicts_to_active_sources(doc_dicts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    active_sources = _get_active_sources()
    if not active_sources:
        # Attempt to recover active sources from the (current tenant's) collection
        # before failing closed.
        try:
            _rebuild_active_sources_from_collection(tenant_id=_resolve_active_source_tenant())
            active_sources = _get_active_sources()
        except Exception:
            pass
        if not active_sources:
            logger.warning("[DOC ROUTER] No active sources — failing closed. in_count=%s", len(doc_dicts or []))
            return []
    kept: List[Dict[str, Any]] = []
    dropped = 0
    unverifiable = 0
    for doc in doc_dicts or []:
        md = dict((doc or {}).get("metadata") or {})
        keys = _metadata_source_keys(md)
        if not keys:
            unverifiable += 1
            dropped += 1
            continue
        if keys & active_sources:
            kept.append(doc)
        else:
            dropped += 1
    if dropped:
        logger.info(
            "[DOC ROUTER] stale_source_filter active_sources=%s kept=%s dropped=%s unverifiable=%s",
            sorted(active_sources),
            len(kept),
            dropped,
            unverifiable,
        )
    _dbg7d3bbb("assistify_rag_server.py:_filter_doc_dicts_to_active_sources", "doc-dict active-source filter result",
               {"in_count": len(doc_dicts or []), "kept": len(kept), "dropped": dropped,
                "unverifiable": unverifiable, "active_sources_count": len(active_sources),
                "active_sources": sorted(active_sources)[:8]}, "H-C")
    if not kept:
        logger.warning(
            "[DOC ROUTER] active-source filter returned nothing — failing closed. active_sources=%s total=%s",
            sorted(active_sources),
            len(doc_dicts or []),
        )
    return kept


# --- Phase 8H refactor: block extracted to backend.retrieval.validation, bound to this live
# module via bind_server so extracted helpers reach shared state/engine fns.
from backend.retrieval import validation as _ext_mod_validation
_ext_mod_validation.bind_server(_sys.modules[__name__])
from backend.retrieval.validation import (
    _ANY_DEFINITION_CUE_RE,
    _DIRECT_DEFINITION_CUE_RE,
    _STRICT_LIST_LABEL_VERB_RE,
    _SYMBOLIC_LIST_CARDINALS,
    _definition_direct_pattern_match,
    _definition_quality_rejected_reason,
    _list_query_count_target,
    _log_definition_quality_rejection,
    _log_list_quality_rejection,
    _log_ocr_filter_rejection,
    _ocr_filter_rejected_reason,
    _preview_for_quality_log,
    _strict_list_label_reject_reason,
)
# --- Phase 8H refactor: block extracted to backend.retrieval.routing, bound to this live
# module via bind_server so extracted helpers reach shared state/engine fns.
from backend.retrieval import routing as _ext_mod_routing
_ext_mod_routing.bind_server(_sys.modules[__name__])
from backend.retrieval.routing import (
    _AR_DEFINITION_QUERY_RE,
    _AR_EXPLANATION_QUERY_RE,
    _AR_FINAL_POLISH_STOPWORDS,
    _BM25_DEF_CACHE,
    _CONVERSATIONAL_INTENT_REDIRECTS,
    _DEFINITION_DESCRIPTIVE_PENALTY_RE,
    _DEFINITION_QUOTED_DEF_RE,
    _DEFINITION_VERB_NEAR_RE,
    _EVIDENCE_STOPWORDS,
    _EVIDENCE_VALUE_PATTERNS,
    _EXPLANATION_CUE_RE,
    _EXPLANATION_DIRECT_CUE_RE,
    _EXPLANATION_EXAMPLE_DOMINANT_RE,
    _EXPLANATION_FEATURE_EVIDENCE_PATTERNS,
    _EXPLANATION_FEATURE_QUERY_PATTERNS,
    _EXPLANATION_HELPER_STOP,
    _EXPLANATION_INTENT_RE_AR,
    _EXPLANATION_INTENT_RE_EN,
    _EXPLANATION_LEADING_FRAGMENT_RE,
    _EXPLANATION_NOISE_RE,
    _EXPLANATION_QUERY_STOP,
    _EXPLANATION_RELATION_VERB_RE,
    _EXPLANATION_SECTION_MARKER_RE,
    _MINBAL_HEADER_TOKENS,
    _MPC15_ALIAS_ONLY_RE,
    _MPC15_BAD_ANCHOR_PREFIX_RE,
    _MPC15_BIO_REJECT_RE,
    _MPC15_DEF_CUE_RE,
    _MPC15_GENERIC_CONCEPT_SUFFIX,
    _MPC15_NEXT_HEADING_RE,
    _MPC6_CAPTION_RE,
    _MPC6_QUERY_STOP,
    _MPC6_SECTION_RE,
    _OCR_CAMELCASE_BOUNDARY_RE,
    _OCR_GLUED_FUNCTION_PREFIXES,
    _OCR_GLUED_PREFIX_RE,
    _SMALLTALK_RESPONSES,
    _STRUCTURE_QUERY_RE,
    _STRUCTURE_WORD_VARIANTS,
    _SYMBOLIC_LIST_NUMBER_WORDS,
    _SYMBOLIC_LIST_QUERY_STOPWORDS,
    _TABLE_FACT_CURRENCY_RE,
    _active_rag_search_async,
    _append_rich_definition_context,
    _append_symbolic_explanation_rescue_doc,
    _apply_concept_filter_to_docs,
    _apply_customer_support_tone,
    _apply_heading_boost_for_family,
    _apply_not_found_ux,
    _arabic_final_query_tokens,
    _assess_list_coherence,
    _assistant_meta_direct_answer,
    _best_term_explanation_from_docs,
    _bm25_tokenize_text,
    _build_compact_fact_context_docs,
    _build_controlled_explanation_answer,
    _build_controlled_explanation_answer_en,
    _build_definition_entity_rescue_queries,
    _build_fact_rescue_queries,
    _build_generation_context,
    _build_grounded_llm_answer,
    _build_indirect_definition_answer,
    _build_relation_rescue_query,
    _build_strict_fact_system_prompt,
    _build_symbolic_anchor_explanation_answer,
    _choose_top_complementary_indirect_sentences,
    _chunk_entity_dominant_topic,
    _chunk_has_entity_heading,
    _chunk_passes_concept_consistency,
    _chunk_satisfies_fact_relation_rule,
    _classify_assistant_meta_intent,
    _classify_conversational_ack_intent,
    _classify_query_family,
    _classify_query_family_v2,
    _classify_simple_recovery_query_type,
    _classify_smalltalk_intent,
    _clean_arabic_final_text,
    _clean_definition_like_sentence,
    _clean_explanation_concept_phrase,
    _clean_explanation_sentence,
    _clean_mixed_not_found_response,
    _clean_ocr_artifacts,
    _cleanup_definition_comparison_answer_text,
    _cleanup_final_answer_text,
    _collect_local_window_support,
    _collection_pipe_table_chunks,
    _compare_answer_from_docs,
    _compare_answer_from_docs_strict,
    _compare_terms_from_query,
    _compose_grounded_generation_answer,
    _concept_proximity_score,
    _concept_specific_signal_terms,
    _contains_compare_terms,
    _context_grounded_definition_override,
    _conversational_redirect,
    _count_concept_specific_signals,
    _count_list_like_items_in_docs,
    _customer_service_no_match_response,
    _debug_section_confidence,
    _dedup_docs_exact_text,
    _definition_comparison_reason,
    _definition_entity_or_reference_match,
    _definition_entity_tokens,
    _definition_explanation_fallback,
    _definition_mode_from_query,
    _definition_structural_signal_delta,
    _detect_fact_query_type,
    _direct_route_answer,
    _distance_threshold_for_query,
    _doc_explanation_focus_hits,
    _doc_has_explanation_for_entity,
    _doc_ocr_noise_score,
    _doc_query_token_signals,
    _docs_have_structure_markers,
    _effective_user_query,
    _enforce_definition_doc_contamination_guard,
    _enforce_runtime_answer_acceptance,
    _enrich_who_identity_answer,
    _ensure_bm25_definition_cache,
    _ensure_user_visible_support_answer,
    _evidence_candidate_units,
    _evidence_concept_tokens,
    _evidence_value_types_for_query,
    _expand_explanation_docs_with_local_windows,
    _expand_query,
    _explanation_content_tokens,
    _explanation_doc_metadata_text,
    _explanation_doc_text,
    _explanation_feature_hits,
    _explanation_focus_tokens,
    _explanation_fragment_marker_count,
    _explanation_group_has_hit,
    _explanation_hit_group_indices,
    _explanation_line_fingerprint,
    _explanation_lines_too_similar,
    _explanation_mode_instructions,
    _explanation_primary_appears_early,
    _explanation_primary_concept_group,
    _explanation_query_features,
    _explanation_relationship_concept_groups,
    _explanation_section_feature_hits,
    _explanation_starts_as_fragment,
    _explanation_token_match,
    _explanation_tokens_for_phrase,
    _explode_inline_ordered_enumerations,
    _extract_best_scored_concept_sentence_from_docs,
    _extract_candidate_definition_sentence_from_docs,
    _extract_confident_factual_answer,
    _extract_definition_comparison_answer,
    _extract_definition_route_answer,
    _extract_definition_sentence,
    _extract_document_headings,
    _extract_entity_from_definition_query,
    _extract_evidence_value_sentence,
    _extract_exact_count_structural_list_group,
    _extract_fact_from_context,
    _extract_fact_route_answer,
    _extract_fallback_list,
    _extract_heading_like_lines_from_chunk,
    _extract_heading_preview,
    _extract_heading_snippets_from_line,
    _extract_inline_numbered_figure_table_list,
    _extract_list_from_context,
    _extract_list_route_answer,
    _extract_metric_fact_answer,
    _extract_minbalance_from_pipe_line,
    _extract_multichunk_who_candidate,
    _extract_overview_chapter_compare_answer,
    _extract_query_concept_signature,
    _extract_relation_subject_terms,
    _extract_section_block,
    _extract_simple_definition_sentence,
    _extract_simple_list_from_docs,
    _extract_simple_overview_from_docs,
    _extract_strict_clean_label_candidates,
    _extract_strict_same_line_person_identity_from_retrieved_docs,
    _extract_structure_aware_definition,
    _extract_structure_concept_cluster_from_docs,
    _extract_structured_list_from_context,
    _extract_table_fact_answer,
    _extract_topic_pure_overview_from_docs,
    _filter_docs_for_explanation,
    _finalize_user_visible_answer,
    _force_clean_definition_sentence,
    _format_table_fact_answer,
    _format_translated_explanation_lines,
    _has_english_keyword_overlap,
    _has_exact_who_person_evidence,
    _has_likely_person_name_for_fact_relation,
    _has_meaningful_context,
    _has_paragraph_prose_shape,
    _has_required_concept_specific_signal,
    _has_strong_local_window_support,
    _has_sufficient_context,
    _has_symbolic_count_letter_support,
    _heading_candidates_from_doc,
    _indirect_evidence_pool_is_weak,
    _infer_fact_context_mode_from_docs,
    _is_answer_grounded_in_docs,
    _is_assistant_behavior_complaint_query,
    _is_assistant_capability_or_meta_query,
    _is_attribution_or_citation_heading_text,
    _is_bad_output_text,
    _is_biography_sentence,
    _is_classification_only_chunk,
    _is_compare_query,
    _is_controlled_definition_entity_query,
    _is_conversational_ack_query,
    _is_current_world_or_personal_query,
    _is_definition_boilerplate_sentence,
    _is_definition_comparison_query,
    _is_definition_sentence,
    _is_definition_style_query,
    _is_document_summary_query,
    _is_document_title_heading_text,
    _is_explanation_intent_query,
    _is_explanation_sentence_for_entity,
    _is_explicit_oos_query,
    _is_feature_only_definition_sentence,
    _is_force_overview_paragraph_query,
    _is_generic_grounding_sentence,
    _is_goal_objective_list_query,
    _is_heading_candidate_line,
    _is_incomplete_fragment_sentence,
    _is_list_or_process_query,
    _is_list_query,
    _is_low_confidence_grounding,
    _is_low_quality_doc,
    _is_metric_fact_query,
    _is_numeric_fact_lookup_query,
    _is_over_generic_definition_template,
    _is_overview_query,
    _is_placeholder_heading_text,
    _is_pure_smalltalk_query,
    _is_rag_no_match_sentinel,
    _is_relationship_or_explanation_query,
    _is_safe_definition_fast_path_query,
    _is_simple_fact_definition_or_list_query,
    _is_simple_factual_text_query,
    _is_smalltalk,
    _is_strict_overview_query,
    _is_structure_query,
    _is_structured_bullet_answer,
    _is_support_procedural_query,
    _is_symbolic_explanation_line,
    _is_symbolic_support_line,
    _is_table_or_classification_sentence,
    _is_targeted_list_question,
    _is_unsupported_unclear_query,
    _is_usable_explanation_sentence,
    _is_valid_definition_sentence,
    _is_valid_overview_answer,
    _is_weak_retrieval_evidence,
    _is_wrong_concept_definition_chunk,
    _is_ws_definition_query_mode,
    _is_ws_explain_query_mode,
    _light_normalize_query_token,
    _lightweight_spelling_correction,
    _list_marker_score,
    _list_query_alignment_metrics,
    _log_answer_mode_markers,
    _log_direct_route_handled,
    _log_query_family_fix,
    _log_selected_doc_markers,
    _looks_like_document_question,
    _looks_like_rag_no_match_stream,
    _match_query_to_headings,
    _max_doc_similarity,
    _mentions_other_approach,
    _merge_rescue_docs_and_rerank,
    _mpc15_corpus_filter_by_entity,
    _mpc15_load_full_corpus_chunks,
    _mpc6_anchor_score_for_text,
    _mpc6_query_focus_tokens,
    _normalize_arabic_readability_terms,
    _normalize_compare_entity_term,
    _normalize_context_entities,
    _normalize_definition_entity,
    _normalize_definition_query_before_retrieval,
    _normalize_final_bullet_format,
    _normalize_phrase_text,
    _normalize_query_for_router,
    _normalize_rescue_doc_dict,
    _normalize_support_query_surface,
    _normalize_validated_fact_answer,
    _not_found_response,
    _ocr_repair_glued_tokens,
    _overview_seed_query,
    _passes_fast_path_definition_validation,
    _passes_hybrid_relevance_gate,
    _passes_strict_definition_relevance_guard,
    _polish_final_response_text,
    _preclean_list_answer_for_assessment,
    _prefilter_fact_docs_by_relation,
    _prepare_rag_doc_dicts_shared,
    _promote_entity_definition_top_doc,
    _prune_overlong_counted_list_items,
    _query_main_entity_tokens,
    _query_requires_structure,
    _query_section_phrases,
    _query_section_tokens,
    _query_tokens_for_evidence,
    _rank_explanation_docs_for_query,
    _refine_concept_definition_answer,
    _rerank_docs_for_query_intent,
    _rescue_support_procedural_from_docs,
    _resolve_doc_heading_source,
    _retrieval_context_is_reliable,
    _retrieval_evidence_metrics,
    _retrieve_with_section_bias,
    _rewrite_query_for_retrieval,
    _route_lang_for_user_visible,
    _route_response_language,
    _s_definition_sentence,
    _safe_grounded_concise_explanation_extraction,
    _safe_int,
    _sanitize_list_answer_text,
    _score_explanation_sentence,
    _search_bm25_definition_fallback,
    _search_fast_definition_minimal,
    _search_fast_definition_minimal_async,
    _search_fast_minimal,
    _search_fast_minimal_async,
    _search_with_query_expansion,
    _select_explanation_topic_group,
    _select_fact_anchor_docs,
    _select_multichunk_fact_fallback_docs,
    _select_safe_indirect_from_pool,
    _sentence_is_generic_weak,
    _sentence_passes_same_concept_filter,
    _sentence_subject_is_target_entity,
    _shared_rag_final_answer_decision,
    _shorten_arabic_spoken_answer,
    _should_allow_generic_answer,
    _slice_chunk_to_query_subsection,
    _smalltalk_response,
    _spelling_correction_preserving_exact_terms,
    _split_arabic_answer_units,
    _split_explanation_candidates,
    _split_explanation_leading_label,
    _split_query_context_focus_tokens,
    _split_text_into_sentences,
    _strip_attribution_prefix_for_definition,
    _strip_doc_structure_artifacts,
    _strip_doc_structure_separators,
    _strip_query_instruction_modifiers,
    _strip_repeated_kb_headings,
    _structure_words_in_text,
    _symbolic_anchor_phrase_hit,
    _table_fact_focus_tokens,
    _table_fact_product_phrases,
    _token_match_light,
    _top_chunk_has_exact_entity_phrase,
    _translate_controlled_explanation_answer_ar,
    _validate_concept_match,
    _validate_query_ui_equivalent,
    _validate_structured_list_items,
    _with_fact_context_mode,
    _ws_fix_explanation_answer,
    call_llm_with_context,
    classify_query_route,
    clean_ocr_noise,
    collect_indirect_entity_evidence,
    count_token_matches,
    defines_other_concept,
    detect_query_intent,
    extract_keywords,
    extract_list_items,
    is_entity_definition_like,
    is_indirect_entity_explanation,
    pick_best_safe_prose_fallback,
)







































































# ========== ANALYTICS DB ==========
ANALYTICS_DB = str(ANALYTICS_DB)

# ========== FASTAPI APP INSTANCE (must come before decorators) ==========
# --- Phase 8L refactor: the FastAPI instance, middleware stack, and /assets
# mount are built by backend.app_factory.create_app(). Construction is identical
# to the previous inline setup; only its location moved. Routes, event handlers,
# and routers below are still registered against this live `app`.
from backend.app_factory import create_app
app = create_app()

# Global aiohttp session for LLM requests (reuse connections)
llm_session: Optional[aiohttp.ClientSession] = None

# Global aiohttp session for TTS requests (reuse connections, avoids TCP
# handshake overhead on every query)
tts_session: Optional[aiohttp.ClientSession] = None

# Global faster-whisper model (typing-safe forward reference)
whisper_model: Optional['WhisperModel'] = None
# Multilingual faster-whisper model — loaded at startup when present, used for Arabic STT
whisper_model_multilingual: Optional['WhisperModel'] = None


# XTTS v2 is now a separate microservice — no local model held in this process
xtts_model = None  # kept for status endpoint backward compat

# Aliased to voice_audio.state (lifecycle updates these)
def _sync_voice_models_from_state():
    global whisper_model, whisper_model_multilingual, tts_session, xtts_model, llm_session
    from backend.voice_audio import config as voice_config
    whisper_model = voice_state.whisper_model
    whisper_model_multilingual = voice_state.whisper_model_multilingual
    tts_session = voice_state.tts_session
    xtts_model = voice_state.xtts_model
    llm_session = voice_state.llm_session or llm_session
    voice_config.EFFECTIVE_DISABLE_TTS = EFFECTIVE_DISABLE_TTS
    voice_config.EFFECTIVE_DISABLE_WHISPER = EFFECTIVE_DISABLE_WHISPER
    voice_config.EFFECTIVE_DISABLE_WARMUP = EFFECTIVE_DISABLE_WARMUP


# Pre-rendered Arabic acknowledgment PCM audio (populated at startup via XTTS).
# Streamed immediately when an Arabic query arrives so the user hears audio
# within ~1 second while the actual answer is still being generated.
_arabic_ack_pcm: bytes = b""
_arabic_offtopic_pcm: bytes = b""

# 10 varied Arabic opener phrases — the assistant rotates through them so
# responses don't sound robotic.  All are pre-rendered as PCM at startup;
# each query picks one round-robin.  The chosen phrase is used both as the
# LLM assistant-prefill and as the immediately-played pre-cached audio.
_arabic_opener_pcm: bytes = b""           # default PCM (first phrase)
_arabic_opener_pool: dict[str, bytes] = {}  # phrase text → raw PCM bytes
_arabic_opener_counter: int = 0            # round-robin index across queries

import chromadb
from sentence_transformers import SentenceTransformer
from backend.pdf_ingestion_rag import VectorStore, _repair_split_words
from backend.knowledge_base import (
    get_or_create_collection,
    build_canonical_source_metadata,
    canonical_source_doc_id,
    delete_documents_by_source_identity,
    normalize_uploaded_filename,
    original_filename_from_stored,
)

class LiveRAGManager:
    def __init__(self, tenant_id=None):
        # Lazy initialization: defer heavy VectorStore / embedding model loading
        # until the first search call. This keeps module import fast and
        # avoids pulling large models into memory when not needed (e.g., tests).
        self._init_args = {}
        db_path = str(CHROMA_DB_PATH)
        self._init_args["persist_directory"] = db_path
        self.vs: Optional[VectorStore] = None
        # Resolve the tenant this manager serves. The default tenant keeps the
        # historical auto-resolution behavior (no explicit collection name) so
        # existing single-tenant data continues to work unchanged. Other tenants
        # bind to their own namespaced collection, which VectorStore enforces in
        # its per-tenant "explicit" resolution branch — guaranteeing a query for
        # one business can never read another business's vectors.
        try:
            self.tenant_id = DEFAULT_TENANT_ID if tenant_id is None else int(tenant_id)
        except (TypeError, ValueError):
            self.tenant_id = DEFAULT_TENANT_ID
        if self.tenant_id == DEFAULT_TENANT_ID:
            self.collection_name = "support_docs_v3_latest"
            # None => preserve legacy auto-resolution inside VectorStore.
            self._vs_collection_name = None
        else:
            try:
                self.collection_name = tenant_collection_name(self.tenant_id)
            except Exception:
                self.collection_name = f"t{self.tenant_id}_support_docs_v3_latest"
            self._vs_collection_name = self.collection_name
        # The ASSISTIFY_COLLECTION_NAME override only applies to the default
        # tenant; honoring it for every tenant would break isolation.
        if self.tenant_id == DEFAULT_TENANT_ID:
            self._preferred_collection = os.environ.get("ASSISTIFY_COLLECTION_NAME", "").strip() or self.collection_name
        else:
            self._preferred_collection = self.collection_name
        
    def search(self, query: str, top_k: int = 5, distance_threshold: float = 1.0, return_dicts: bool = False, enable_rerank: bool = True):
        """High-level search orchestration."""
        logger.debug("[LiveRAGManager] tenant=%s Query: %r", self.tenant_id, query)

        # Lazy-create VectorStore on first use (safe, idempotent)
        if self.vs is None:
            try:
                self.vs = VectorStore(
                    persist_directory=str(self._init_args.get("persist_directory") or ""),
                    collection_name=self._vs_collection_name,
                )
                # If a preferred collection is set but empty, VectorStore logic will
                # handle fallback; keep behavior consistent with previous design.
            except Exception as e:
                logger.warning(f"LiveRAGManager lazy init of VectorStore failed: {e}")

        # Basic intent detection for logging
        q_lower = (query or "").lower()
        if "unit" in q_lower or "chapter" in q_lower:
            intent = "structural"
        elif any(k in q_lower for k in ["list", "section", "table of contents"]):
            intent = "structure"
        else:
            intent = "general"

        logger.info(f"[LiveRAGManager] Detected intent: {intent}")

        # Delegate to VectorStore for optimized retrieval and reranking
        results = None
        if self.vs is None:
            logger.warning("LiveRAGManager.vs is not available; returning empty results")
            results = []
        else:
            results = self.vs.search(
                query=query,
                top_k=top_k,
                distance_threshold=distance_threshold,
                return_dicts=return_dicts,
                enable_rerank=enable_rerank,
            )

        return results

    # --- DEPRECATED OLD SEARCH HELPERS REMOVED ---

# Inject the new pipeline wrapper. `live_rag` serves the default tenant and
# preserves the historical single-tenant retrieval behavior exactly.
live_rag = LiveRAGManager()

# Per-tenant retrieval managers. Each non-default tenant gets its own
# LiveRAGManager (and therefore its own ChromaDB collection + cached VectorStore),
# so retrieval is physically isolated per business.
_tenant_rag_managers: dict = {}
_tenant_rag_lock = RLock()


def get_tenant_rag(tenant_id=None) -> "LiveRAGManager":
    """Return the retrieval manager bound to a tenant's knowledge base.

    The default tenant reuses the legacy `live_rag` singleton; every other
    tenant gets a lazily-created, cached manager pinned to its own collection.
    """
    try:
        tid = int(tenant_id) if tenant_id is not None else DEFAULT_TENANT_ID
    except (TypeError, ValueError):
        tid = DEFAULT_TENANT_ID
    if tid <= 0:
        tid = DEFAULT_TENANT_ID
    if tid == DEFAULT_TENANT_ID:
        return live_rag
    with _tenant_rag_lock:
        mgr = _tenant_rag_managers.get(tid)
        if mgr is None:
            mgr = LiveRAGManager(tenant_id=tid)
            _tenant_rag_managers[tid] = mgr
        return mgr


def _active_rag() -> "LiveRAGManager":
    """Retrieval manager for the tenant bound to the current request context."""
    try:
        return get_tenant_rag(current_tenant_id())
    except Exception:
        return live_rag


def _sync_live_retrieval_collection(target_collection_name: str | None = None, tenant_id: int | None = None) -> str:
    """Ensure live retrieval is pointed at the same collection used by indexing.

    This is the CRITICAL handoff point between upload/indexing and live queries.
    After every upload, this function MUST be called to guarantee that live_rag
    is querying the same collection that just received the new chunks.

    Fixes the 'Not found in the document' bug that occurred when:
    - The indexing collection and retrieval collection fell out of sync
    - ChromaDB returned a stale collection object after deletions
    """
    from backend.knowledge_base import _collection_owned_by_tenant, get_or_create_collection

    tid = int(tenant_id if tenant_id is not None else current_tenant_id())
    scope_tid = None if int(tid) == int(DEFAULT_TENANT_ID) else int(tid)
    kb_collection = get_or_create_collection(allow_empty=True, tenant_id=scope_tid)
    if not kb_collection:
        raise RuntimeError("No KB collection available for live retrieval sync")

    desired = str(target_collection_name or getattr(kb_collection, "name", "") or "").strip()
    if not desired:
        raise RuntimeError("Resolved KB collection has no valid name")

    # Always get a FRESH collection reference from ChromaDB — never reuse
    # cached references which may be stale after delete_all + re-index.
    client = getattr(getattr(live_rag, "vs", None), "client", None)
    if client is None:
        from backend.knowledge_base import client as kb_client
        client = kb_client

    try:
        fresh_collection = client.get_collection(name=desired)
        fresh_count = fresh_collection.count()
    except Exception as e:
        logger.error("Failed to get fresh collection '%s': %s", desired, e)
        raise RuntimeError(f"Collection '{desired}' not found: {e}")

    # If the target collection is empty, scan only collections owned by this tenant.
    if fresh_count == 0:
        logger.warning(
            "Target collection '%s' is empty after sync attempt — scanning tenant-owned alternatives",
            desired,
        )
        try:
            all_collections = client.list_collections()
            collection_names: list[str] = []
            for c in all_collections or []:
                if isinstance(c, str):
                    collection_names.append(c)
                else:
                    name = getattr(c, "name", None)
                    if name:
                        collection_names.append(str(name))
            for c_name in sorted(collection_names, reverse=True):
                if not _collection_owned_by_tenant(c_name, tid):
                    continue
                try:
                    candidate = client.get_collection(name=c_name)
                    if candidate.count() > 0:
                        fresh_collection = candidate
                        fresh_count = candidate.count()
                        desired = c_name
                        logger.info("Fallback: using non-empty collection '%s' (count=%s)", desired, fresh_count)
                        break
                except Exception:
                    continue
        except Exception as scan_err:
            logger.warning("Collection scan failed: %s", scan_err)

    _vs_collection_ref = getattr(getattr(live_rag, "vs", None), "collection", None)
    old_name = str(_vs_collection_ref.name) if _vs_collection_ref is not None else "<none>"
    _live_vs = live_rag.vs
    if _live_vs is not None:
        _live_vs.collection = fresh_collection
    # Invalidate rerank cache when the active collection changes — entries
    # are keyed by collection name + query + candidate-ids, so stale entries
    # would never match anyway, but clearing keeps memory bounded after
    # uploads/deletes/hot-swaps. Safe no-op if helper is unavailable.
    if old_name != desired:
        try:
            from backend.pdf_ingestion_rag import _rerank_cache_clear as _rc_clear
            _rc_clear(reason=f"collection_swap {old_name}->{desired}")
        except Exception as _rc_err:
            logger.warning("[RERANK CACHE] clear-on-swap failed: %s", _rc_err)
    logger.info(
        "Live retrieval collection synced | previous=%s current=%s count=%s",
        old_name, desired, fresh_count,
    )
    return desired

@app.on_event("startup")
async def startup_event():
    global llm_session, tts_session, whisper_model, whisper_model_multilingual, xtts_model, WHISPER_DEVICE, WHISPER_COMPUTE_TYPE, EFFECTIVE_DISABLE_TTS

    assert_production_config()
    init_database()
    init_analytics_db()
    _chat_store.init_chat_store_schema()
    try:
        migrated = _chat_store.migrate_from_json(CONVERSATIONS_FILE)
        if migrated:
            logger.info("[CHAT] auto-migrated %s conversations from JSON", migrated)
    except Exception as exc:
        logger.warning("[CHAT] JSON migration skipped: %s", exc)
    logger.warning(
        "[INGEST OWNER] RAG server is the single ingestion/delete owner; "
        "admin/login servers must proxy upload, update, and delete requests only."
    )
    
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

    # ================== NEW PIPELINE STARTUP LOGS ==================
    logger.info("\n========== RAG PIPELINE DIAGNOSTICS ==========")
    # Ensure live_rag.vs is available at startup (lazy-init may leave it None)
    try:
        if getattr(live_rag, 'vs', None) is None:
            db_path = str(CHROMA_DB_PATH)
            try:
                live_rag.vs = VectorStore(persist_directory=db_path)
                logger.info("LiveRAGManager.vs lazily initialized at startup")
            except Exception as e:
                logger.warning(f"LiveRAGManager.vs lazy init failed: {e}")
        if getattr(live_rag, 'vs', None) is not None:
            logger.info(f"Active Retrieval Class/Module: {live_rag.vs.__class__.__module__}.{live_rag.vs.__class__.__name__}")
            db_path = str(CHROMA_DB_PATH)
            logger.info(f"Active ChromaDB Path: {db_path}")
            try:
                _startup_vs = live_rag.vs
                if _startup_vs is not None and getattr(_startup_vs, 'collection', None):
                    logger.info(f"Active Collection Name: {_startup_vs.collection.name}")
                    total_chunks = _startup_vs.collection.count()
                    logger.info(f"Number of chunks loaded: {total_chunks}")
            except Exception:
                logger.warning("Could not introspect live_rag.vs.collection at startup")
    except Exception as e:
        logger.warning(f"RAG pipeline diagnostics skipped due to init error: {e}")
        try:
            # Generic, collection-agnostic startup retrieval probes.
            test_queries = [
                "What is this document about?",
                "List 3 key ideas from this document",
                "Explain an important concept mentioned in this document",
                "What topics are covered in this document?",
                "What does this document say about quantum computing?",
            ]

            logger.info("\n--- STARTUP DEBUG: generic retrieval probes ---")
            for q in test_queries:
                logger.info(f"Probe query: {q}")
                try:
                    _probe_vs = live_rag.vs
                    if _probe_vs is None:
                        logger.info("  Probe skipped: live_rag.vs is not initialized.")
                        continue
                    probe_results = _probe_vs.search(query=q, top_k=5, distance_threshold=-2.0)
                    if not probe_results:
                        logger.info("  No results returned for this query.")
                        continue
                    for i, r in enumerate(probe_results, start=1):
                        # Safely handle result dict keys (similarity/score/metadata/text)
                        sim = None
                        if isinstance(r, dict):
                            sim = r.get('similarity') if 'similarity' in r else r.get('score')
                            meta = r.get('metadata', {})
                            text = r.get('text', '')
                        else:
                            meta = {}
                            text = str(r)
                        try:
                            sim_str = f"{float(sim):.4f}" if sim is not None else "N/A"
                        except Exception:
                            sim_str = str(sim)
                        logger.info(f"  Result #{i} | Sim: {sim_str} | Meta: {meta}")
                        logger.info(f"  Preview: {text[:150].replace(chr(10), ' ')}")
                except Exception as probe_err:
                    logger.warning(f"  Probe failed for query '{q}': {probe_err}")
            logger.info("=================================================\n")
        except Exception as startup_probe_err:
            logger.warning(f"Startup retrieval probes skipped due to collection issue: {startup_probe_err}")
        logger.info("=================================================\n")
    # ===============================================================

    logger.info("✓ Persistent LLM session created with connection pooling")
    logger.info("✓ Persistent TTS session created")
    logger.info("[OLLAMA CONFIG] host_raw=%s", OLLAMA_HOST)
    logger.info("[OLLAMA CONFIG] port_raw=%s", OLLAMA_PORT)
    logger.info("[OLLAMA CONFIG] chat_url=%s", _build_ollama_url('/api/chat'))
    logger.info("[OLLAMA CONFIG] generate_url=%s", _build_ollama_url('/api/generate'))
    logger.info(
        "[FEATURE FLAGS] safe_mode=%s reranker=%s tts=%s whisper=%s warmup=%s",
        ASSISTIFY_SAFE_MODE,
        ("disabled" if EFFECTIVE_DISABLE_RERANKER else "enabled"),
        ("disabled" if EFFECTIVE_DISABLE_TTS else "enabled"),
        ("disabled" if EFFECTIVE_DISABLE_WHISPER else "enabled"),
        ("disabled" if EFFECTIVE_DISABLE_WARMUP else "enabled"),
    )
    logger.info(
        "[FEATURE FLAGS RAW] ASSISTIFY_SAFE_MODE=%s EFFECTIVE_DISABLE_RERANKER=%s EFFECTIVE_DISABLE_TTS=%s EFFECTIVE_DISABLE_WHISPER=%s EFFECTIVE_DISABLE_WARMUP=%s",
        ASSISTIFY_SAFE_MODE,
        EFFECTIVE_DISABLE_RERANKER,
        EFFECTIVE_DISABLE_TTS,
        EFFECTIVE_DISABLE_WHISPER,
        EFFECTIVE_DISABLE_WARMUP,
    )
    await _check_ollama_connectivity()

    try:
        indexed_files = [f.get("filename") for f in list_uploaded_files() if f.get("filename")]
        if indexed_files and not _get_active_sources():
            if _active_doc_registry.get("mode", RAG_DOC_MODE) == "single":
                _set_active_sources([indexed_files[-1]], mode="single")
            else:
                _rebuild_active_sources_from_collection()
        elif not _get_active_sources():
            _rebuild_active_sources_from_collection()
    except Exception as registry_err:
        logger.warning(f"Active source registry bootstrap failed: {registry_err}")

    # Print the RAG collection being used at startup for quick diagnostics
    try:
        from backend.knowledge_base import get_or_create_collection as _goc
        _kb_col = _goc(allow_empty=False)
        if _kb_col is not None:
            _name = getattr(_kb_col, 'name', None) or '<unknown>'
            logger.info("[RAG INIT] Using collection: %s", _name)
            logger.info("[RAG INIT] Count: %s", _kb_col.count())
    except Exception:
        pass

    # SAFE MODE logic: skip heavy initialization
    if ASSISTIFY_SAFE_MODE:
        logger.warning("ASSISTIFY_SAFE_MODE IS ENABLED. Skipping Whisper, XTTS checks, and TTS precaching.")
        return

    # Voice STT/TTS init (Phase 1: voice_audio package)
    await init_voice_audio(
        app,
        safe_mode=ASSISTIFY_SAFE_MODE,
        disable_warmup=EFFECTIVE_DISABLE_WARMUP,
    )
    _sync_voice_models_from_state()
    logger.info("✓ Voice audio subsystem initialized")

    if not EFFECTIVE_DISABLE_WARMUP:
        asyncio.create_task(_warmup_llm())

    # Assets watcher: prefer watchdog (OS events) for instant reindexing,
    # fallback to the polling watcher if watchdog isn't installed.
    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler

        # Capture the running event loop NOW (in the async context) so the
        # watchdog callbacks — which run in a separate OS thread — can safely
        # schedule coroutines without calling get_event_loop() from a thread
        # (which raises RuntimeError in Python 3.10+ when no loop is set for
        # that thread).
        _main_loop = asyncio.get_running_loop()

        class _AssetsHandler(FileSystemEventHandler):
            def on_created(self, event):
                if event.is_directory:
                    return
                try:
                    fname = Path(str(event.src_path)).name
                    _main_loop.call_soon_threadsafe(
                                lambda f=fname: _queue_assets_reindex(f)
                    )
                except Exception:
                    logger.exception("Assets handler on_created error")

            def on_modified(self, event):
                if event.is_directory:
                    return
                try:
                    fname = Path(str(event.src_path)).name
                    _main_loop.call_soon_threadsafe(
                        lambda f=fname: _queue_assets_reindex(f)
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

    # If Chroma is empty but files exist in assets (e.g., after dependency/env
    # issues during earlier uploads), bootstrap indexing on startup.
    asyncio.create_task(_bootstrap_assets_index_if_needed())

async def _warmup_llm():
    """
    Background task: preload the Ollama model into VRAM on startup.

    Uses the official Ollama preload method: POST /api/generate with no
    prompt and keep_alive: -1.  This loads the model weights into GPU
    memory and tells Ollama to NEVER evict them, so every user query
    gets a fast first token instead of waiting 8+ seconds for a cold load.
    """
    await asyncio.sleep(3)          # let server finish binding first
    preload_url = _build_ollama_url("/api/generate")
    logger.info(f"[Warmup] Preloading {OLLAMA_MODEL} into VRAM (keep_alive=-1)...")
    payload = {
        "model": OLLAMA_MODEL,
        "keep_alive": -1,   # never evict from VRAM
        # No 'prompt' key — this is the official Ollama preload pattern.
        # Ollama loads the model and returns immediately without generating tokens.
        # IMPORTANT: num_ctx must match chat requests exactly, otherwise Ollama
        # reloads the model on every chat call (causing 8-second cold-start delays).
        "options": {
            "num_ctx": 3072,
            "num_gpu": 99,
        },
    }
    try:
        logger.info("[OLLAMA CALL] endpoint=%s model=%s query_type=warmup", preload_url, OLLAMA_MODEL)
        async with aiohttp.ClientSession() as session:
            async with session.post(
                preload_url,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=120),
            ) as resp:
                logger.info("[OLLAMA CALL RESULT] status=%s endpoint=%s", resp.status, preload_url)
                if resp.status == 200:
                    logger.info(f"[Warmup] ✓ {OLLAMA_MODEL} loaded into VRAM | keep_alive=forever")
                else:
                    text = await resp.text()
                    logger.warning(f"[Warmup] Ollama preload returned {resp.status}: {text[:120]}")
    except Exception as e:
        logger.warning(f"[Warmup] LLM preload failed (Ollama may not be running yet): {e}")


async def _warmup_xtts():
    """Background task: warm up the XTTS model.

    By default ONLY a short English warmup runs; Arabic ack/off-topic and
    the 10-phrase opener batch are gated behind env flags because they were
    blocking real user TTS for >60s at startup. To re-enable them set:

        ASSISTIFY_ENABLE_ENGLISH_TTS_WARMUP=1
        ASSISTIFY_ENABLE_ARABIC_TTS_WARMUP=1
        ASSISTIFY_ENABLE_TTS_OPENER_WARMUP=1
    """
    global _arabic_ack_pcm, _arabic_offtopic_pcm, _arabic_opener_pcm, _arabic_opener_pool

    en_enabled = ASSISTIFY_ENABLE_ENGLISH_TTS_WARMUP
    ar_enabled = ASSISTIFY_ENABLE_ARABIC_TTS_WARMUP
    op_enabled = ASSISTIFY_ENABLE_TTS_OPENER_WARMUP

    logger.info(f"[TTS WARMUP] english={'enabled' if en_enabled else 'disabled'}")
    logger.info(f"[TTS WARMUP] arabic={'enabled' if ar_enabled else 'disabled'}")
    logger.info(f"[TTS WARMUP] openers={'enabled' if op_enabled else 'disabled'}")

    if not (en_enabled or ar_enabled or op_enabled):
        logger.info("[TTS WARMUP] all_tts_warmups_disabled")
        logger.info("[TTS WARMUP] complete time=0ms (all warmups disabled)")
        return

    _t_overall = time.perf_counter()
    await asyncio.sleep(10)  # let the Piper service finish initializing
    logger.info(f"[TTS ENGINE] piper")
    logger.info(f"[PIPER] warmup_starting url={XTTS_SERVICE_URL}")

    # Hold the global synth semaphore while warmups run so a real user /tts
    # request that arrives during warmup waits cleanly behind it instead of
    # competing with XTTS for GPU.
    try:
        async with _XTTS_SYNTH_SEM:
            try:
                async with aiohttp.ClientSession() as session:
                    if en_enabled:
                        # ---- Single minimal English warmup ----
                        # Short realistic sentence in the same speaker/lang the
                        # user response uses, so the first real synth is hot.
                        _EN_WARMUP_TEXT = (
                            "This is a short warmup sentence used to prepare the speech "
                            "model for real responses, so the first answer can start quickly."
                        )
                        try:
                            _t0 = time.perf_counter()
                            async with session.post(
                                f"{XTTS_SERVICE_URL}/synthesize",
                                json={"text": _EN_WARMUP_TEXT, "speaker": XTTS_SPEAKER, "language": XTTS_LANGUAGE},
                                timeout=aiohttp.ClientTimeout(total=120),
                            ) as _en_resp:
                                if _en_resp.status == 200:
                                    await _en_resp.read()
                                    logger.info(
                                        f"[TTS WARMUP] english_done time={int((time.perf_counter() - _t0) * 1000)}ms "
                                        f"speaker={XTTS_SPEAKER} lang={XTTS_LANGUAGE}"
                                    )
                                else:
                                    _t = await _en_resp.text()
                                    logger.warning(
                                        f"[TTS WARMUP] english_failed status={_en_resp.status} body={_t[:120]}"
                                    )
                        except Exception as _e_en:
                            logger.warning(f"[TTS WARMUP] english_error: {_e_en}")

                    if ar_enabled:
                        # ---- Arabic ack + off-topic refusal pre-render ----
                        _ACK_PHRASE = "تفضل"
                        try:
                            async with session.post(
                                f"{XTTS_SERVICE_URL}/synthesize",
                                json={"text": _ACK_PHRASE, "speaker": XTTS_SPEAKER, "language": "ar"},
                                timeout=aiohttp.ClientTimeout(total=60),
                            ) as _ack_resp:
                                if _ack_resp.status == 200:
                                    _wav = await _ack_resp.read()
                                    _arabic_ack_pcm = _wav[44:] if len(_wav) > 44 else _wav
                                    logger.info(f"[TTS WARMUP] arabic_ack_cached bytes={len(_arabic_ack_pcm)}")
                                else:
                                    logger.warning(
                                        f"[TTS WARMUP] arabic_ack_failed status={_ack_resp.status}"
                                    )
                        except Exception as _e_ack:
                            logger.warning(f"[TTS WARMUP] arabic_ack_error: {_e_ack}")

                        try:
                            async with session.post(
                                f"{XTTS_SERVICE_URL}/synthesize",
                                json={"text": ARABIC_OFF_TOPIC_RESPONSE, "speaker": XTTS_SPEAKER, "language": "ar"},
                                timeout=aiohttp.ClientTimeout(total=60),
                            ) as _off_resp:
                                if _off_resp.status == 200:
                                    _wav = await _off_resp.read()
                                    _arabic_offtopic_pcm = _wav[44:] if len(_wav) > 44 else _wav
                                    logger.info(
                                        f"[TTS WARMUP] arabic_offtopic_cached bytes={len(_arabic_offtopic_pcm)}"
                                    )
                                else:
                                    logger.warning(
                                        f"[TTS WARMUP] arabic_offtopic_failed status={_off_resp.status}"
                                    )
                        except Exception as _e_off:
                            logger.warning(f"[TTS WARMUP] arabic_offtopic_error: {_e_off}")

                    if op_enabled:
                        # ---- Batch opener pre-render (10 phrases in parallel) ----
                        async def _render_opener_phrase(_sess, phrase: str) -> tuple:
                            try:
                                async with _sess.post(
                                    f"{XTTS_SERVICE_URL}/synthesize",
                                    json={"text": phrase, "speaker": XTTS_SPEAKER, "language": "ar"},
                                    timeout=aiohttp.ClientTimeout(total=60),
                                ) as _r:
                                    if _r.status == 200:
                                        _wav = await _r.read()
                                        _pcm = _wav[44:] if len(_wav) > 44 else _wav
                                        logger.info(
                                            f"[TTS WARMUP] opener_cached phrase=\"{phrase[:25]}\" bytes={len(_pcm)}"
                                        )
                                        return phrase, _pcm
                                    else:
                                        logger.warning(
                                            f"[TTS WARMUP] opener_failed phrase=\"{phrase[:25]}\" status={_r.status}"
                                        )
                            except Exception as _e_op:
                                logger.warning(
                                    f"[TTS WARMUP] opener_error phrase=\"{phrase[:25]}\": {_e_op}"
                                )
                            return phrase, b""

                        _opener_results = await asyncio.gather(
                            *[_render_opener_phrase(session, p) for p in _ARABIC_OPENER_PHRASES]
                        )
                        for _ph, _pcm in _opener_results:
                            if _pcm:
                                _arabic_opener_pool[_ph] = _pcm
                        if _ARABIC_OPENER_PHRASES[0] in _arabic_opener_pool:
                            _arabic_opener_pcm = _arabic_opener_pool[_ARABIC_OPENER_PHRASES[0]]
            except Exception as e:
                # Outer catch: do NOT let warmup spawn hidden background work
                # on partial failure. Just log and exit cleanly.
                logger.warning(f"[TTS WARMUP] aborted_on_error: {e}")
    finally:
        logger.info(f"[TTS WARMUP] complete time={int((time.perf_counter() - _t_overall) * 1000)}ms")


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

# ---------------------------------------------------------------------------
# Assets watcher helpers (debounce + skip + per-file lock)
# ---------------------------------------------------------------------------

_assets_reindex_tasks: dict[str, asyncio.Task] = {}
_assets_recently_indexed_until: dict[str, float] = {}
_assets_upload_owned_until: dict[str, float] = {}

# --- Phase 8G refactor: the collection mutation lock primitives moved to
# backend.repositories.chroma_repository. The _collection_mutation async
# context manager below still lives here because it drives the KB pipeline
# watchdog, but it acquires the single lock owned by the repository.
from backend.repositories.chroma_repository import (
    _collection_mutation_lock_holder,
    _get_collection_mutation_lock,
    _reset_collection_mutation_lock,
)

# Tombstones for files explicitly deleted via /rag/delete. The watcher and
# the startup bootstrap MUST consult this set before re-indexing, otherwise
# a file that was just deleted can be silently resurrected (the verified
# "delete is not atomic" bug). Stored as filename -> expiry timestamp so
# old entries are reaped automatically.
_recently_deleted_filenames: dict[str, float] = {}






































# The assets watcher will be started on application startup. We prefer
# using an OS-level watcher (watchdog) when available for instant events;
# otherwise the polling watcher `_assets_watcher` will be used as a fallback.

# --- Phase 8L refactor: middleware stack and /assets mount now live in
# backend.app_factory.create_app() (applied above when `app` was built).

pwd_context = CryptContext(
    schemes=["bcrypt_sha256", "pbkdf2_sha256"],
    default="bcrypt_sha256",
    deprecated=["pbkdf2_sha256"],
    bcrypt_sha256__rounds=12,
)

# ========== AUTH DECORATOR ================
def require_login(role=None):
    def wrapper(request: Request):
        token = request.cookies.get(SESSION_COOKIE)
        if not token:
            raise HTTPException(status_code=401, detail="Authentication required.")
        user, err = load_and_validate_session_token(serializer, token)
        if user is None:
            raise HTTPException(status_code=401, detail=err or "Invalid session.")
        if role and user.get("role") != role:
            raise HTTPException(status_code=403, detail="Forbidden.")
        return user
    return wrapper


def _owner_from_chat_request(request: Request, user) -> str | None:
    logged = _coerce_owner(user)
    if logged:
        return logged
    try:
        from config import ALLOW_PUBLIC_GUEST_CHAT
        from Login_system.guest_session import GUEST_OWNER_HEADER, is_valid_guest_id
    except Exception:
        return None
    if not ALLOW_PUBLIC_GUEST_CHAT:
        return None
    guest_hdr = request.headers.get(GUEST_OWNER_HEADER) or request.headers.get(
        str(GUEST_OWNER_HEADER).lower()
    )
    if guest_hdr and is_valid_guest_id(guest_hdr):
        return str(guest_hdr).strip()
    return None


def require_chat_access(role=None):
    """Authenticated user or anonymous guest (X-Guest-Owner) for chat APIs only."""

    def wrapper(request: Request):
        token = request.cookies.get(SESSION_COOKIE)
        user = None
        if token:
            user, err = load_and_validate_session_token(serializer, token)
            if user is None:
                user = None
        owner = _owner_from_chat_request(request, user)
        if not owner:
            raise HTTPException(status_code=401, detail="Authentication required.")
        if role and user and user.get("role") != role:
            raise HTTPException(status_code=403, detail="Forbidden.")
        return {"user": user, "owner": owner}

    return wrapper


def require_roles(*allowed_roles):
    def wrapper(request: Request):
        token = request.cookies.get(SESSION_COOKIE)
        if not token:
            raise HTTPException(status_code=401, detail="Authentication required.")
        user, err = load_and_validate_session_token(serializer, token)
        if user is None:
            raise HTTPException(status_code=401, detail=err or "Invalid session.")
        if allowed_roles and user.get("role") not in allowed_roles:
            raise HTTPException(status_code=403, detail="Forbidden.")
        return user
    return wrapper


def require_tenant_staff():
    return require_roles("admin", "master_admin", "superadmin")

register_voice_routes(app, require_login)

# ========== CSRF VERIFICATION HELPER ==========
# verify_csrf imported from backend.rag_middleware

# ========== ARABIC LANGUAGE SUPPORT ==========

# Arabic refusal message for off-topic questions (outside system scope)




# ---- Arabic→English translation cache ----
# Avoids a ~700-900ms Google Translate API round-trip on repeated queries
# (same question asked multiple times, demo runs, test loops, etc.).
# Key: original Arabic text (stripped).  Value: translated English text.
# Capped at 512 entries to bound memory; LRU eviction via collections.OrderedDict.
import collections as _collections
_AR_EN_CACHE: "_collections.OrderedDict[str, str]" = _collections.OrderedDict()
_AR_NON_LLM_QUERY_CACHE: "_collections.OrderedDict[str, Dict[str, Any]]" = _collections.OrderedDict()

# ---- Final grounded English→Arabic answer translation cache ----
# Keyed only by the already-selected final answer text and target language.
# This cache never stores retrieved chunks or ungrounded intermediate drafts.
_FINAL_AR_TRANSLATION_CACHE: "_collections.OrderedDict[str, str]" = _collections.OrderedDict()
# --- Phase 8H refactor: block extracted to backend.retrieval.arabic, bound to this live
# module via bind_server so extracted helpers reach shared state/engine fns.
from backend.retrieval import arabic as _ext_mod_arabic
_ext_mod_arabic.bind_server(_sys.modules[__name__])
from backend.retrieval.arabic import (
    _ALLOWED_LATIN_BRANDS,
    _AR_ITEM_TRANSLATION_CACHE_MAX,
    _AR_TTS_DIGIT_MAP,
    _BULLET_LINE_RE,
    _FINAL_AR_TRANSLATION_CACHE_MAX,
    _allow_latin_token_in_arabic_text,
    _ar_item_translation_cache_get,
    _ar_item_translation_cache_key,
    _ar_item_translation_cache_put,
    _arabic_structural_search_hints,
    _build_external_arabic_explanation_query,
    _build_fast_arabic_explanation_query,
    _build_llm_arabic_explanation_query,
    _build_non_llm_arabic_explanation_query,
    _clean_english_search_query_candidate,
    _expand_english_retrieval_query_terms,
    _extract_latin_runs_from_query,
    _final_ar_translation_cache_get,
    _final_ar_translation_cache_key,
    _final_ar_translation_cache_put,
    _is_compact_arabic_item_translation,
    _maybe_improve_arabic_translation_retrieval,
    _normalize_arabic_keyword_for_non_llm_query,
    _parse_bullet_list_items,
    _preprocess_for_tts,
    _repair_fast_arabic_search_query,
    _retrieval_candidate_strength,
    _sanitize_arabic_text,
    _translate_arabic_query_for_search_with_llm,
    _translation_retrieval_is_weak,
    translate_with_llm,
)

# ---- Per-item Arabic translation cache (deterministic list fast path) ----
# Stores per-item English→Arabic translations so repeated bullet items in
# different lists (e.g. "Planning") translate instantly on subsequent runs.
# The key always includes the answer-type bucket, the target language, and a
# normalized lowercase form of the source item — never raw retrieved chunks.
_AR_ITEM_TRANSLATION_CACHE: "_collections.OrderedDict[str, str]" = _collections.OrderedDict()

# ---- Fast response cache (simple factual/definition queries) ----
_SIMPLE_RAG_CACHE: "_collections.OrderedDict[str, dict]" = _collections.OrderedDict()
_LAST_LATENCY_BREAKDOWN: Dict[str, Dict[str, float]] = {}














# _is_arabic_text moved to backend/utils/text.py (Phase 1 refactor); imported above.



















































# ---- Per-item Arabic translation cache helpers (Phase 10) ----










import re as _re_mod

# Latin tokens inside Arabic text are kept only when they look like generic
# acronyms or product/code identifiers. No brand or domain whitelist.






# ---- Arabic digit-to-word table for TTS normalization ----






































































































# --- Phase 3 refactor: language-resolution logic moved to backend.services ---
# _detect_language and _resolve_user_language now live in
# backend/services/language_service.py. Re-imported here to preserve the
# original module-level names and behavior.
from backend.services.language_service import _detect_language, _resolve_user_language




















# ---------------------------------------------------------------------------
# PHASE 11B — CONTROLLED EXPLANATION MODE (no retrieval/reranker parameter changes)
# ---------------------------------------------------------------------------
# Generic explanation-intent detection (English + Arabic) used to:
#   1. Append a strict "EXPLANATION MODE" instruction block to the system
#      prompt so already-retrieved chunks are summarized in 2-5 short
#      grounded lines without merging unrelated topics.
#   2. Filter the already-retrieved doc list down to the chunks that share
#      at least one query-content token (contamination guard) — this is a
#      post-retrieval reuse of existing chunks.
#   3. If a counted/symbolic explanation loses its short anchor during strict
#      narrowing, reuse the existing active-source lexical symbolic-list rescue
#      and accept only an anchor sentence plus adjacent explanatory support.
# No domain words, no hardcoded answers, no top_k change, no reranker change.

# Arabic explanation intent: لماذا / كيف / ما دور / ما العلاقة / كيف يساهم
# plus standalone forms (دور / أهمية / علاقة / يساهم / يؤثر) that surface
# the same explanation intent in conversational Arabic.

# Helper words that should NOT count as topic tokens when filtering chunks
# for explanation queries (they describe the *intent*, not the *topic*).












































































































# MP-C15 — Structure-aware definition recovery.
# When the strict definition route returns nothing, real documents often
# express a concept's definition through structure rather than a single
# "X is Y" sentence:
#   A) heading/label line followed by explanatory prose
#   B) table/classification row whose label matches the entity, followed
#      by an adjacent paragraph that explains it
#   C) concept paragraph followed by a list of defining characteristics
# This helper looks for an entity-anchored heading/label/row in the
# retrieved chunks and returns the best-scored adjacent defining sentence.
# Pronoun-led sentences are allowed only when their antecedent is the
# heading anchor we just located. Generic — no domain words; uses
# structural cues only.

# MP-C15 corpus cache — small lazy snapshot of every chunk in the active
# vector store. The retrieval pipeline's quality filter caps results at
# 3 chunks, so structurally-anchored content (e.g. an "Elements of X:"
# block) often never reaches the structure-aware helper through normal
# search. We bypass that cap by scanning the raw collection text once
# and filtering by entity-stem occurrence at query time. Generic — no
# domain words. Safe for small corpora (≤ a few thousand chunks).
_MPC15_CORPUS_CACHE: dict = {"chunks": None, "version": None}






















































































































from backend.rag_chunk_heuristics import looks_table_or_heading_like_chunk as _looks_table_or_heading_like_chunk






































# Run checklist (definition selection):
# - restart server
# - test `what is classical approach`
# - test `what is scientific management`




















# Value shapes the evidence extractor can recognise. None of these encode a
# specific amount — they only describe the *form* of a number to read from text.











# NOTE: The former concept-keyed extractors (FDIC / ACH / wire / instant /
# fastest) were removed. All numeric/value fact answers now flow through the
# single generic `_extract_evidence_value_sentence`, called directly from
# `_extract_table_fact_answer`. There are no domain-specific extractors left.






















































# (Dead code removed)





















































# MP-C4: Generic OCR token-repair for list candidates.
# Splits two purely structural OCR-glue patterns BEFORE list coherence
# validation rejects partially noisy lists. Both rules are language-level
# (English function words / CamelCase boundaries) and domain-agnostic — they
# carry no topic vocabulary, no PDF-specific terms, and apply equally to any
# document corpus. Examples handled (all generic):
#   "PlanningProcess"        -> "Planning Process"   (CamelCase boundary)
#   "Thefirst"               -> "The first"          (determiner + word)
#   "Variousfactors"         -> "Various factors"    (quantifier + word)
#   "andforemost"            -> "and foremost"       (conjunction + word)
# Random garbage ("kjsdfhskdf") is NOT split and remains rejectable.
# Sort by descending length so longer prefixes win the alternation
# (e.g. "These" wins over "The" for "Theseterms").
#   avoids over-splitting legitimate lowercase words like "influence",
#   "another", "thereby" that share a prefix substring.








# MP-C2 FIX: Generic, purely structural/linguistic signals for choosing between
# competing definition-sentence candidates. NO domain words, NO topic words,
# NO query-to-answer mappings. Only sentence-shape evidence.






































































































































# --- Phase 8H refactor: block extracted to backend.services.rag_service, bound to this live
# module via bind_server so extracted helpers reach shared state/engine fns.
from backend.services import rag_service as _ext_mod_rag_service
_ext_mod_rag_service.bind_server(_sys.modules[__name__])
from backend.services.rag_service import (
    _ROUTER_DIRECT_ROUTES,
    call_llm_with_rag,
)




























































































# MP-C6: Generic heading/figure-caption anchored subsection extraction.
# When a chunk's body contains a numbered subsection heading (e.g. "1.2 Foo Bar :")
# or a figure/table caption (e.g. "Table 2.1: Foo Bar") whose title overlaps the
# discriminating tokens of the query, restrict downstream list extraction to the
# region that follows that anchor (until the next anchor whose title does NOT
# overlap the query). Pure structural — no domain words, no question templates.











# ========== HELPER: RAG+LLM ==========

# (Structured extraction logic removed to favor pure RAG pipeline)







# ========== STREAMING LLM FOR REAL-TIME SENTENCE TTS ==========
import re as _re
_sentence_end_pattern = _re.compile(r'(?<=[.!?])\s+')
# ---------------------------------------------------------------------------
# Streaming LLM timeout constants (in seconds)
# ---------------------------------------------------------------------------
STREAM_FIRST_TOKEN_TIMEOUT_S = 15.0   # Timeout for first token from LLM (seconds)
STREAM_MID_TOKEN_TIMEOUT_S = 5.0      # Timeout for subsequent tokens (seconds)

# ---------------------------------------------------------------------------
# TTS text-quality helper: digit normalization only
# ---------------------------------------------------------------------------

# Adaptive TTS chunk sizing — adjusts words-per-chunk based on real-time perf
from backend.adaptive_chunk_manager import adaptive_manager, chunk_text_by_words
# Streaming LLM timeout constants (in seconds)
# ---------------------------------------------------------------------------
STREAM_FIRST_TOKEN_TIMEOUT_S = 15.0   # Timeout for first token from LLM (seconds)
STREAM_MID_TOKEN_TIMEOUT_S = 5.0      # Timeout for subsequent tokens (seconds)

# Adaptive TTS chunk sizing — adjusts words-per-chunk based on real-time perf
from backend.adaptive_chunk_manager import adaptive_manager, chunk_text_by_words









# ========== QUERY ENDPOINT ==========
class ConversationMessageRequest(BaseModel):
    role: str
    text: str
    tenant_id: Optional[int] = None


class ConversationCreateRequest(BaseModel):
    active_tenant_id: Optional[int] = None
    title: Optional[str] = None


class ConversationActiveTenantRequest(BaseModel):
    active_tenant_id: int


class ConversationRenameRequest(BaseModel):
    title: str


class QueryRequest(BaseModel):
    text: str
    conversation_id: Optional[str] = None
    tenant_id: Optional[int] = None


# --- Phase 8C refactor: /conversations CRUD routes moved to
# backend.routers.conversation_router and bound to this live module via the
# factory pattern (paths/methods/responses unchanged).
from backend.routers.conversation_router import build_conversation_router as _build_conversation_router
app.include_router(_build_conversation_router(_sys.modules[__name__]))


@app.post("/query")
async def query_rag(data: QueryRequest, request: Request, user=Depends(require_login())):
    _current_user_query.set(str(data.text or ""))
    _owner = _coerce_owner(user)
    persistent_conversation_id: str | None = None
    if data.conversation_id:
        persistent_conversation_id = str(data.conversation_id)
        chat_tid = _resolve_chat_tenant_id(data.tenant_id, persistent_conversation_id, _owner)
        get_or_create_conversation(persistent_conversation_id, owner=_owner, active_tenant_id=chat_tid)
        connection_id = persistent_conversation_id
        append_conversation_message(
            persistent_conversation_id, "user", data.text, tenant_id=chat_tid, owner=_owner
        )
        bind_conversation_memory(connection_id, persistent_conversation_id)
    else:
        chat_tid = assert_chat_tenant_allowed(user, data.tenant_id) if data.tenant_id is not None else DEFAULT_TENANT_ID
        if data.tenant_id is None:
            raise HTTPException(status_code=400, detail="tenant_id required when conversation_id is omitted")
        _uname = (user or {}).get("username") if isinstance(user, dict) else None
        if _uname:
            connection_id = f"http_user_{_uname}"
        else:
            try:
                _tok = request.cookies.get(SESSION_COOKIE)
            except Exception:
                _tok = None
            if _tok:
                import hashlib as _hashlib
                connection_id = "http_sess_" + _hashlib.sha1(_tok.encode("utf-8", errors="ignore")).hexdigest()[:12]
            else:
                connection_id = "http_anon"
    logger.info("[FLOW] entering query_rag (tenant=%s)", chat_tid)
    logger.info("[FLOW] query_before = %s", (data.text or "")[:400])
    _post_text = data.text if _is_memory_rewrite_query(data.text) else _maybe_rewrite_about_entity_question(data.text)
    with _TenantScope(chat_tid):
        ai_response, retrieved_docs = await call_llm_with_rag(_post_text, connection_id, user)
    if persistent_conversation_id:
        append_conversation_message(
            persistent_conversation_id, "assistant", ai_response, tenant_id=chat_tid, owner=_owner
        )
        persist_runtime_memory(connection_id, persistent_conversation_id)
    # Skip definition/cleanup post-processing for follow-up clarifications:
    # those answers are already finalized inside _handle_followup_query and
    # would otherwise be reshaped by definition-style cleaners that expect a
    # fresh retrieval, not a clarification.
    if _is_followup_query(_post_text, connection_id):
        # Map the internal strict sentinel ("Not found in the document.") to the
        # friendly customer-support message so it is never shown to the customer.
        # This only rewrites the not-found sentinel; real follow-up answers pass
        # through unchanged (so definition-style cleaners are still skipped).
        if str(ai_response or "").strip().lower() == RAG_NO_MATCH_RESPONSE.lower():
            ai_response = _finalize_user_visible_answer(_post_text, ai_response, retrieved_docs=retrieved_docs)
        logger.info("[HTTP FINAL ANSWER BEFORE RETURN] (followup) %s", str(ai_response or "")[:320])
        return {"answer": ai_response}
    if _classify_query_family_v2(_post_text) != "fact_entity":
        normalized_query_for_output, _ = _normalize_definition_query_before_retrieval(_post_text)
        ai_response = _force_clean_definition_sentence(normalized_query_for_output or _post_text, ai_response, retrieved_docs)
    ai_response = _cleanup_final_answer_text(ai_response)
    ai_response = _finalize_user_visible_answer(_post_text, ai_response, retrieved_docs=retrieved_docs)
    logger.info("[HTTP FINAL ANSWER BEFORE RETURN] %s", str(ai_response or "")[:320])
    return {"answer": ai_response}

# ========== ANALYTICS API ==========
# --- Phase 8F refactor: /admin/analytics and /admin/errors moved to
# backend.routers.analytics_router (registered near the end of this module).


@app.get("/admin/knowledge", response_class=HTMLResponse)
def admin_knowledge_page(request: Request, user=Depends(require_tenant_staff())):
    html_path = Path(__file__).parent / "templates" / "admin_knowledge.html"
    if not html_path.exists():
        raise HTTPException(status_code=404, detail="Admin knowledge template not found.")
    content = html_path.read_text(encoding="utf-8")
    return HTMLResponse(content=content)


# --- Phase 8D refactor: /rag/files, /rag/debug, /rag/retrieve-debug and the
# other factory-safe KB routes moved to backend.routers.kb_router (registered
# near the end of this module). /debug/runtime-rag stays here because it
# introspects this module's own source via __name__/globals().


@app.get("/debug/runtime-rag")
def debug_runtime_rag(query: str | None = None, user=Depends(require_tenant_staff())):
    """Temporary admin-only route: return live runtime introspection for RAG debugging.

    Returns JSON with process info, inspected source for key functions, runtime constants,
    and an optional live retrieval probe when a query parameter is supplied.
    """
    _kb_admin_scope_tenant(user)
    _request_tenant_id.set(require_request_tenant(user))
    import os as _os
    import sys as _sys
    import inspect as _inspect
    import re as _re

    out: dict = {}
    # 1) Process info
    out['process'] = {
        'pid': _os.getpid(),
        'cwd': _os.getcwd(),
    }

    # Module file paths (if loaded)
    mod_assist = _sys.modules.get('backend.assistify_rag_server')
    mod_pdf = _sys.modules.get('backend.pdf_ingestion_rag')
    out['modules'] = {
        'backend.assistify_rag_server': getattr(mod_assist, '__file__', None) if mod_assist else None,
        'backend.pdf_ingestion_rag': getattr(mod_pdf, '__file__', None) if mod_pdf else None,
    }

    # 2) Live source snippets
    def safe_getsource(obj):
        try:
            return _inspect.getsource(obj)
        except Exception as e:
            return f'*** source unavailable: {e}'

    out['source'] = {
        '_rewrite_query_for_retrieval': safe_getsource(_rewrite_query_for_retrieval) if '_rewrite_query_for_retrieval' in globals() else 'MISSING',
        'call_llm_streaming': safe_getsource(call_llm_streaming) if 'call_llm_streaming' in globals() else 'MISSING',
        'call_llm_with_rag': safe_getsource(call_llm_with_rag) if 'call_llm_with_rag' in globals() else 'MISSING',
    }

    # 3) Runtime constants / derived values
    try:
        probe_q = re.sub(r"\s+", " ", str(query or "").strip())
        out['runtime'] = {
            'RAG_STRICT_DISTANCE_THRESHOLD': RAG_STRICT_DISTANCE_THRESHOLD,
            'rewrite_probe_returns': _rewrite_query_for_retrieval(probe_q) if probe_q and '_rewrite_query_for_retrieval' in globals() else None,
        }
    except Exception as e:
        out['runtime'] = {'error': str(e)}

    # 3b) show exact lines around any 'top_k_req' assignments found in module source
    module_src = ""
    try:
        _mod = _sys.modules.get(__name__)
        module_src = _inspect.getsource(_mod) if _mod is not None else ""
        lines = module_src.splitlines()
        hits = []
        for i, ln in enumerate(lines):
            if 'top_k_req' in ln:
                start = max(0, i-3)
                end = min(len(lines), i+4)
                snippet = '\n'.join(lines[start:end])
                hits.append({'line_index': i+1, 'context': snippet})
        out['top_k_sites'] = hits
    except Exception as e:
        out['top_k_sites'] = {'error': str(e)}

    # 4) Live probe execution
    probe_q = re.sub(r"\s+", " ", str(query or "").strip())
    if not probe_q:
        out['probe'] = {
            'skipped': True,
            'reason': 'provide a query parameter to run a live retrieval probe',
        }
        return out
    try:
        rewritten = _rewrite_query_for_retrieval(probe_q) if '_rewrite_query_for_retrieval' in globals() else probe_q
        # determine top_k to use by looking for an explicit assignment in module
        top_k_used = None
        m = _re.search(r'top_k_req\s*=\s*(\d+)', module_src)
        if m:
            try:
                top_k_used = int(m.group(1))
            except Exception:
                top_k_used = 10
        if top_k_used is None:
            top_k_used = 10

        # determine distance threshold function if available
        dist = None
        if '_distance_threshold_for_query' in globals():
            try:
                dist = _distance_threshold_for_query(rewritten)
            except Exception:
                dist = 1.0
        else:
            dist = 1.0

        # Execute retrieval probe via live_rag
        try:
            docs = _active_rag().search(rewritten, top_k=top_k_used, distance_threshold=dist, return_dicts=True, enable_rerank=True)
            logger.info("[RERANK ACTIVE]")
        except Exception as e:
            docs = {'error': f'retrieval failed: {e}'}

        # Format first 3 chunks
        preview = []
        if isinstance(docs, list):
            for d in (docs or [])[:3]:
                text_preview = (d or {}).get('text') or ((d or {}).get('document') or '')
                md = (d or {}).get('metadata') or {}
                preview.append({'text_preview': (text_preview[:240] if isinstance(text_preview, str) else str(text_preview)), 'metadata': md})

        out['probe'] = {
            'original_query': probe_q,
            'rewritten_query': rewritten,
            'top_k_used': top_k_used,
            'distance_threshold_used': dist,
            'first_3_chunks': preview,
        }
    except Exception as e:
        out['probe'] = {'error': str(e)}

    return out


# --- Phase 8F refactor: /analytics/summary, /analytics/comprehensive,
# /analytics/tts-performance, /analytics/errors and /analytics/feedback moved
# to backend.routers.analytics_router, bound to this live module via the
# factory pattern (paths/methods/responses unchanged).
from backend.routers.analytics_router import build_analytics_router as _build_analytics_router
app.include_router(_build_analytics_router(_sys.modules[__name__]))

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
# Chat UI is served by the Login server at /frontend/ (React build in assistify-ui-design/out/).
# This RAG server exposes API + WebSocket only; no HTML chat shell here.
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

# --- Phase 4 refactor: /health and /stats moved to backend.routers.health ---
# Handlers live in backend/routers/health.py and are bound to this live module
# (factory pattern) to avoid an import cycle. Paths/methods/responses unchanged.
from backend.routers.health import build_health_router as _build_health_router
app.include_router(_build_health_router(_sys.modules[__name__]))


# --- Phase 8D refactor: /kb_status moved to backend.routers.kb_router ---


@app.get("/assets/{filename}")
async def get_audio(filename: str, user=Depends(require_login())):
    tenant_id = require_request_tenant(user)
    scope_tid = None if int(tenant_id) == int(DEFAULT_TENANT_ID) else int(tenant_id)
    assets_dir = ASSETS_DIR if scope_tid is None else tenant_assets_dir(scope_tid)
    safe_name = Path(filename).name
    if not safe_name or safe_name != filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    file_path = assets_dir / safe_name
    try:
        resolved = file_path.resolve()
        if not str(resolved).startswith(str(assets_dir.resolve())):
            raise HTTPException(status_code=403, detail="Access denied")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=404, detail="File not found")
    if file_path.exists():
        return FileResponse(str(file_path), media_type="audio/wav")
    raise HTTPException(status_code=404, detail="File not found")

# ========== FILE UPLOAD ENDPOINT ==========
# Background tasks currently in flight, keyed by filename. Used to avoid
# duplicate concurrent indexing of the same upload and to keep strong
# references so asyncio doesn't garbage-collect a running task.
_pdf_indexing_tasks: dict = {}


def _maybe_recover_stale_kb_pipeline() -> bool:
    """Fail stuck uploads and reset the collection lock so the UI can recover."""
    state = str(_kb_pipeline_state.get("state") or "ready").lower()
    if state not in {"uploading", "processing"}:
        return False
    updated = float(_kb_pipeline_state.get("updated_at") or 0)
    if not updated:
        return False
    stale_for = time.time() - updated
    if stale_for < KB_PIPELINE_STALE_TIMEOUT_S:
        return False
    filename = _kb_pipeline_state.get("filename")
    logger.warning(
        "[KB WATCHDOG] pipeline stale %.0fs | state=%s stage=%s filename=%s — recovering",
        stale_for,
        state,
        _kb_pipeline_state.get("stage"),
        filename,
    )
    for fn, task in list(_pdf_indexing_tasks.items()):
        if task and not task.done():
            task.cancel()
            logger.warning("[KB WATCHDOG] cancelled background task for %s", fn)
        _pdf_indexing_tasks.pop(fn, None)
    _reset_collection_mutation_lock()
    _set_kb_pipeline_state(
        "failed",
        message=(
            f"Ingestion timed out after {int(stale_for)}s "
            f"(stage={_kb_pipeline_state.get('stage')}). Please retry."
        ),
        filename=filename,
    )
    return True


@asynccontextmanager
async def _collection_mutation(timeout: Optional[float] = None):
    """Serialize Chroma mutations with a bounded wait (prevents infinite UI freeze)."""
    lock_timeout = float(timeout if timeout is not None else COLLECTION_MUTATION_LOCK_TIMEOUT_S)
    lock = _get_collection_mutation_lock()
    try:
        await asyncio.wait_for(lock.acquire(), timeout=lock_timeout)
    except asyncio.TimeoutError:
        _maybe_recover_stale_kb_pipeline()
        raise RuntimeError(
            f"Timed out waiting {lock_timeout:.0f}s for KB collection lock "
            f"(another upload may be stuck). Try again shortly."
        )
    try:
        yield
    finally:
        lock.release()


async def _finalize_tenant_pdf_upload_background(
    *,
    tenant_id: int,
    filename: str,
    original_filename: str,
    file_ext: str,
    save_path: Path,
    source_metadata: dict,
) -> None:
    """Isolated ingestion path for NON-default tenants.

    The default tenant keeps the historical, finely-tuned blue/green ingestion
    pipeline (`_finalize_pdf_upload_background`). Every other business indexes
    straight into its own '_latest' collection via the tenant-aware knowledge
    base helpers, so a business's documents are physically stored in a separate
    ChromaDB collection and can never be retrieved by another tenant.
    """
    try:
        _set_kb_pipeline_stage("extracting", message="Extracting text", filename=filename)
        text = await asyncio.to_thread(_extract_text_from_asset, save_path)
        if not text.strip():
            _set_kb_pipeline_state("failed", message="No extractable text found", filename=filename)
            return

        normalized_filename = str(
            (source_metadata or {}).get("normalized_filename")
            or normalize_uploaded_filename(original_filename)
        )
        doc_id = str(
            (source_metadata or {}).get("source_doc_id")
            or canonical_source_doc_id(normalized_filename or original_filename)
        )
        metadata = dict(source_metadata or {})
        metadata.update({
            "file_ext": file_ext,
            "ingestion_owner": "rag_server_upload_tenant",
            "tenant_id": int(tenant_id),
        })

        _set_kb_pipeline_stage("chunking", message="Chunking document", filename=filename)
        deleted = 0
        added = 0
        try:
            async with _collection_mutation():
                # Remove any prior chunks for this file within THIS tenant only.
                try:
                    prior_id = await asyncio.to_thread(
                        find_base_doc_id_by_filename, normalized_filename, tenant_id
                    )
                    if prior_id:
                        deleted += int(
                            await asyncio.to_thread(
                                delete_documents_with_prefix, str(prior_id), tenant_id
                            )
                            or 0
                        )
                except Exception as _del_err:
                    logger.warning("[TENANT UPLOAD] prior-chunk cleanup skipped: %s", _del_err)
                try:
                    deleted += int(
                        await asyncio.to_thread(delete_documents_with_prefix, str(doc_id), tenant_id)
                        or 0
                    )
                except Exception:
                    pass
                _cad = await asyncio.wait_for(
                    asyncio.to_thread(
                        chunk_and_add_document,
                        doc_id=doc_id,
                        text=text,
                        metadata=metadata,
                        kb_version=_kb_global_version + 1,
                        tenant_id=tenant_id,
                    ),
                    timeout=INGEST_INDEX_TIMEOUT_S,
                )
                added = int(_cad) if isinstance(_cad, int) else 0
        except asyncio.TimeoutError:
            _set_kb_pipeline_state(
                "failed",
                message=f"Indexing timed out after {int(INGEST_INDEX_TIMEOUT_S)}s",
                filename=filename,
            )
            return
        except RuntimeError as lock_err:
            _set_kb_pipeline_state("failed", message=str(lock_err), filename=filename)
            return

        # Force the tenant retrieval manager to rebind to its (now populated)
        # collection on the next query so new chunks are immediately visible.
        try:
            mgr = get_tenant_rag(tenant_id)
            mgr.vs = None
        except Exception as _rebind_err:
            logger.warning("[TENANT UPLOAD] retrieval rebind skipped: %s", _rebind_err)

        # Phase 13C: register the newly indexed document in THIS tenant's
        # active-source set. Retrieval is collection-per-tenant isolated, so the
        # anti-leak filter must know the new source belongs to the tenant whose
        # collection just received the chunks. Register all metadata aliases
        # together because retrieved chunks may expose either filename or doc id.
        if added > 0:
            _register_active_source_aliases(
                sorted(_source_aliases_from_metadata(metadata, normalized_filename, filename)),
                tenant_id=tenant_id,
            )
            logger.info(
                "[TENANT UPLOAD] active source registered | tenant=%s filename=%s active_sources=%s",
                tenant_id,
                filename,
                sorted(_get_active_sources(tenant_id=tenant_id)),
            )

        _set_kb_pipeline_state(
            "ready",
            message=f"Indexed {added} chunk(s) for tenant {tenant_id}",
            filename=filename,
        )
        logger.info(
            "[TENANT UPLOAD] tenant=%s filename=%s indexed=%s deleted=%s collection=%s",
            tenant_id, filename, added, deleted, tenant_collection_name(tenant_id),
        )
        try:
            await invalidate_all_caches(
                action="upload", filename=filename,
                chunks_added=added, chunks_deleted=deleted,
                triggered_by="upload_tenant",
            )
        except Exception:
            pass
    except Exception as e:
        logger.exception("[TENANT UPLOAD] finalize failed for %s: %s", filename, e)
        _set_kb_pipeline_state("failed", message=f"Tenant ingestion failed: {e}", filename=filename)


async def _finalize_pdf_upload_background(
    *,
    filename: str,
    original_filename: str,
    file_ext: str,
    save_path: Path,
    file_size_mb: float,
    target_collection_name: str,
    old_single_mode_collection: str,
    source_metadata: dict,
) -> None:
    """Run the heavy half of /upload_rag (text extract + chunk + embed +
    Chroma write + state activation) outside the request lifecycle so the
    HTTP response can return in <500 ms.

    Only changes the EXECUTION MODEL — the actual indexing logic, blue/green
    swap, GC and active-source registration are byte-for-byte identical to
    the previous synchronous implementation.
    """
    global _current_active_doc_id
    swap_t0 = time.time()
    logger.info("[SWAP START] filename=%s size=%.2fMB ext=%s", filename, file_size_mb, file_ext)
    source_doc_id = str((source_metadata or {}).get("source_doc_id") or "").strip()
    normalized_filename = str((source_metadata or {}).get("normalized_filename") or normalize_uploaded_filename(original_filename)).strip()

    try:
        # ---- Collection diagnostics (was previously logged inside upload_rag) ----
        try:
            kb_col = get_or_create_collection()
            kb_col_name = kb_col.name if kb_col else "<none>"
        except Exception as kb_col_err:
            kb_col_name = f"<error:{kb_col_err}>"

        retrieval_col_name = getattr(getattr(live_rag, "vs", None), "collection", None)
        retrieval_col_name = getattr(retrieval_col_name, "name", "<none>")
        logger.info(
            "upload_rag(bg) start | filename=%s mode=%s kb_collection=%s retrieval_collection=%s",
            filename,
            _active_doc_registry.get("mode", RAG_DOC_MODE),
            kb_col_name,
            retrieval_col_name,
        )
        if kb_col_name != retrieval_col_name:
            logger.warning("upload_rag(bg) collection mismatch | kb=%s retrieval=%s", kb_col_name, retrieval_col_name)

        # ---- 1) Read text from the saved asset ----
        _set_kb_pipeline_stage("extracting", message="Extracting text", filename=filename)
        read_t0 = time.time()
        text = ""
        extracted_page_count = 0
        non_empty_pages = 0
        extraction_errors = 0
        if file_ext == "txt":
            try:
                content_bytes = save_path.read_bytes()
                try:
                    text = content_bytes.decode("utf-8")
                except Exception:
                    text = content_bytes.decode(errors="ignore")
            except Exception as txt_err:
                logger.error("[SWAP FAIL] TXT read failed | filename=%s err=%s", filename, txt_err)
                _set_kb_pipeline_state("failed", message=f"TXT read failed: {txt_err}", filename=filename)
                return
            extracted_page_count = 1
            non_empty_pages = 1 if text.strip() else 0
            logger.info(f"  Extracted TXT: {len(text)} chars, ~{len(text.split())} words")
        else:
            # Run the heavy synchronous PDF extraction off the event loop so
            # WebSocket handlers and status polling remain responsive
            text = await asyncio.to_thread(_extract_text_from_asset, save_path)
            if not text.strip():
                logger.warning(
                    "  PDF extraction produced empty text | filename=%s",
                    filename,
                )
                _set_kb_pipeline_state(
                    "failed",
                    message="PDF extraction produced no usable text (try re-upload or OCR)",
                    filename=filename,
                )
                return
            extracted_page_count = text.count("[PAGE_START:")
            non_empty_pages = sum(
                1 for block in text.split("[PAGE_START:")
                if block.strip() and not block.strip().startswith("]")
            )
            logger.info(f"  Extracted PDF: {len(text)} chars, ~{len(text.split())} words from {extracted_page_count} pages")
            logger.info(
                "  PDF extraction diagnostics | filename=%s pages=%s non_empty_pages=%s extraction_errors=%s chars=%s",
                filename,
                extracted_page_count,
                non_empty_pages,
                extraction_errors,
                len(text),
            )

        text_extract_ms = int((time.time() - read_t0) * 1000)
        logger.info("[INGEST PERF] stage=text_extract ms=%s", text_extract_ms)
        logger.info("[PDF READ DONE] filename=%s elapsed=%.2fs chars=%d", filename, time.time() - read_t0, len(text))
        _record_kb_stage("pdf_read_done")

        # ---- 2) Chunk + embed + write to Chroma ----
        doc_id = source_doc_id or canonical_source_doc_id(normalized_filename or original_filename)
        metadata = dict(source_metadata or {})
        metadata.update({"file_size_mb": file_size_mb, "file_ext": file_ext, "ingestion_owner": "rag_server_upload"})

        logger.info(f"  Starting chunking and embedding indexing (batch processing)...")
        _set_kb_pipeline_stage("chunking", message="Chunking document", filename=filename)
        chunk_t0 = time.time()
        active_collection = ""
        gc_report: dict = {}
        indexing_details: dict = {}
        try:
            async with _collection_mutation():
                delete_report = await asyncio.to_thread(
                    delete_documents_by_source_identity,
                    source_doc_id=str(metadata.get("source_doc_id") or doc_id),
                    original_filename=str(metadata.get("original_filename") or original_filename),
                    stored_filename=str(metadata.get("stored_filename") or filename),
                    normalized_filename=str(metadata.get("normalized_filename") or normalized_filename),
                    upload_id=str(metadata.get("upload_id") or ""),
                    document_version=str(metadata.get("document_version") or ""),
                    doc_prefix=doc_id,
                    extra_keys=[filename, original_filename],
                )
                logger.info(
                    "[INGEST DELETE VERIFY] upload_prewrite filename=%s deleted=%s remaining=%s",
                    filename,
                    delete_report.get("deleted_count", 0),
                    delete_report.get("remaining_count", 0),
                )
                # Run the CPU/IO-heavy embedder off the event loop so /ws and
                # other coroutines (including the KB-ready gate) stay responsive.
                _raw_indexing = await asyncio.wait_for(
                    asyncio.to_thread(
                        chunk_and_add_document,
                        doc_id,
                        text,
                        metadata,
                        _kb_global_version + 1,
                        True,
                        target_collection_name,
                        lambda event: _on_ingest_progress(event, filename),
                    ),
                    timeout=INGEST_INDEX_TIMEOUT_S,
                )
                indexing_details = _raw_indexing if isinstance(_raw_indexing, dict) else {}
                logger.info("[CHUNKING DONE] filename=%s generated=%s",
                            filename, indexing_details.get("generated_chunks"))
                _record_kb_stage("chunking_done")
                logger.info("[EMBEDDING DONE] filename=%s elapsed=%.2fs",
                            filename, time.time() - chunk_t0)
                _record_kb_stage("embedding_done")

                chunks_indexed = int((indexing_details).get("indexed_chunks") or 0)
                if chunks_indexed > 0:
                    _set_kb_pipeline_state(
                        "processing",
                        message="Indexing completed; activating live retrieval",
                        filename=filename,
                    )
                    _set_kb_pipeline_stage("activating", message="Activating live retrieval", filename=filename)
                    active_collection = _sync_live_retrieval_collection((indexing_details).get("collection"))
                    logger.info("[DB WRITE DONE] filename=%s collection=%s indexed=%s",
                                filename, active_collection, chunks_indexed)
                    _record_kb_stage("db_write_done")
                    _record_kb_stage("active_switch_done")

                    if _active_doc_registry.get("mode", RAG_DOC_MODE) == "single":
                        try:
                            from backend.knowledge_base import garbage_collect_support_collections
                            gc_report = garbage_collect_support_collections(
                                active_collection_name=active_collection,
                                delete_non_empty=True,
                                prefix="support_docs_v3_",
                            )
                        except Exception as gc_err:
                            logger.warning(f"Blue/Green GC skipped due to error: {gc_err}")
        except asyncio.TimeoutError:
            _set_kb_pipeline_state(
                "failed",
                message=f"Indexing timed out after {int(INGEST_INDEX_TIMEOUT_S)}s",
                filename=filename,
            )
            logger.error(
                "[SWAP FAIL] filename=%s reason=ingest_timeout total=%.2fs",
                filename,
                time.time() - swap_t0,
            )
            return
        except RuntimeError as lock_err:
            _set_kb_pipeline_state("failed", message=str(lock_err), filename=filename)
            return
        except Exception as upsert_err:
            _set_kb_pipeline_state("failed", message=f"Indexing failed: {upsert_err}", filename=filename)
            logger.exception("upload_rag(bg) upsert failure | filename=%s doc_id=%s error=%s",
                             filename, doc_id, upsert_err)
            return

        chunks_indexed = int(indexing_details.get("indexed_chunks") or 0)
        chunks_generated = int(indexing_details.get("generated_chunks") or 0)
        batch_errors = indexing_details.get("batch_errors") or []
        logger.info(
            "upload_rag(bg) indexing diagnostics | filename=%s doc_id=%s collection=%s generated=%s indexed=%s batch_errors=%s",
            filename,
            doc_id,
            indexing_details.get("collection"),
            chunks_generated,
            chunks_indexed,
            len(batch_errors),
        )
        if chunks_generated == 0:
            logger.warning("upload_rag(bg) generated zero chunks | filename=%s reason=%s",
                           filename, indexing_details.get("reason", ""))

        if chunks_indexed > 0:
            # Atomically activate the new doc as the single source of truth.
            _register_active_source_aliases(
                sorted(_source_aliases_from_metadata(metadata, normalized_filename, filename))
            )
            _current_active_doc_id = _normalize_source_label(normalized_filename or filename)
            logger.info(
                "upload_rag(bg) post-index | filename=%s active_doc_id=%s active_collection=%s active_sources=%s",
                filename,
                _current_active_doc_id,
                active_collection,
                sorted(_get_active_sources()),
            )
            if gc_report:
                logger.info(
                    "upload_rag(bg) GC summary | deleted=%s skipped=%s errors=%s",
                    (gc_report or {}).get("deleted_count", 0),
                    (gc_report or {}).get("skipped_count", 0),
                    len((gc_report or {}).get("errors") or []),
                )
            _mark_assets_recently_indexed(filename, seconds=120.0)
            try:
                await invalidate_all_caches(action="upload", filename=filename,
                                             chunks_added=chunks_indexed, triggered_by="admin")
            except Exception as cache_err:
                logger.warning("upload_rag(bg) cache invalidation failed: %s", cache_err)

            # ---- Verification probe: confirm the new source is actually retrievable ----
            # Direct metadata check on the active retrieval collection. Semantic
            # search is unreliable for very small documents (1-2 chunks), so we
            # query Chroma's metadata index directly for any chunk whose
            # filename / source matches the upload we just indexed.
            probe_ok = False
            probe_reason = ""
            target_source = _normalize_source_label(normalized_filename or filename)
            try:
                vs = getattr(live_rag, "vs", None)
                col = getattr(vs, "collection", None) if vs is not None else None
                if col is None:
                    probe_reason = "no live retrieval collection"
                else:
                    raw = await asyncio.to_thread(lambda: col.get(include=["metadatas"]))
                    metas = (raw or {}).get("metadatas") or []
                    matched = 0
                    for md in metas:
                        if isinstance(md, dict) and target_source and target_source in _metadata_source_keys(md):
                            matched += 1
                    if matched > 0:
                        probe_ok = True
                    else:
                        probe_reason = f"verification: 0 chunks with source={target_source} in collection"
            except Exception as probe_err:
                probe_reason = f"verification probe error: {probe_err}"
            _record_kb_stage("verification_done")
            if not probe_ok:
                _set_kb_pipeline_state("failed", message=f"Indexed but not retrievable: {probe_reason}", filename=filename)
                logger.warning("[KB READY DENIED] filename=%s reason=%s", filename, probe_reason)
                return

            _set_kb_pipeline_state("ready", message="Document indexed and active for retrieval", filename=filename)
            logger.info("[KB READY] filename=%s total=%.2fs chunks=%d", filename, time.time() - swap_t0, chunks_indexed)
        else:
            _set_kb_pipeline_state("failed", message="No chunks indexed from uploaded file", filename=filename)
            logger.warning("[SWAP FAIL] filename=%s reason=no_chunks total=%.2fs", filename, time.time() - swap_t0)
    except Exception as bg_err:
        logger.exception("[SWAP FAIL] background task crashed for %s: %s", filename, bg_err)
        _set_kb_pipeline_state("failed", message=f"Background indexing crashed: {bg_err}", filename=filename)
    finally:
        # Drop our task handle so re-uploads of the same filename are allowed.
        _pdf_indexing_tasks.pop(filename, None)


# --- Phase 8E refactor: /upload_rag moved to backend.routers.ingestion_router
# (registered near the end of this module via the factory pattern).


# ========== LEGACY (DEAD) SYNCHRONOUS UPLOAD BODY — REMOVED ===============
# The previous in-line synchronous indexing body of /upload_rag has been
# fully replaced by `_finalize_pdf_upload_background` defined above.
# Removed in the async hot-swap upgrade.


# --- Phase 8G refactor: /rag/delete, /rag/update and PUT /rag/files/{filename}
# moved to backend.routers.chroma_router, bound to this live module via the
# factory pattern (paths/methods/responses unchanged).
from backend.routers.chroma_router import build_chroma_router as _build_chroma_router
app.include_router(_build_chroma_router(_sys.modules[__name__]))


def _reindex_asset_sync(
    path: Path,
    scope_tid,
    *,
    upload_id: str = "manual_reindex",
    ingestion_owner: str = "rag_server_reindex",
) -> dict:
    """Sync per-file reindex body — run via asyncio.to_thread to avoid blocking the event loop."""
    filename = path.name
    _set_kb_pipeline_stage("extracting", message="Reindexing file", filename=filename)
    text = _extract_text_from_asset(path)
    if not text.strip():
        raise RuntimeError("Extraction produced no usable text")

    original_filename = original_filename_from_stored(filename)
    metadata = build_canonical_source_metadata(
        original_filename=original_filename,
        stored_filename=filename,
        upload_id=upload_id,
        document_version=str(int(path.stat().st_mtime)),
    )
    metadata.update({"ingestion_owner": ingestion_owner, "file_ext": path.suffix.lower()})
    doc_id = str(metadata.get("source_doc_id") or canonical_source_doc_id(metadata.get("normalized_filename") or original_filename))
    delete_report = delete_documents_by_source_identity(
        source_doc_id=str(metadata.get("source_doc_id") or ""),
        original_filename=str(metadata.get("original_filename") or ""),
        stored_filename=str(metadata.get("stored_filename") or filename),
        normalized_filename=str(metadata.get("normalized_filename") or ""),
        doc_prefix=doc_id,
        tenant_id=scope_tid,
    )
    deleted = int(delete_report.get("deleted_count") or 0)
    _set_kb_pipeline_stage("chunking", message="Chunking document", filename=filename)
    _raw_chunks = chunk_and_add_document(
        doc_id=doc_id,
        text=text,
        metadata=metadata,
        kb_version=_kb_global_version + 1,
        progress_callback=lambda event, fn=filename: _on_ingest_progress(event, fn),
        tenant_id=scope_tid,
    )
    chunks = int(_raw_chunks) if isinstance(_raw_chunks, int) else 0
    return {
        "filename": filename,
        "chunks": chunks,
        "deleted_old": deleted,
        "delete_verification": delete_report,
    }


# --- Phase 8E refactor: /upload_rag, /rag/reindex-file, /rag/rebuild-active-sources
# and /rag/reindex-all moved to backend.routers.ingestion_router, bound to this
# live module via the factory pattern (paths/methods/responses unchanged).
from backend.routers.ingestion_router import build_ingestion_router as _build_ingestion_router
app.include_router(_build_ingestion_router(_sys.modules[__name__]))


# --- Phase 8D refactor: /rag/ready, /rag/clear-cache and /rag/doc-mode (GET/POST)
# moved to backend.routers.kb_router ---


# ========== TEXT-TO-SPEECH ENDPOINT (proxies to XTTS v2 microservice) ==========
#

# ========== VOICE WS CALLBACKS (Phase 1 — post-STT / typed text stay in RAG server) ==========

# --- Phase 8H refactor: block extracted to backend.services.voice_service, bound to this live
# module via bind_server so extracted helpers reach shared state/engine fns.
from backend.services import voice_service as _ext_mod_voice_service
_ext_mod_voice_service.bind_server(_sys.modules[__name__])
from backend.services.voice_service import (
    _on_ws_disconnect,
    _process_voice_transcript_ws,
    _process_ws_text_message,
)





# --- Phase 8K refactor: /ws and /ws/kb-events live in backend.routers.ws_router,
# which also owns the voice WS deps binding (_build_voice_ws_deps) and handler
# creation (create_rag_ws_handler) that previously lived here. The factory reads
# every dependency off this live server module, so the WebSocket protocol,
# payloads, auth and tenant behavior are byte-identical. build_ws_router also
# sets server._rag_ws_handler for backward compatibility.
from backend.routers.ws_router import build_ws_router as _build_ws_router
app.include_router(_build_ws_router(_sys.modules[__name__]))


# ========== KB MONITORING DASHBOARD ==========
# --- Phase 8D refactor: KB management routes (/kb_status, /rag/files,
# /rag/debug, /rag/retrieve-debug, /rag/ready, /rag/clear-cache, /rag/doc-mode,
# /admin/kb-monitor, /api/kb-stats, /api/kb-events, /internal/preflight) moved
# to backend.routers.kb_router and bound to this live module via the factory
# pattern (paths/methods/responses unchanged).
from backend.routers.kb_router import build_kb_router as _build_kb_router
app.include_router(_build_kb_router(_sys.modules[__name__]))

if __name__ == "__main__":
    import uvicorn
    # STABILIZATION: Never use --reload with GPU models (spawns duplicate processes)
    uvicorn.run(app, host="0.0.0.0", port=7000, reload=False)
        
