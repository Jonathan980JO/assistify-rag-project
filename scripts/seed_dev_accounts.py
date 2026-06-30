#!/usr/bin/env python3
"""Non-destructive upsert of bootstrap superadmin into existing users.db.

Ensures superadmin exists, removes legacy demo accounts from older installs,
and clears stray test rows from persistent security state tables.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from config import BCRYPT_ROUNDS, DEFAULT_TENANT_ID  # noqa: E402
from passlib.context import CryptContext  # noqa: E402

try:
    from Login_system.dev_users import (
        DEV_USER_ACCOUNTS,
        LEGACY_DEMO_USERNAMES,
        dev_user_summary,
        remove_legacy_demo_users,
        seed_dev_users,
    )
    from Login_system.persistent_state import ensure_persistent_state_schema
except ImportError:
    from dev_users import (  # type: ignore
        DEV_USER_ACCOUNTS,
        LEGACY_DEMO_USERNAMES,
        dev_user_summary,
        remove_legacy_demo_users,
        seed_dev_users,
    )
    from persistent_state import ensure_persistent_state_schema  # type: ignore

DB_PATH = REPO_ROOT / "Login_system" / "users.db"

DEV_USERNAMES = tuple(u.username for u in DEV_USER_ACCOUNTS)
CLEANUP_FAILED_USERNAMES = ("user1", *DEV_USERNAMES, *LEGACY_DEMO_USERNAMES)
CLEANUP_INVALIDATED_SESSIONS = ("sess-a",)


def _pwd_context() -> CryptContext:
    return CryptContext(
        schemes=["bcrypt_sha256", "pbkdf2_sha256"],
        default="bcrypt_sha256",
        deprecated=["pbkdf2_sha256"],
        bcrypt_sha256__rounds=BCRYPT_ROUNDS,
    )


def _cleanup_security_artifacts(conn: sqlite3.Connection) -> None:
    c = conn.cursor()
    for table in (
        "invalidated_sessions",
        "failed_login_attempts",
        "account_lockouts",
        "rate_limit_buckets",
    ):
        try:
            c.execute(f"SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,))
            if not c.fetchone():
                continue
        except sqlite3.Error:
            continue

    placeholders = ",".join("?" * len(CLEANUP_INVALIDATED_SESSIONS))
    try:
        c.execute(
            f"DELETE FROM invalidated_sessions WHERE session_id IN ({placeholders})",
            CLEANUP_INVALIDATED_SESSIONS,
        )
    except sqlite3.Error:
        pass

    placeholders = ",".join("?" * len(CLEANUP_FAILED_USERNAMES))
    try:
        c.execute(
            f"DELETE FROM failed_login_attempts WHERE username IN ({placeholders})",
            CLEANUP_FAILED_USERNAMES,
        )
    except sqlite3.Error:
        pass

    try:
        c.execute("DELETE FROM rate_limit_buckets WHERE identifier = ?", ("login:127.0.0.1",))
    except sqlite3.Error:
        pass


def main() -> int:
    if not DB_PATH.exists():
        print(f"ERROR: {DB_PATH} not found. Run Login_system/init_users_db.py first for a fresh DB.")
        return 1

    pwd_context = _pwd_context()
    conn = sqlite3.connect(str(DB_PATH))
    try:
        c = conn.cursor()
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
        if not c.fetchone():
            print("ERROR: users table missing in users.db")
            return 1

        before = {
            row[0]
            for row in c.execute(
                "SELECT username FROM users WHERE username IN ({})".format(
                    ",".join("?" * len(DEV_USERNAMES))
                ),
                DEV_USERNAMES,
            ).fetchall()
        }

        removed = remove_legacy_demo_users(c)
        seed_dev_users(c, pwd_context, tenant_id=DEFAULT_TENANT_ID)
        ensure_persistent_state_schema()
        _cleanup_security_artifacts(conn)
        conn.commit()

        after = {
            row[0]
            for row in c.execute(
                "SELECT username FROM users WHERE username IN ({})".format(
                    ",".join("?" * len(DEV_USERNAMES))
                ),
                DEV_USERNAMES,
            ).fetchall()
        }
        created = sorted(after - before)
        refreshed = sorted(before & after)

        print(f"Database: {DB_PATH}")
        print(f"Bootstrap account: {dev_user_summary()}")
        if removed:
            print(f"Removed legacy demo accounts: {', '.join(removed)}")
        if created:
            print(f"Created: {', '.join(created)}")
        if refreshed:
            print(f"Refreshed password hashes: {', '.join(refreshed)}")
        print("Cleaned stray security-state rows (sess-a, user1, dev failed-login counts, login rate bucket).")
        print("Done.")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
