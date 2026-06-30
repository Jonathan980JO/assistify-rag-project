"""Chat tenant validation — active-tenant checks and optional membership enforcement."""
from __future__ import annotations

import logging
import sqlite3
import time
from pathlib import Path

from fastapi import HTTPException

try:
    from config import DEFAULT_TENANT_ID, ENFORCE_CHAT_TENANT_MEMBERSHIP, ROOT
except Exception:
    ROOT = Path(__file__).resolve().parent.parent
    DEFAULT_TENANT_ID = 1
    ENFORCE_CHAT_TENANT_MEMBERSHIP = False

USERS_DB_PATH = Path(ROOT) / "Login_system" / "users.db"
logger = logging.getLogger("TenantAccess")

_tenant_cache: dict[int, dict] = {}
_tenant_cache_ts: float = 0.0
_CACHE_TTL_SEC = 60.0


def _users_db_path() -> str:
    return str(USERS_DB_PATH)


def invalidate_tenant_cache() -> None:
    """Force reload of tenant list from users.db on next access."""
    global _tenant_cache_ts
    _tenant_cache_ts = 0.0


def _refresh_tenant_cache() -> None:
    global _tenant_cache, _tenant_cache_ts
    if not USERS_DB_PATH.exists():
        _tenant_cache = {DEFAULT_TENANT_ID: {"id": DEFAULT_TENANT_ID, "name": "Default", "slug": "default", "active": 1}}
        _tenant_cache_ts = time.time()
        return
    conn = sqlite3.connect(_users_db_path())
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, name, slug, active FROM tenants")
        rows = cursor.fetchall()
    except sqlite3.Error:
        rows = []
    conn.close()
    _tenant_cache = {
        int(r[0]): {"id": int(r[0]), "name": r[1], "slug": r[2], "active": int(r[3] or 0)}
        for r in rows
    }
    _tenant_cache_ts = time.time()


def _tenant_map() -> dict[int, dict]:
    global _tenant_cache_ts
    if time.time() - _tenant_cache_ts > _CACHE_TTL_SEC or not _tenant_cache:
        _refresh_tenant_cache()
    return _tenant_cache


def list_active_chat_tenants() -> list[dict]:
    tenants = [
        {"id": t["id"], "name": t["name"], "slug": t.get("slug")}
        for t in _tenant_map().values()
        if int(t.get("active") or 0) == 1
    ]
    tenants.sort(key=lambda x: str(x.get("name") or "").lower())
    return tenants


def get_tenant_name(tenant_id: int) -> str:
    t = _tenant_map().get(int(tenant_id))
    if not t:
        return f"Tenant #{tenant_id}"
    return str(t.get("name") or f"Tenant #{tenant_id}")


def _user_role(user) -> str:
    if not user or not isinstance(user, dict):
        return ""
    return str(user.get("role") or "").strip().lower()


def _is_guest_user(user) -> bool:
    return _user_role(user) == "guest"


def _staff_tenant_id(user) -> int | None:
    if not user or not isinstance(user, dict):
        return None
    role = _user_role(user)
    if role in {"admin", "master_admin", "employee", "superadmin"}:
        try:
            tid = int(user.get("tenant_id") or user.get("active_tenant_id") or 0)
            return tid if tid > 0 else None
        except (TypeError, ValueError):
            return None
    return None


def _customer_has_membership(username: str, tenant_id: int) -> bool:
    if not username or not USERS_DB_PATH.exists():
        return False
    conn = sqlite3.connect(_users_db_path())
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT 1 FROM tenant_memberships
            WHERE username = ? AND tenant_id = ? AND status = 'approved'
            LIMIT 1
            """,
            (str(username), int(tenant_id)),
        )
        return cursor.fetchone() is not None
    except sqlite3.Error:
        return False
    finally:
        conn.close()


def _assert_tenant_membership(user, tenant_id: int) -> None:
    """Enforce tenant access when ENFORCE_CHAT_TENANT_MEMBERSHIP is enabled."""
    if not ENFORCE_CHAT_TENANT_MEMBERSHIP:
        return
    if not user or not isinstance(user, dict):
        return
    role = _user_role(user)
    if role in {"superadmin"}:
        return
    if role in {"admin", "master_admin", "employee"}:
        staff_tid = _staff_tenant_id(user)
        if staff_tid is not None and int(staff_tid) != int(tenant_id):
            raise HTTPException(status_code=403, detail="Tenant not authorized for this account")
        return
    if role == "customer":
        username = str(user.get("username") or "")
        if not _customer_has_membership(username, tenant_id):
            raise HTTPException(status_code=403, detail="Tenant membership required")
        return
    if _is_guest_user(user):
        return


def assert_chat_tenant_allowed(user, tenant_id) -> int:
    """Verify tenant exists, is active, and (when configured) user may access it."""
    try:
        tid = int(tenant_id)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid tenant_id") from None
    if tid <= 0:
        raise HTTPException(status_code=400, detail="Invalid tenant_id")
    tenant = _tenant_map().get(tid)
    if not tenant:
        raise HTTPException(status_code=403, detail="Tenant not found")
    if int(tenant.get("active") or 0) != 1:
        raise HTTPException(status_code=403, detail="Tenant is not active")
    _assert_tenant_membership(user, tid)
    return tid


def resolve_active_chat_tenant(
    request_tenant_id,
    conversation_id: str | None,
    owner: str | None,
    get_active_fn,
    user=None,
) -> int:
    """Resolve active tenant for a chat turn: request > conversation state > error."""
    if request_tenant_id is not None:
        return assert_chat_tenant_allowed(user, request_tenant_id)
    if conversation_id:
        active = get_active_fn(conversation_id, owner)
        if active is not None:
            return assert_chat_tenant_allowed(user, active)
    raise HTTPException(
        status_code=400,
        detail="tenant_id required (or set active tenant on conversation)",
    )
