"""Single source of truth for the bootstrap superadmin account."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Sequence


@dataclass(frozen=True)
class DevUser:
    username: str
    password: str
    role: str
    tenant_id: int | None = 1


# Fresh installs seed only the platform owner. All other roles are created via UI/APIs.
DEV_USER_ACCOUNTS: Sequence[DevUser] = (
    DevUser("superadmin", "superadmin", "superadmin", None),
)

# Demo accounts removed from seeding; delete if still present from older installs.
LEGACY_DEMO_USERNAMES: Sequence[str] = (
    "master_admin",
    "admin",
    "employee",
    "customer",
)


def dev_user_summary() -> str:
    return ", ".join(f"{u.username}/{u.password}" for u in DEV_USER_ACCOUNTS)


def remove_legacy_demo_users(cursor) -> list[str]:
    """Delete auto-seeded demo accounts from older installs."""
    try:
        from Login_system.tenant_lifecycle import purge_user_dependencies
    except ImportError:
        from tenant_lifecycle import purge_user_dependencies

    removed: list[str] = []
    for username in LEGACY_DEMO_USERNAMES:
        cursor.execute(
            "SELECT id FROM users WHERE username=?",
            (username,),
        )
        row = cursor.fetchone()
        if not row:
            continue
        user_id = int(row[0])
        purge_user_dependencies(cursor, user_id, username)
        cursor.execute("DELETE FROM users WHERE id=?", (user_id,))
        removed.append(username)
    return removed


def seed_dev_users(cursor, pwd_context, tenant_id: int = 1) -> None:
    """Upsert bootstrap superadmin with bcrypt hash."""
    remove_legacy_demo_users(cursor)
    now = datetime.utcnow().isoformat()
    upsert_sql = """
        INSERT INTO users (username, password_hash, role, active, tenant_id, created_at)
        VALUES (?, ?, ?, 1, ?, ?)
        ON CONFLICT(username) DO UPDATE SET
            password_hash = excluded.password_hash,
            role = excluded.role,
            active = excluded.active,
            tenant_id = excluded.tenant_id,
            created_at = excluded.created_at
    """
    for user in DEV_USER_ACCOUNTS:
        tid = user.tenant_id if user.tenant_id is not None else None
        cursor.execute(
            upsert_sql,
            (user.username, pwd_context.hash(user.password), user.role, tid, now),
        )
