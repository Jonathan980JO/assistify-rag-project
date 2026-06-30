"""Tenant membership helpers for customer ↔ business access workflow."""
from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any

try:
    from config import DEFAULT_TENANT_ID
except Exception:
    DEFAULT_TENANT_ID = 1

MEMBERSHIP_STATUSES = frozenset({"pending", "approved", "rejected", "revoked"})


def ensure_membership_schema(cursor: sqlite3.Cursor) -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS tenant_memberships (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            tenant_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            reviewed_at TIMESTAMP,
            reviewed_by TEXT,
            notes TEXT,
            UNIQUE(username, tenant_id),
            FOREIGN KEY (tenant_id) REFERENCES tenants(id)
        )
        """
    )
    cursor.execute("PRAGMA table_info(tenants)")
    tenant_cols = {row[1] for row in cursor.fetchall()}
    if "allow_multiple_admins" not in tenant_cols:
        cursor.execute(
            "ALTER TABLE tenants ADD COLUMN allow_multiple_admins INTEGER DEFAULT 0"
        )


def list_memberships_for_user(
    conn: sqlite3.Connection,
    username: str,
    *,
    status: str | None = None,
) -> list[dict[str, Any]]:
    cursor = conn.cursor()
    sql = """
        SELECT m.id, m.username, m.tenant_id, m.status, m.requested_at,
               m.reviewed_at, m.reviewed_by, m.notes, t.name, t.slug, t.active
        FROM tenant_memberships m
        JOIN tenants t ON t.id = m.tenant_id
        WHERE m.username = ?
    """
    params: list[Any] = [username]
    if status:
        sql += " AND m.status = ?"
        params.append(status)
    sql += " ORDER BY m.requested_at DESC"
    cursor.execute(sql, params)
    rows = cursor.fetchall()
    return [_membership_row(row) for row in rows]


def list_memberships_for_tenant(
    conn: sqlite3.Connection,
    tenant_id: int,
    *,
    status: str | None = None,
) -> list[dict[str, Any]]:
    cursor = conn.cursor()
    sql = """
        SELECT m.id, m.username, m.tenant_id, m.status, m.requested_at,
               m.reviewed_at, m.reviewed_by, m.notes, t.name, t.slug, t.active
        FROM tenant_memberships m
        JOIN tenants t ON t.id = m.tenant_id
        WHERE m.tenant_id = ?
    """
    params: list[Any] = [int(tenant_id)]
    if status:
        sql += " AND m.status = ?"
        params.append(status)
    sql += " ORDER BY m.requested_at DESC"
    cursor.execute(sql, params)
    return [_membership_row(row) for row in cursor.fetchall()]


def get_membership(
    conn: sqlite3.Connection,
    username: str,
    tenant_id: int,
) -> dict[str, Any] | None:
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT m.id, m.username, m.tenant_id, m.status, m.requested_at,
               m.reviewed_at, m.reviewed_by, m.notes, t.name, t.slug, t.active
        FROM tenant_memberships m
        JOIN tenants t ON t.id = m.tenant_id
        WHERE m.username = ? AND m.tenant_id = ?
        """,
        (username, int(tenant_id)),
    )
    row = cursor.fetchone()
    return _membership_row(row) if row else None


def get_membership_by_id(conn: sqlite3.Connection, membership_id: int) -> dict[str, Any] | None:
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT m.id, m.username, m.tenant_id, m.status, m.requested_at,
               m.reviewed_at, m.reviewed_by, m.notes, t.name, t.slug, t.active
        FROM tenant_memberships m
        JOIN tenants t ON t.id = m.tenant_id
        WHERE m.id = ?
        """,
        (int(membership_id),),
    )
    row = cursor.fetchone()
    return _membership_row(row) if row else None


def create_access_request(conn: sqlite3.Connection, username: str, tenant_id: int) -> dict[str, Any]:
    cursor = conn.cursor()
    cursor.execute("SELECT id, active FROM tenants WHERE id=?", (int(tenant_id),))
    tenant = cursor.fetchone()
    if not tenant:
        raise ValueError("tenant_not_found")
    if not tenant[1]:
        raise ValueError("tenant_inactive")
    existing = get_membership(conn, username, tenant_id)
    if existing:
        if existing["status"] in {"pending", "approved"}:
            raise ValueError("already_requested")
        if existing["status"] == "rejected":
            cursor.execute(
                """
                UPDATE tenant_memberships
                SET status='pending', requested_at=CURRENT_TIMESTAMP,
                    reviewed_at=NULL, reviewed_by=NULL, notes=NULL
                WHERE id=?
                """,
                (existing["id"],),
            )
            conn.commit()
            return get_membership_by_id(conn, existing["id"]) or existing
        if existing["status"] == "revoked":
            cursor.execute(
                """
                UPDATE tenant_memberships
                SET status='pending', requested_at=CURRENT_TIMESTAMP,
                    reviewed_at=NULL, reviewed_by=NULL, notes=NULL
                WHERE id=?
                """,
                (existing["id"],),
            )
            conn.commit()
            return get_membership_by_id(conn, existing["id"]) or existing
    cursor.execute(
        """
        INSERT INTO tenant_memberships (username, tenant_id, status)
        VALUES (?, ?, 'pending')
        """,
        (username, int(tenant_id)),
    )
    conn.commit()
    return get_membership_by_id(conn, cursor.lastrowid) or {}


def update_membership_status(
    conn: sqlite3.Connection,
    membership_id: int,
    status: str,
    reviewed_by: str,
    notes: str | None = None,
) -> dict[str, Any] | None:
    if status not in MEMBERSHIP_STATUSES:
        raise ValueError("invalid_status")
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE tenant_memberships
        SET status=?, reviewed_at=?, reviewed_by=?, notes=COALESCE(?, notes)
        WHERE id=?
        """,
        (status, datetime.utcnow().isoformat(), reviewed_by, notes, int(membership_id)),
    )
    conn.commit()
    return get_membership_by_id(conn, membership_id)


def approved_memberships(conn: sqlite3.Connection, username: str) -> list[dict[str, Any]]:
    return [
        m for m in list_memberships_for_user(conn, username, status="approved")
        if m.get("tenant_active", True)
    ]


def resolve_active_tenant_id(
    conn: sqlite3.Connection,
    *,
    role: str,
    username: str,
    user_tenant_id: int | None,
    session_active_tenant_id: int | None = None,
    requested_tenant_id: int | None = None,
) -> int | None:
    role = str(role or "").lower()
    if role == "superadmin":
        if requested_tenant_id and int(requested_tenant_id) > 0:
            return int(requested_tenant_id)
        return int(user_tenant_id or DEFAULT_TENANT_ID)
    if role in {"admin", "employee"}:
        return int(user_tenant_id or DEFAULT_TENANT_ID)
    if role != "customer":
        return int(user_tenant_id or DEFAULT_TENANT_ID)
    approved = approved_memberships(conn, username)
    if not approved:
        return None
    if requested_tenant_id:
        rid = int(requested_tenant_id)
        if any(m["tenant_id"] == rid for m in approved):
            return rid
    if session_active_tenant_id:
        sid = int(session_active_tenant_id)
        if any(m["tenant_id"] == sid for m in approved):
            return sid
    if len(approved) == 1:
        return int(approved[0]["tenant_id"])
    return None


def customer_has_approved_access(conn: sqlite3.Connection, username: str) -> bool:
    return bool(approved_memberships(conn, username))


def backfill_default_tenant_memberships(conn: sqlite3.Connection, tenant_id: int = DEFAULT_TENANT_ID) -> int:
    """Grant approved membership to legacy customers on the default tenant."""
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT username FROM users
        WHERE role='customer' AND (tenant_id IS NULL OR tenant_id=?)
        """,
        (int(tenant_id),),
    )
    count = 0
    for (username,) in cursor.fetchall():
        if get_membership(conn, username, tenant_id):
            continue
        cursor.execute(
            """
            INSERT INTO tenant_memberships (username, tenant_id, status, reviewed_by, reviewed_at)
            VALUES (?, ?, 'approved', 'migration', CURRENT_TIMESTAMP)
            """,
            (username, int(tenant_id)),
        )
        count += 1
    conn.commit()
    return count


def _membership_row(row) -> dict[str, Any]:
    return {
        "id": row[0],
        "username": row[1],
        "tenant_id": row[2],
        "status": row[3],
        "requested_at": row[4],
        "reviewed_at": row[5],
        "reviewed_by": row[6],
        "notes": row[7],
        "tenant_name": row[8],
        "tenant_slug": row[9],
        "tenant_active": bool(row[10]) if row[10] is not None else True,
    }
