"""Per-request multi-tenancy context for the RAG backend.

Extracted verbatim from ``assistify_rag_server.py`` during the Phase 8B
refactor. This module owns the request-scoped tenant resolution that keeps
every business's retrieval, conversations and analytics isolated.

Behavior-preserving notes:
- ``DEFAULT_TENANT_ID`` is imported from :mod:`backend.config_head`, exactly
  where the monolith's ``from backend.config_head import *`` sourced it.
- ``log_usage``/``log_kb_event`` are tenant-aware wrappers that shadow the
  plain analytics functions. The monolith re-imports them (after its
  ``config_head`` wildcard import) so the shadow ordering is preserved.
- This module never imports ``assistify_rag_server`` (avoids an import cycle).
  ``get_tenant_rag`` (per-tenant Chroma manager cache) stays in the server and
  moves to the Chroma service in Phase 8G.
"""
import contextvars as _contextvars

from fastapi import HTTPException

from backend.config_head import DEFAULT_TENANT_ID
from backend.analytics import (
    log_usage as _analytics_log_usage,
    log_kb_event as _analytics_log_kb_event,
)


# Every request carries the tenant in the signed session cookie issued by the
# login server. For customers the login server overwrites `tenant_id` with the
# business they selected (`active_tenant_id`); staff/superadmin carry their home
# tenant. We resolve the effective tenant here so retrieval, conversations, and
# analytics can all be scoped to a single business and never cross over.
#
# The resolved tenant is stored in a ContextVar so the deep retrieval call chain
# can read it without threading the id through dozens of function signatures.
# Each tenant gets its own ChromaDB collection (see get_tenant_rag), so even
# under concurrent requests one business can never read another's vectors.
_request_tenant_id: "_contextvars.ContextVar[int]" = _contextvars.ContextVar(
    "request_tenant_id", default=DEFAULT_TENANT_ID
)
_current_user_query: "_contextvars.ContextVar[str]" = _contextvars.ContextVar(
    "current_user_query", default=""
)


def _user_has_explicit_tenant(user) -> bool:
    """True when the session carries an explicit tenant id (> 0)."""
    if not user:
        return False
    for key in ("active_tenant_id", "tenant_id"):
        val = user.get(key)
        if val is None:
            continue
        try:
            if int(val) > 0:
                return True
        except (TypeError, ValueError):
            continue
    return False


def resolve_request_tenant(user) -> int:
    """Resolve the effective tenant id for a request from the session cookie.

    Order of preference: the customer's actively selected business
    (`active_tenant_id`), then the user's home `tenant_id`, then the default
    tenant. Anonymous/legacy requests fall back to the default tenant so
    single-tenant installs keep working unchanged.
    """
    if not user:
        return DEFAULT_TENANT_ID
    for key in ("active_tenant_id", "tenant_id"):
        val = user.get(key)
        if val is None:
            continue
        try:
            tid = int(val)
        except (TypeError, ValueError):
            continue
        if tid > 0:
            return tid
    return DEFAULT_TENANT_ID


def require_request_tenant(user) -> int:
    """Like resolve_request_tenant but rejects callers with no explicit tenant
    so they can never silently fall back to another business's data."""
    role = str((user or {}).get("role") or "").lower()
    if not _user_has_explicit_tenant(user):
        if role == "customer":
            raise HTTPException(status_code=403, detail="No active business selected.")
        if role in ("admin", "master_admin", "employee"):
            raise HTTPException(status_code=403, detail="No business assigned to this account.")
        if role == "superadmin":
            raise HTTPException(status_code=403, detail="No target business selected. Switch to a tenant first.")
    return resolve_request_tenant(user)


class _TenantScope:
    """Context manager that binds the current request's tenant for the duration
    of a request, resetting it afterwards (safe for async/concurrent requests)."""

    __slots__ = ("tenant_id", "_token")

    def __init__(self, tenant_id):
        try:
            self.tenant_id = int(tenant_id)
        except (TypeError, ValueError):
            self.tenant_id = DEFAULT_TENANT_ID
        self._token = None

    def __enter__(self):
        self._token = _request_tenant_id.set(self.tenant_id)
        return self.tenant_id

    def __exit__(self, *exc):
        if self._token is not None:
            try:
                _request_tenant_id.reset(self._token)
            except Exception:
                pass
        return False


def current_tenant_id() -> int:
    """Return the tenant bound to the current request context (default tenant
    if none has been set)."""
    try:
        return int(_request_tenant_id.get())
    except Exception:
        return DEFAULT_TENANT_ID


# ---- Tenant-aware analytics wrappers ----
# These thin wrappers automatically attribute each event to the tenant bound to
# the current request, so analytics are isolated per business without having to
# thread tenant_id through the ~15 call sites in the chat pipeline.
def log_usage(*args, tenant_id=None, **kwargs):  # noqa: F811 (intentional shadow)
    if tenant_id is None:
        tenant_id = current_tenant_id()
    return _analytics_log_usage(*args, tenant_id=tenant_id, **kwargs)


def log_kb_event(*args, tenant_id=None, **kwargs):  # noqa: F811 (intentional shadow)
    if tenant_id is None:
        tenant_id = current_tenant_id()
    return _analytics_log_kb_event(*args, tenant_id=tenant_id, **kwargs)


def analytics_scope_tenant(user, requested_tenant_id=None):
    """Resolve which tenant an analytics/admin read should be scoped to.

    - superadmin: may target a specific tenant (via `requested_tenant_id`) or,
      when none is given, see platform-wide data (returns None => no filter).
    - business admin/employee: always restricted to their own tenant; any
      requested override is ignored so they can never read another business's
      analytics.
    """
    role = str((user or {}).get("role") or "").lower()
    if role == "superadmin":
        if requested_tenant_id is None:
            return None
        try:
            return int(requested_tenant_id)
        except (TypeError, ValueError):
            return None
    return resolve_request_tenant(user)
