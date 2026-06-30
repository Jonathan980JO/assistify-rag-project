"""
SQLite-backed ephemeral security state for the login server.

Replaces in-memory dicts/sets for session invalidation, concurrent session
tracking, rate limiting, and account lockouts so state survives restarts and
works across multiple uvicorn workers (WAL mode).
"""
from __future__ import annotations

import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, List, Optional

DB_PATH = Path(__file__).resolve().parent / "users.db"

MAX_INVALIDATED_SESSIONS = 5000
MAX_RATE_LIMIT_ENTRIES = 10000


@contextmanager
def _conn() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(str(DB_PATH), timeout=10.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def ensure_persistent_state_schema() -> None:
    with _conn() as conn:
        c = conn.cursor()
        c.execute("PRAGMA journal_mode=WAL")
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS invalidated_sessions (
                session_id TEXT PRIMARY KEY,
                invalidated_at REAL NOT NULL
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS user_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                session_id TEXT NOT NULL,
                created_at REAL NOT NULL,
                last_activity REAL NOT NULL,
                UNIQUE(user_id, session_id)
            )
            """
        )
        c.execute(
            "CREATE INDEX IF NOT EXISTS idx_user_sessions_user ON user_sessions(user_id, created_at)"
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS rate_limit_buckets (
                identifier TEXT PRIMARY KEY,
                count INTEGER NOT NULL DEFAULT 0,
                reset_time REAL NOT NULL
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS failed_login_attempts (
                username TEXT PRIMARY KEY,
                count INTEGER NOT NULL DEFAULT 0,
                updated_at REAL NOT NULL
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS account_lockouts (
                username TEXT PRIMARY KEY,
                lockout_until REAL NOT NULL
            )
            """
        )


def is_session_invalidated(session_id: str) -> bool:
    if not session_id:
        return False
    with _conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM invalidated_sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
    return row is not None


def invalidate_session(session_id: str) -> None:
    if not session_id:
        return
    now = time.time()
    with _conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO invalidated_sessions (session_id, invalidated_at) VALUES (?, ?)",
            (session_id, now),
        )
        conn.execute("DELETE FROM user_sessions WHERE session_id = ?", (session_id,))
        _prune_invalidated_sessions(conn)


def _prune_invalidated_sessions(conn: sqlite3.Connection) -> None:
    count = conn.execute("SELECT COUNT(*) FROM invalidated_sessions").fetchone()[0]
    if count <= MAX_INVALIDATED_SESSIONS:
        return
    keep = MAX_INVALIDATED_SESSIONS // 2
    conn.execute(
        """
        DELETE FROM invalidated_sessions
        WHERE session_id NOT IN (
            SELECT session_id FROM invalidated_sessions
            ORDER BY invalidated_at DESC
            LIMIT ?
        )
        """,
        (keep,),
    )


def track_user_session(
    user_id: int,
    session_id: str,
    created_at: float,
    max_concurrent: int,
) -> Optional[str]:
    """Register session; evict oldest if over limit. Returns evicted session_id if any."""
    evicted: Optional[str] = None
    with _conn() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO user_sessions (user_id, session_id, created_at, last_activity)
            VALUES (?, ?, ?, ?)
            """,
            (user_id, session_id, created_at, created_at),
        )
        rows = conn.execute(
            """
            SELECT session_id, created_at FROM user_sessions
            WHERE user_id = ?
            ORDER BY created_at ASC
            """,
            (user_id,),
        ).fetchall()
        if len(rows) > max_concurrent:
            evicted = rows[0]["session_id"]
            conn.execute(
                "DELETE FROM user_sessions WHERE user_id = ? AND session_id = ?",
                (user_id, evicted),
            )
            conn.execute(
                "INSERT OR REPLACE INTO invalidated_sessions (session_id, invalidated_at) VALUES (?, ?)",
                (evicted, time.time()),
            )
    return evicted


def touch_user_session(session_id: str, last_activity: float) -> None:
    if not session_id:
        return
    with _conn() as conn:
        conn.execute(
            "UPDATE user_sessions SET last_activity = ? WHERE session_id = ?",
            (last_activity, session_id),
        )


def get_session_last_activity(session_id: str) -> float | None:
    """Return the DB-persisted last_activity for a session, or None if not found."""
    if not session_id:
        return None
    with _conn() as conn:
        row = conn.execute(
            "SELECT last_activity FROM user_sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
    return float(row["last_activity"]) if row else None


def check_rate_limit(identifier: str, limit: int, window_seconds: int = 60) -> bool:
    now = time.time()
    with _conn() as conn:
        _prune_expired_rate_limits(conn, now)
        row = conn.execute(
            "SELECT count, reset_time FROM rate_limit_buckets WHERE identifier = ?",
            (identifier,),
        ).fetchone()
        if row is None or now > row["reset_time"]:
            conn.execute(
                """
                INSERT OR REPLACE INTO rate_limit_buckets (identifier, count, reset_time)
                VALUES (?, 1, ?)
                """,
                (identifier, now + window_seconds),
            )
            return True
        if row["count"] >= limit:
            return False
        conn.execute(
            "UPDATE rate_limit_buckets SET count = count + 1 WHERE identifier = ?",
            (identifier,),
        )
    return True


def _prune_expired_rate_limits(conn: sqlite3.Connection, now: float) -> None:
    conn.execute("DELETE FROM rate_limit_buckets WHERE reset_time < ?", (now,))
    count = conn.execute("SELECT COUNT(*) FROM rate_limit_buckets").fetchone()[0]
    if count > MAX_RATE_LIMIT_ENTRIES:
        conn.execute(
            """
            DELETE FROM rate_limit_buckets
            WHERE identifier NOT IN (
                SELECT identifier FROM rate_limit_buckets
                ORDER BY reset_time DESC
                LIMIT ?
            )
            """,
            (MAX_RATE_LIMIT_ENTRIES // 2,),
        )


def check_account_lockout(username: str) -> tuple[bool, int]:
    now = time.time()
    with _conn() as conn:
        expired_users = [
            r["username"]
            for r in conn.execute(
                "SELECT username FROM account_lockouts WHERE lockout_until <= ?",
                (now,),
            ).fetchall()
        ]
        conn.execute("DELETE FROM account_lockouts WHERE lockout_until <= ?", (now,))
        for u in expired_users:
            conn.execute("DELETE FROM failed_login_attempts WHERE username = ?", (u,))
        row = conn.execute(
            "SELECT lockout_until FROM account_lockouts WHERE username = ?",
            (username,),
        ).fetchone()
        if row:
            remaining = int(row["lockout_until"] - now)
            return True, max(0, remaining)
    return False, 0


def record_failed_login(username: str) -> int:
    now = time.time()
    with _conn() as conn:
        row = conn.execute(
            "SELECT count FROM failed_login_attempts WHERE username = ?",
            (username,),
        ).fetchone()
        count = (row["count"] if row else 0) + 1
        conn.execute(
            """
            INSERT OR REPLACE INTO failed_login_attempts (username, count, updated_at)
            VALUES (?, ?, ?)
            """,
            (username, count, now),
        )
    return count


def set_account_lockout(username: str, lockout_until: float) -> None:
    with _conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO account_lockouts (username, lockout_until) VALUES (?, ?)",
            (username, lockout_until),
        )


def clear_failed_attempts(username: str) -> None:
    with _conn() as conn:
        conn.execute("DELETE FROM failed_login_attempts WHERE username = ?", (username,))
        conn.execute("DELETE FROM account_lockouts WHERE username = ?", (username,))


def get_failed_attempt_count(username: str) -> int:
    with _conn() as conn:
        row = conn.execute(
            "SELECT count FROM failed_login_attempts WHERE username = ?",
            (username,),
        ).fetchone()
    return int(row["count"]) if row else 0
