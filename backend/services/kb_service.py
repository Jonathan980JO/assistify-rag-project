"""Knowledge-base service helpers for the RAG backend.

Extracted verbatim from ``assistify_rag_server.py`` during the Phase 8D
refactor. Holds the self-contained, thread-safe in-memory rate limiter and the
KB-admin tenant scoping helper. The websocket-coupled KB event broadcast and
pipeline-state machine stay in the server module (they move with the websocket
integration in a later phase).

This module never imports ``assistify_rag_server`` (avoids an import cycle).
"""
import time
import threading as _threading
from collections import defaultdict as _defaultdict

from backend.config_head import DEFAULT_TENANT_ID
from backend.core.tenant_context import require_request_tenant, _request_tenant_id


# ========== IN-MEMORY RATE LIMITER ==========
_rate_buckets: dict = _defaultdict(lambda: {"count": 0, "reset": 0.0})
_rate_lock = _threading.Lock()


def _check_rate_limit(key: str, limit: int, window: int = 60) -> bool:
    """Return True if allowed, False if rate-limited. Thread-safe, in-memory."""
    now = time.time()
    with _rate_lock:
        bucket = _rate_buckets[key]
        if now > bucket["reset"]:
            bucket["count"] = 1
            bucket["reset"] = now + window
            return True
        if bucket["count"] >= limit:
            return False
        bucket["count"] += 1
        return True


def _kb_admin_scope_tenant(user) -> int | None:
    """Tenant id to scope a KB-admin read/write to, or None for the default
    tenant (which keeps the historical, un-namespaced collection behavior)."""
    tid = require_request_tenant(user)
    _request_tenant_id.set(tid)
    try:
        return None if int(tid) == int(DEFAULT_TENANT_ID) else int(tid)
    except (TypeError, ValueError):
        return None
