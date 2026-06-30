#!/usr/bin/env python3
"""Reset bootstrap superadmin password without touching custom users."""
from __future__ import annotations

import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Login_system.dev_users import DEV_USER_ACCOUNTS, seed_dev_users
from Login_system.login_server import auth_user, init_db, pwd_context
from Login_system.repositories.db import DB_PATH, get_db

PROTECTED_PREFIXES = ("ahmed",)
PROTECTED_EXACT = {
    "ahmed_khaled1",
    "ahmed_khaled",
    "ahmedkhalid",
    "ahmed_khaled1907@gmail.com",
}


def _is_protected(username: str | None, email: str | None = None) -> bool:
    for value in (username, email):
        if not value:
            continue
        low = str(value).strip().lower()
        if low in PROTECTED_EXACT:
            return True
        if any(low.startswith(p) for p in PROTECTED_PREFIXES):
            return True
    return False


def list_custom_users(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT username, role, email, active, tenant_id, auth_provider,
               CASE WHEN password_hash IS NULL OR TRIM(password_hash) = '' THEN 1 ELSE 0 END AS empty_hash
        FROM users
        ORDER BY username
        """
    ).fetchall()
    dev_names = {u.username.lower() for u in DEV_USER_ACCOUNTS}
    custom = []
    for row in rows:
        if row["username"].lower() in dev_names:
            continue
        custom.append(row)
    return custom


def main() -> int:
    db_path = Path(DB_PATH)
    if not db_path.exists():
        init_db()
        print(f"Created {db_path}")

    conn = get_db()
    cur = conn.cursor()

    before = list_custom_users(conn)
    protected = [r for r in before if _is_protected(r["username"], r["email"])]
    other_custom = [r for r in before if not _is_protected(r["username"], r["email"])]

    seed_dev_users(cur, pwd_context, tenant_id=1)
    conn.commit()

    print("Reset bootstrap credentials:")
    for user in DEV_USER_ACCOUNTS:
        ok_name, ok_role = auth_user(user.username, user.password)
        status = "OK" if ok_name and ok_role == user.role else "FAIL"
        print(f"  - {user.username} / {user.password} ({user.role}) [{status}]")

    after_custom = list_custom_users(conn)
    conn.close()

    print("\nProtected custom users (unchanged):")
    if not protected:
        print("  (none matching ahmed*)")
    for row in protected:
        print(
            f"  - username={row['username']!r} role={row['role']!r} "
            f"email={row['email']!r} active={row['active']}"
        )
        print("    password: unchanged (stored as bcrypt hash; plaintext not recoverable from DB)")

    if other_custom:
        print("\nOther non-dev users found:")
        for row in other_custom:
            print(
                f"  - username={row['username']!r} role={row['role']!r} "
                f"email={row['email']!r} active={row['active']}"
            )
            if row["empty_hash"]:
                print("    password: empty hash (dev fallback may accept username as password if enabled)")
            else:
                print("    password: unchanged (bcrypt hash only; ask owner or use password reset)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
