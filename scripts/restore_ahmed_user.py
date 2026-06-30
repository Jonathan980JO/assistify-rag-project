#!/usr/bin/env python3
"""Restore a wiped user from Login_system/users_backup.db into users.db."""
from __future__ import annotations

import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
USERS_DB = REPO / "Login_system" / "users.db"
BACKUP_DB = REPO / "Login_system" / "users_backup.db"

# Backup row: id=32, registered as email username; chats/analytics use ahmed_khaled1.
SOURCE_USERNAME = "ahmed_khaled1907@gmail.com"
RESTORE_USERNAME = "ahmed_khaled1"
RESTORE_EMAIL = "ahmed_khaled1907@gmail.com"
RESTORE_ROLE = "master_admin"  # analytics.db shows this role in recent sessions


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def main() -> int:
    if not BACKUP_DB.exists():
        print(f"[ERROR] Missing backup: {BACKUP_DB}")
        return 1
    if not USERS_DB.exists():
        print(f"[ERROR] Missing live DB: {USERS_DB}")
        return 1

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    snapshot = USERS_DB.with_name(f"users.db.before_restore_{stamp}")
    shutil.copy2(USERS_DB, snapshot)
    print(f"[RESTORE] Snapshot: {snapshot}")

    src = sqlite3.connect(BACKUP_DB)
    src.row_factory = sqlite3.Row
    row = src.execute(
        "SELECT * FROM users WHERE username = ?", (SOURCE_USERNAME,)
    ).fetchone()
    if row is None:
        print(f"[ERROR] User {SOURCE_USERNAME!r} not found in backup")
        return 1

    dst = sqlite3.connect(USERS_DB)
    dst.row_factory = sqlite3.Row
    cur = dst.cursor()

    # Merge tenants from backup (keep existing Default tenant id=1).
    for tenant in src.execute("SELECT * FROM tenants"):
        t = dict(tenant)
        exists = cur.execute("SELECT id FROM tenants WHERE id = ?", (t["id"],)).fetchone()
        if exists:
            continue
        cols = [k for k in t.keys() if k != "id"]
        placeholders = ",".join("?" for _ in cols)
        cur.execute(
            f"INSERT INTO tenants (id, {', '.join(cols)}) VALUES (?, {placeholders})",
            (t["id"], *[t[c] for c in cols]),
        )
        print(f"[RESTORE] Tenant added: {t['id']} {t['name']}")

    existing = cur.execute(
        "SELECT id, username FROM users WHERE username IN (?, ?) OR email = ?",
        (RESTORE_USERNAME, RESTORE_EMAIL, RESTORE_EMAIL),
    ).fetchall()
    if existing:
        print(f"[RESTORE] Removing stale rows before insert: {[dict(r) for r in existing]}")
        for r in existing:
            cur.execute("DELETE FROM users WHERE id = ?", (r["id"],))

    cur.execute(
        """
        INSERT INTO users (
            username, password_hash, role, mfa_enabled, mfa_secret, active,
            google_id, email, profile_picture, auth_provider, email_verified,
            full_name, tenant_id, created_at, username_changed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            RESTORE_USERNAME,
            row["password_hash"],
            RESTORE_ROLE,
            row["mfa_enabled"],
            row["mfa_secret"],
            1,
            row["google_id"],
            RESTORE_EMAIL,
            row["profile_picture"],
            row["auth_provider"] or "local",
            row["email_verified"],
            row["full_name"] or "Ahmed Khaled",
            row["tenant_id"] or 1,
            row["created_at"] or _utc_now(),
            _utc_now(),
        ),
    )
    new_id = cur.lastrowid
    print(f"[RESTORE] User inserted id={new_id} username={RESTORE_USERNAME!r} role={RESTORE_ROLE}")

    # Clear lockouts / failed attempts for both identifiers.
    for table in ("failed_login_attempts", "account_lockouts", "rate_limit_buckets"):
        try:
            cur.execute(f"DELETE FROM {table} WHERE username IN (?, ?)", (RESTORE_USERNAME, RESTORE_EMAIL))
        except sqlite3.OperationalError:
            pass

    dst.commit()
    src.close()
    dst.close()

    print("[RESTORE] Done.")
    print(f"  Login with username: {RESTORE_USERNAME}")
    print(f"  Or email:            {RESTORE_EMAIL}")
    print("  Password: your original password from registration (hash restored from backup).")
    print("  Chat history in backend/conversations.db is still tied to ahmed_khaled1.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
