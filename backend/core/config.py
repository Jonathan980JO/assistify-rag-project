"""RAG-server runtime configuration flags and constants.

Extracted verbatim from ``assistify_rag_server.py`` during the Phase 8A
refactor. This module holds the server-local feature flags, Ollama endpoint
URLs, retrieval tuning constants and the startup preflight check that the
monolith previously defined inline.

Design notes (behavior-preserving):
- Base settings (``OLLAMA_HOST``/``OLLAMA_PORT`` and the ``WHISPER_*`` constants)
  are imported from :mod:`backend.config_head`, which is exactly where the
  monolith's ``from backend.config_head import *`` sourced them. Importing them
  here yields identical values.
- ``LLM_URL`` is intentionally redefined to ``OLLAMA_CHAT_URL`` (matching the
  monolith, which overrode the ``config``-provided ``LLM_URL`` at this point).
- This module never imports ``assistify_rag_server`` (avoids an import cycle).
"""
import os
from urllib.parse import urlsplit

from backend.config_head import (
    OLLAMA_HOST,
    OLLAMA_PORT,
    WHISPER_MODEL_SIZE,
    WHISPER_DEVICE,
    WHISPER_COMPUTE_TYPE,
    WHISPER_BEAM_SIZE,
)

# Define RAG hybrid semantic threshold (tune as needed)
RAG_HYBRID_SEMANTIC_THRESHOLD = 0.18

# Fact-query performance and correctness guards
FACT_MAX_TOP_K = 20
MAX_FACT_RETRIES = 2
FACT_MAX_RESCUE_QUERIES = 2
FACT_CONTEXT_MAX_SNIPPETS = 4
FACT_CONTEXT_MAX_CHARS = 1400


# Ensure ASSISTIFY feature flags have safe defaults when config isn't present
def _env_flag_enabled(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _build_ollama_url(path: str) -> str:
    host_raw = str(globals().get("OLLAMA_HOST", "127.0.0.1") or "").strip()
    port_raw = globals().get("OLLAMA_PORT", 11434)
    clean_path = "/" + str(path or "").strip().lstrip("/")

    if not host_raw:
        host_raw = "127.0.0.1"

    if host_raw.startswith(("http://", "https://")):
        base = host_raw.rstrip("/")
    else:
        host_no_slash = host_raw.rstrip("/")
        parsed = urlsplit(f"//{host_no_slash}")
        netloc = parsed.netloc or parsed.path
        if ":" not in netloc:
            netloc = f"{netloc}:{port_raw}"
        base = f"http://{netloc}"

    return f"{base.rstrip('/')}{clean_path}"


OLLAMA_CHAT_URL = _build_ollama_url("/api/chat")
OLLAMA_GENERATE_URL = _build_ollama_url("/api/generate")
OLLAMA_TAGS_URL = _build_ollama_url("/api/tags")
LLM_URL = OLLAMA_CHAT_URL
OLLAMA_API_URL = OLLAMA_CHAT_URL

ASSISTIFY_SAFE_MODE: bool = _env_flag_enabled('ASSISTIFY_SAFE_MODE', default=False)
ASSISTIFY_DISABLE_TTS: bool = _env_flag_enabled('ASSISTIFY_DISABLE_TTS', default=False)
ASSISTIFY_DISABLE_RERANKER: bool = _env_flag_enabled('ASSISTIFY_DISABLE_RERANKER', default=False)
ASSISTIFY_DISABLE_WHISPER: bool = _env_flag_enabled('ASSISTIFY_DISABLE_WHISPER', default=False)
ASSISTIFY_DISABLE_WARMUP: bool = _env_flag_enabled('ASSISTIFY_DISABLE_WARMUP', default=False)

# ---- TTS warmup sub-flags ----
# Arabic ack/off-topic/opener pre-renders and the batch opener warmup are
# expensive and routinely block real user TTS at startup (one tiny chunk
# observed at 61s while warmups were still running). Default ALL OFF so
# startup never synthesises anything before real user requests arrive.
ASSISTIFY_ENABLE_ENGLISH_TTS_WARMUP: bool = _env_flag_enabled('ASSISTIFY_ENABLE_ENGLISH_TTS_WARMUP', default=False)
ASSISTIFY_ENABLE_ARABIC_TTS_WARMUP: bool = _env_flag_enabled('ASSISTIFY_ENABLE_ARABIC_TTS_WARMUP', default=False)
ASSISTIFY_ENABLE_TTS_OPENER_WARMUP: bool = _env_flag_enabled('ASSISTIFY_ENABLE_TTS_OPENER_WARMUP', default=False)

# Effective flags used across module
EFFECTIVE_DISABLE_TTS = ASSISTIFY_DISABLE_TTS
EFFECTIVE_DISABLE_RERANKER = ASSISTIFY_DISABLE_RERANKER
EFFECTIVE_DISABLE_WHISPER = ASSISTIFY_DISABLE_WHISPER
EFFECTIVE_DISABLE_WARMUP = ASSISTIFY_DISABLE_WARMUP


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
