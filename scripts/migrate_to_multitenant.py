"""Upgrade an existing single-tenant Assistify install to multi-tenant.

This script is **standalone**, **idempotent**, and **Windows-friendly**. It is
safe to run more than once: every step checks whether a table / column / file /
index already exists before acting, so re-running it is a no-op for anything
that is already migrated.

What it does (each step is isolated in try/except so one failure does not abort
the rest of the migration):

  1. Resolve DB/asset paths from ``config`` (falls back to sensible defaults
     under the repo root if ``config`` cannot be imported).
  2. Back up each existing DB file to ``<file>.pre_mt_backup`` before touching it.
  3. ``users.db``: ensure the ``tenants`` table + default tenant exist, ensure
     ``users.tenant_id`` exists (backfilling NULLs), and ensure a ``superadmin``
     user exists.
  4. Conversations DB: add ``tenant_id`` to ``conversations`` / ``sessions`` and
     create the tenant-scoped indexes.
  5. Analytics DB: add ``tenant_id`` to the analytics tables.
  6. Assets: move top-level files under the assets dir into
     ``assets/tenant_<DEFAULT_TENANT_ID>/``.
  7. Chroma: print a note (no vector-store migration is required).

Usage (from the repo root)::

    python scripts/migrate_to_multitenant.py

Only the standard library is required (sqlite3, os, shutil, sys, pathlib);
``passlib`` is used if available for hashing the seeded superadmin password.
"""

import os
import sys
import shutil
import sqlite3
import traceback
from pathlib import Path

# --------------------------------------------------------------------------- #
# Step 1: resolve paths from config (with safe fallbacks under the repo root)  #
# --------------------------------------------------------------------------- #
# scripts/ -> repo root is one level up.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

CONFIG_OK = True
_CONFIG_ERR = None
try:
    from config import DB_PATH, ANALYTICS_DB, ASSETS_DIR, DEFAULT_TENANT_ID

    DB_PATH = Path(DB_PATH)
    ANALYTICS_DB = Path(ANALYTICS_DB)
    ASSETS_DIR = Path(ASSETS_DIR)
    DEFAULT_TENANT_ID = int(DEFAULT_TENANT_ID)
except Exception as exc:  # pragma: no cover - defensive fallback
    CONFIG_OK = False
    _CONFIG_ERR = exc
    DB_PATH = REPO_ROOT / "backend" / "conversations.db"
    ANALYTICS_DB = REPO_ROOT / "backend" / "analytics.db"
    ASSETS_DIR = REPO_ROOT / "backend" / "assets"
    DEFAULT_TENANT_ID = 1

# users.db always lives next to the login server, regardless of config.
USERS_DB = REPO_ROOT / "Login_system" / "users.db"

# --------------------------------------------------------------------------- #
# Optional passlib for the seeded superadmin password.                         #
# login_server.py uses CryptContext(schemes=["bcrypt_sha256", ...]), so a      #
# bcrypt_sha256 hash produced here is verifiable by the app on login.          #
# --------------------------------------------------------------------------- #
try:
    from passlib.hash import bcrypt_sha256 as _bcrypt_sha256

    def hash_password(raw: str) -> str:
        return _bcrypt_sha256.hash(raw)

    HASH_SCHEME = "passlib bcrypt_sha256"
    PASSLIB_OK = True
except Exception:
    import hashlib as _hashlib

    def hash_password(raw: str) -> str:
        # Clearly-marked, NON-VERIFIABLE fallback. If you see this scheme in the
        # DB, install passlib and reset the superadmin password via the app.
        return "INSECURE-FALLBACK-SHA256$" + _hashlib.sha256(raw.encode("utf-8")).hexdigest()

    HASH_SCHEME = "INSECURE sha256 fallback (passlib unavailable - reset password via app!)"
    PASSLIB_OK = False


SUPERADMIN_USERNAME = "superadmin"
SUPERADMIN_PASSWORD = "superadmin123"

# Tenant registry schema (mirrors Login_system/login_server.py::init_db).
CREATE_TENANTS_SQL = """
    CREATE TABLE IF NOT EXISTS tenants (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        slug TEXT UNIQUE NOT NULL,
        active INTEGER DEFAULT 1,
        plan TEXT DEFAULT 'standard',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
"""


# --------------------------------------------------------------------------- #
# Small sqlite helpers                                                         #
# --------------------------------------------------------------------------- #
def table_exists(conn: sqlite3.Connection, table: str) -> bool:
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    )
    return cur.fetchone() is not None


def column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    cur = conn.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in cur.fetchall())


def ensure_tenant_column(conn: sqlite3.Connection, table: str, default_tenant_id: int) -> None:
    """Add a ``tenant_id`` column to ``table`` if missing, then backfill NULLs."""
    if not table_exists(conn, table):
        print(f"  - table '{table}' not present; skipping")
        return

    if not column_exists(conn, table, "tenant_id"):
        # default_tenant_id is coerced to int so it is safe to inline.
        conn.execute(
            f"ALTER TABLE {table} ADD COLUMN tenant_id INTEGER DEFAULT {int(default_tenant_id)}"
        )
        print(f"  - {table}: added tenant_id column (default {default_tenant_id})")
    else:
        print(f"  - {table}: tenant_id column already present")

    cur = conn.execute(
        f"UPDATE {table} SET tenant_id=? WHERE tenant_id IS NULL",
        (default_tenant_id,),
    )
    backfilled = cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
    print(f"  - {table}: backfilled {backfilled} NULL tenant_id -> {default_tenant_id}")


# --------------------------------------------------------------------------- #
# Step 2: backups                                                             #
# --------------------------------------------------------------------------- #
def backup_file(path: Path) -> None:
    path = Path(path)
    if not path.exists():
        print(f"  - {path.name}: does not exist; nothing to back up")
        return
    backup = Path(str(path) + ".pre_mt_backup")
    if backup.exists():
        print(f"  - {path.name}: backup already exists ({backup.name}); skipping")
        return
    shutil.copy2(str(path), str(backup))
    print(f"  - {path.name}: backed up -> {backup.name}")


def backup_all() -> None:
    for db in (USERS_DB, DB_PATH, ANALYTICS_DB):
        backup_file(db)


# --------------------------------------------------------------------------- #
# Step 3: users.db                                                            #
# --------------------------------------------------------------------------- #
def migrate_users_db() -> None:
    # sqlite3.connect creates the file if it does not exist. We intentionally
    # operate even on a missing users.db so the superadmin is guaranteed to
    # exist after migration.
    USERS_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(USERS_DB))
    try:
        # tenants registry
        conn.execute(CREATE_TENANTS_SQL)
        cur = conn.execute("SELECT id FROM tenants WHERE id=?", (DEFAULT_TENANT_ID,))
        if cur.fetchone() is None:
            conn.execute(
                "INSERT INTO tenants (id, name, slug, active, plan) "
                "VALUES (?, 'Default', 'default', 1, 'standard')",
                (DEFAULT_TENANT_ID,),
            )
            print(f"  - seeded default tenant id={DEFAULT_TENANT_ID} (slug='default')")
        else:
            print(f"  - default tenant id={DEFAULT_TENANT_ID} already present")

        # users table: create a compatible schema if missing, else ensure col.
        if not table_exists(conn, "users"):
            conn.execute(
                f"""
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE,
                    password_hash TEXT,
                    role TEXT,
                    mfa_enabled INTEGER DEFAULT 0,
                    mfa_secret TEXT,
                    active INTEGER DEFAULT 1,
                    google_id TEXT UNIQUE,
                    email TEXT,
                    profile_picture TEXT,
                    auth_provider TEXT DEFAULT 'local',
                    email_verified INTEGER DEFAULT 0,
                    full_name TEXT,
                    tenant_id INTEGER DEFAULT {int(DEFAULT_TENANT_ID)},
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            print("  - created users table (was missing)")
        else:
            ensure_tenant_column(conn, "users", DEFAULT_TENANT_ID)

        # superadmin: ensure at least one user with role 'superadmin' exists.
        cur = conn.execute("SELECT COUNT(*) FROM users WHERE role='superadmin'")
        if cur.fetchone()[0] > 0:
            print("  - superadmin role already present; leaving as-is")
        else:
            cur = conn.execute(
                "SELECT id FROM users WHERE username=?", (SUPERADMIN_USERNAME,)
            )
            if cur.fetchone() is not None:
                print(
                    f"  - WARNING: a '{SUPERADMIN_USERNAME}' username exists without the "
                    "superadmin role; not modifying it. Promote it manually if needed."
                )
            else:
                conn.execute(
                    "INSERT INTO users (username, password_hash, role, active, tenant_id) "
                    "VALUES (?, ?, 'superadmin', 1, ?)",
                    (SUPERADMIN_USERNAME, hash_password(SUPERADMIN_PASSWORD), DEFAULT_TENANT_ID),
                )
                print(
                    f"  - created superadmin user '{SUPERADMIN_USERNAME}' "
                    f"(password '{SUPERADMIN_PASSWORD}', hash: {HASH_SCHEME})"
                )

        conn.commit()
    finally:
        conn.close()


def migrate_memberships() -> None:
    """Create tenant_memberships and backfill default-tenant customer access."""
    USERS_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(USERS_DB))
    try:
        conn.execute(
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
        cur = conn.execute("PRAGMA table_info(tenants)")
        cols = {row[1] for row in cur.fetchall()}
        if "allow_multiple_admins" not in cols:
            conn.execute(
                "ALTER TABLE tenants ADD COLUMN allow_multiple_admins INTEGER DEFAULT 0"
            )
            print("  - tenants: added allow_multiple_admins column")
        cur = conn.execute(
            """
            SELECT username FROM users
            WHERE role='customer' AND (tenant_id IS NULL OR tenant_id=?)
            """,
            (DEFAULT_TENANT_ID,),
        )
        backfilled = 0
        for (username,) in cur.fetchall():
            exists = conn.execute(
                "SELECT id FROM tenant_memberships WHERE username=? AND tenant_id=?",
                (username, DEFAULT_TENANT_ID),
            ).fetchone()
            if exists:
                continue
            conn.execute(
                """
                INSERT INTO tenant_memberships
                (username, tenant_id, status, reviewed_by, reviewed_at)
                VALUES (?, ?, 'approved', 'migration', CURRENT_TIMESTAMP)
                """,
                (username, DEFAULT_TENANT_ID),
            )
            backfilled += 1
        conn.commit()
        print(f"  - tenant_memberships ready; backfilled {backfilled} approved membership(s)")
    finally:
        conn.close()
def migrate_conversations_db() -> None:
    if not DB_PATH.exists():
        print(
            f"  - conversations DB {DB_PATH} does not exist; skipping "
            "(the backend creates it tenant-aware on first run)"
        )
        return

    conn = sqlite3.connect(str(DB_PATH))
    try:
        for table in ("conversations", "sessions"):
            ensure_tenant_column(conn, table, DEFAULT_TENANT_ID)

        # Tenant-scoped indexes (only if the base tables exist).
        if table_exists(conn, "conversations"):
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_conversations_tenant_conn "
                "ON conversations (tenant_id, connection_id)"
            )
            print("  - ensured index idx_conversations_tenant_conn (tenant_id, connection_id)")
        if table_exists(conn, "sessions"):
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_sessions_tenant "
                "ON sessions (tenant_id)"
            )
            print("  - ensured index idx_sessions_tenant (tenant_id)")

        conn.commit()
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# Step 5: analytics DB                                                        #
# --------------------------------------------------------------------------- #
ANALYTICS_TABLES = (
    "usage_stats",
    "satisfaction_ratings",
    "session_analytics",
    "kb_document_versions",
)


def migrate_analytics_db() -> None:
    if not ANALYTICS_DB.exists():
        print(
            f"  - analytics DB {ANALYTICS_DB} does not exist; skipping "
            "(the backend creates it tenant-aware on first run)"
        )
        return

    conn = sqlite3.connect(str(ANALYTICS_DB))
    try:
        for table in ANALYTICS_TABLES:
            ensure_tenant_column(conn, table, DEFAULT_TENANT_ID)
        conn.commit()
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# Step 6: assets                                                              #
# --------------------------------------------------------------------------- #
def migrate_assets() -> None:
    if not ASSETS_DIR.exists():
        print(f"  - assets dir {ASSETS_DIR} does not exist; skipping")
        return

    target = ASSETS_DIR / f"tenant_{DEFAULT_TENANT_ID}"
    target.mkdir(parents=True, exist_ok=True)
    print(f"  - target dir: {target}")

    moved = 0
    skipped = 0
    # sorted(...) materializes the listing before we start moving, so mutating
    # the directory during the loop is safe.
    for entry in sorted(ASSETS_DIR.iterdir()):
        if entry.is_dir():
            # Skip subdirectories, including tenant_* folders already migrated.
            continue
        dest = target / entry.name
        if dest.exists():
            print(f"  - skip (already in tenant dir): {entry.name}")
            skipped += 1
            continue
        shutil.move(str(entry), str(dest))
        print(f"  - moved: {entry.name} -> tenant_{DEFAULT_TENANT_ID}/{entry.name}")
        moved += 1

    print(f"  - assets summary: {moved} moved, {skipped} already present")


# --------------------------------------------------------------------------- #
# Step 7: Chroma note                                                         #
# --------------------------------------------------------------------------- #
def chroma_note() -> None:
    print(
        "  - No Chroma migration required: tenant "
        f"{DEFAULT_TENANT_ID} (default) reuses the existing "
        "'support_docs_v3_*' collection names, so the historical vector store "
        "remains the active KB. New tenants get namespaced collections "
        "('t<id>_support_docs_v3_*') created on demand."
    )


# --------------------------------------------------------------------------- #
# Orchestration                                                               #
# --------------------------------------------------------------------------- #
def run_step(title, func, summary, failures) -> None:
    print(f"\n=== {title} ===")
    try:
        func()
        summary.append((title, "OK"))
    except Exception as exc:
        print(f"  [ERROR] {title} failed: {exc}")
        traceback.print_exc()
        summary.append((title, f"FAILED: {exc}"))
        failures.append(title)


def main() -> int:
    print("=" * 60)
    print("Assistify single-tenant -> multi-tenant migration")
    print("=" * 60)
    print(f"Repo root      : {REPO_ROOT}")
    if CONFIG_OK:
        print("config import  : OK")
    else:
        print(f"config import  : FAILED ({_CONFIG_ERR}); using fallback defaults")
    print("Resolved paths :")
    print(f"  users.db          = {USERS_DB}")
    print(f"  conversations DB  = {DB_PATH}")
    print(f"  analytics DB      = {ANALYTICS_DB}")
    print(f"  assets dir        = {ASSETS_DIR}")
    print(f"  default tenant id = {DEFAULT_TENANT_ID}")
    print(f"  password hashing  = {HASH_SCHEME}")
    if not PASSLIB_OK:
        print(
            "  [WARNING] passlib not installed: any superadmin created here will "
            "NOT be able to log in until you install passlib and reset the password."
        )

    summary: list = []
    failures: list = []

    run_step("Step 2: Back up existing databases", backup_all, summary, failures)
    run_step("Step 3: Migrate users.db (tenants + tenant_id + superadmin)", migrate_users_db, summary, failures)
    run_step("Step 3b: Migrate tenant memberships + admin settings", migrate_memberships, summary, failures)
    run_step("Step 4: Migrate conversations DB (tenant_id + indexes)", migrate_conversations_db, summary, failures)
    run_step("Step 5: Migrate analytics DB (tenant_id)", migrate_analytics_db, summary, failures)
    run_step("Step 6: Migrate assets into per-tenant folder", migrate_assets, summary, failures)
    run_step("Step 7: Chroma note", chroma_note, summary, failures)

    print("\n" + "=" * 60)
    print("MIGRATION SUMMARY")
    print("=" * 60)
    for title, status in summary:
        print(f"  [{'OK' if status == 'OK' else 'XX'}] {title}: {status}")

    if failures:
        print(f"\n{len(failures)} step(s) FAILED: {', '.join(failures)}")
        print("Review the errors above. Re-running is safe (the script is idempotent).")
        return 1

    print("\nAll steps completed successfully. Re-running is safe (idempotent).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
