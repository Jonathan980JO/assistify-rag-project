"""Permanent tenant deletion and related user dependency cleanup."""
from __future__ import annotations

import logging
import sqlite3
from typing import Any

try:
    from config import DEFAULT_TENANT_ID
except Exception:
    DEFAULT_TENANT_ID = 1

logger = logging.getLogger("TenantLifecycle")

_STAFF_ROLES = ("master_admin", "admin", "employee")


def purge_user_dependencies(cursor, user_id: int, username: str | None = None) -> None:
    """Remove rows that block deleting a user (support data, memberships)."""
    uid = int(user_id)
    uname = (username or "").strip()
    cursor.execute("SELECT id FROM support_tickets WHERE customer_id=?", (uid,))
    ticket_ids = [row[0] for row in cursor.fetchall()]
    if ticket_ids:
        placeholders = ",".join("?" * len(ticket_ids))
        cursor.execute(
            f"DELETE FROM ticket_messages WHERE ticket_id IN ({placeholders})",
            ticket_ids,
        )
        cursor.execute(
            f"DELETE FROM notifications WHERE related_ticket_id IN ({placeholders})",
            ticket_ids,
        )
        cursor.execute(
            f"DELETE FROM support_tickets WHERE id IN ({placeholders})",
            ticket_ids,
        )
    cursor.execute("DELETE FROM customer_notes WHERE customer_id=?", (uid,))
    if uname:
        cursor.execute("DELETE FROM tenant_memberships WHERE username=?", (uname,))
        cursor.execute("DELETE FROM notifications WHERE user_username=?", (uname,))


def _purge_tenant_tickets(cursor, tenant_id: int) -> int:
    cursor.execute("SELECT id FROM support_tickets WHERE tenant_id=?", (int(tenant_id),))
    ticket_ids = [row[0] for row in cursor.fetchall()]
    if not ticket_ids:
        return 0
    placeholders = ",".join("?" * len(ticket_ids))
    cursor.execute(
        f"DELETE FROM ticket_messages WHERE ticket_id IN ({placeholders})",
        ticket_ids,
    )
    cursor.execute(
        f"DELETE FROM notifications WHERE related_ticket_id IN ({placeholders})",
        ticket_ids,
    )
    cursor.execute(
        f"DELETE FROM support_tickets WHERE id IN ({placeholders})",
        ticket_ids,
    )
    return len(ticket_ids)


def purge_tenant_users_db(conn: sqlite3.Connection, tenant_id: int) -> dict[str, int]:
    """Delete tenant-scoped rows from users.db. Caller must commit."""
    tid = int(tenant_id)
    cursor = conn.cursor()
    tickets_deleted = _purge_tenant_tickets(cursor, tid)

    placeholders = ",".join("?" * len(_STAFF_ROLES))
    cursor.execute(
        f"""
        SELECT id, username FROM users
        WHERE tenant_id = ? AND role IN ({placeholders})
        """,
        (tid, *_STAFF_ROLES),
    )
    staff_rows = cursor.fetchall()
    users_deleted = 0
    for user_id, username in staff_rows:
        purge_user_dependencies(cursor, int(user_id), username)
        cursor.execute("DELETE FROM users WHERE id=?", (int(user_id),))
        users_deleted += 1

    cursor.execute("DELETE FROM tenant_memberships WHERE tenant_id=?", (tid,))
    memberships_deleted = cursor.rowcount if cursor.rowcount >= 0 else 0

    cursor.execute("DELETE FROM tenants WHERE id=?", (tid,))
    if cursor.rowcount == 0:
        raise ValueError("tenant_not_found")

    return {
        "tickets_deleted": tickets_deleted,
        "users_deleted": users_deleted,
        "memberships_deleted": memberships_deleted,
    }


def _best_effort_secondary_cleanup(tenant_id: int) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    try:
        from backend.knowledge_base import purge_tenant_knowledge

        summary["knowledge"] = purge_tenant_knowledge(tenant_id)
    except Exception as exc:
        logger.warning("purge_tenant_knowledge failed for tenant %s: %s", tenant_id, exc)
        summary["knowledge"] = {"error": str(exc)}

    try:
        from backend.chat_store import purge_tenant_chat_data

        summary["chat"] = purge_tenant_chat_data(tenant_id)
    except Exception as exc:
        logger.warning("purge_tenant_chat_data failed for tenant %s: %s", tenant_id, exc)
        summary["chat"] = {"error": str(exc)}

    try:
        from backend.analytics import purge_tenant_analytics

        summary["analytics"] = purge_tenant_analytics(tenant_id)
    except Exception as exc:
        logger.warning("purge_tenant_analytics failed for tenant %s: %s", tenant_id, exc)
        summary["analytics"] = {"error": str(exc)}

    try:
        from backend.tenant_access import invalidate_tenant_cache

        invalidate_tenant_cache()
    except Exception as exc:
        logger.warning("invalidate_tenant_cache failed: %s", exc)

    return summary


def delete_tenant_permanently(
    conn: sqlite3.Connection,
    tenant_id: int,
    *,
    performed_by: str = "superadmin",
    ip_address: str | None = None,
) -> dict[str, Any]:
    """Remove a tenant and all scoped data. DB purge is transactional; secondary stores are best-effort."""
    tid = int(tenant_id)
    if tid == int(DEFAULT_TENANT_ID):
        raise PermissionError("cannot_delete_default_tenant")

    cursor = conn.cursor()
    cursor.execute("SELECT id, name, slug, active FROM tenants WHERE id=?", (tid,))
    row = cursor.fetchone()
    if not row:
        raise ValueError("tenant_not_found")
    if int(row[3] or 0) == 1:
        raise RuntimeError("tenant_still_active")

    tenant_name = str(row[1] or "")
    tenant_slug = str(row[2] or "")

    try:
        db_summary = purge_tenant_users_db(conn, tid)
        cursor.execute(
            """
            INSERT INTO audit_logs (user_id, username, action, old_value, new_value, ip_address, performed_by)
            VALUES (NULL, ?, 'SUPERADMIN_TENANT_DELETE', ?, 'deleted', ?, ?)
            """,
            (
                tenant_slug or tenant_name,
                f"{tenant_name} ({tenant_slug})",
                ip_address,
                performed_by,
            ),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    secondary = _best_effort_secondary_cleanup(tid)
    return {
        "status": "deleted",
        "tenant_id": tid,
        "slug": tenant_slug,
        **db_summary,
        "secondary_cleanup": secondary,
    }
