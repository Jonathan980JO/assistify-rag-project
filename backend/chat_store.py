"""Normalized per-owner chat storage with per-message tenant_id and active tenant state."""
from __future__ import annotations

import logging
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

try:
    from config import DB_PATH, DEFAULT_TENANT_ID
except Exception:
    DB_PATH = Path(__file__).resolve().parent / "conversations.db"
    DEFAULT_TENANT_ID = 1

DB_PATH = str(DB_PATH)
logger = logging.getLogger("ChatStore")
_store_lock = Lock()

VALID_ROLES = frozenset({"user", "assistant", "system"})


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _coerce_tenant_id(tenant_id) -> int:
    try:
        tid = int(tenant_id)
    except (TypeError, ValueError):
        return DEFAULT_TENANT_ID
    return tid if tid > 0 else DEFAULT_TENANT_ID


def _title_from_text(text: str) -> str:
    words = re.findall(r"\S+", str(text or "").strip())
    if not words:
        return "New chat"
    title = " ".join(words[:8])
    if len(words) > 8:
        title += "..."
    return title[:80]


def init_chat_store_schema() -> None:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS chat_conversations (
            id TEXT PRIMARY KEY,
            owner TEXT NOT NULL,
            session_id TEXT,
            title TEXT NOT NULL DEFAULT 'New chat',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS chat_conversation_state (
            conversation_id TEXT PRIMARY KEY,
            active_tenant_id INTEGER NOT NULL,
            last_changed_at TEXT NOT NULL,
            FOREIGN KEY (conversation_id) REFERENCES chat_conversations(id) ON DELETE CASCADE
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS chat_messages (
            id TEXT PRIMARY KEY,
            conversation_id TEXT NOT NULL,
            tenant_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (conversation_id) REFERENCES chat_conversations(id) ON DELETE CASCADE
        )
        """
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_chat_messages_conv "
        "ON chat_messages (conversation_id, created_at)"
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_chat_conversations_owner "
        "ON chat_conversations (owner, updated_at DESC)"
    )
    conn.commit()
    conn.close()


def _get_owner_conversation(cursor, conversation_id: str, owner: str | None) -> sqlite3.Row | None:
    owner_val = str(owner or "").strip()
    cursor.execute(
        "SELECT id, owner, session_id, title, created_at, updated_at "
        "FROM chat_conversations WHERE id = ?",
        (str(conversation_id),),
    )
    row = cursor.fetchone()
    if not row:
        return None
    if owner_val and str(row[1]) != owner_val:
        return None
    return row


def _load_messages(cursor, conversation_id: str) -> list[dict]:
    cursor.execute(
        """
        SELECT id, tenant_id, role, content, created_at
        FROM chat_messages
        WHERE conversation_id = ?
        ORDER BY created_at ASC
        """,
        (str(conversation_id),),
    )
    rows = cursor.fetchall()
    return [
        {
            "id": r[0],
            "tenant_id": int(r[1]),
            "role": r[2],
            "text": r[3],
            "content": r[3],
            "created_at": r[4],
        }
        for r in rows
    ]


def _get_active_tenant_id(cursor, conversation_id: str) -> int | None:
    cursor.execute(
        "SELECT active_tenant_id FROM chat_conversation_state WHERE conversation_id = ?",
        (str(conversation_id),),
    )
    row = cursor.fetchone()
    if not row:
        return None
    return int(row[0])


def _conversation_detail(cursor, conversation_id: str, owner: str | None) -> dict | None:
    row = _get_owner_conversation(cursor, conversation_id, owner)
    if not row:
        return None
    active = _get_active_tenant_id(cursor, conversation_id)
    messages = _load_messages(cursor, conversation_id)
    return {
        "id": row[0],
        "owner": row[1],
        "session_id": row[2],
        "title": row[3] or "New chat",
        "created_at": row[4],
        "updated_at": row[5],
        "active_tenant_id": active,
        "messages": messages,
    }


def create_conversation(
    owner: str | None,
    active_tenant_id=None,
    title: str | None = None,
    session_id: str | None = None,
) -> dict:
    init_chat_store_schema()
    owner_val = str(owner or "").strip() or "anon"
    tid = _coerce_tenant_id(active_tenant_id)
    now = _utc_now_iso()
    conv_id = str(uuid.uuid4())
    conv_title = (title or "New chat").strip() or "New chat"
    with _store_lock:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO chat_conversations (id, owner, session_id, title, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (conv_id, owner_val, session_id, conv_title, now, now),
        )
        cursor.execute(
            """
            INSERT INTO chat_conversation_state (conversation_id, active_tenant_id, last_changed_at)
            VALUES (?, ?, ?)
            """,
            (conv_id, tid, now),
        )
        conn.commit()
        detail = _conversation_detail(cursor, conv_id, owner_val)
        conn.close()
    logger.info("[CHAT] created id=%s owner=%s active_tenant=%s", conv_id, owner_val, tid)
    return detail or {"id": conv_id, "title": conv_title, "messages": [], "active_tenant_id": tid}


def get_conversation(conversation_id: str, owner: str | None = None) -> dict | None:
    init_chat_store_schema()
    with _store_lock:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        detail = _conversation_detail(cursor, conversation_id, owner)
        conn.close()
    return detail


def get_or_create_conversation(
    conversation_id: str | None,
    owner: str | None = None,
    active_tenant_id=None,
) -> dict:
    if conversation_id:
        existing = get_conversation(conversation_id, owner)
        if existing:
            return existing
    return create_conversation(owner=owner, active_tenant_id=active_tenant_id)


def list_conversations_summary(owner: str | None = None) -> list[dict]:
    init_chat_store_schema()
    owner_val = str(owner or "").strip()
    with _store_lock:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        if owner_val:
            cursor.execute(
                """
                SELECT id, title, updated_at
                FROM chat_conversations
                WHERE owner = ?
                ORDER BY updated_at DESC
                """,
                (owner_val,),
            )
        else:
            cursor.execute(
                """
                SELECT id, title, updated_at
                FROM chat_conversations
                ORDER BY updated_at DESC
                """
            )
        rows = cursor.fetchall()
        conn.close()
    return [{"id": r[0], "title": r[1] or "New chat", "updated_at": r[2]} for r in rows]


def append_message(
    conversation_id: str,
    role: str,
    content: str,
    tenant_id,
    owner: str | None = None,
) -> dict:
    role_value = str(role or "").strip().lower()
    if role_value not in VALID_ROLES:
        raise ValueError("role must be 'user', 'assistant', or 'system'")
    text_value = str(content or "").strip()
    tid = _coerce_tenant_id(tenant_id)
    now = _utc_now_iso()
    msg_id = str(uuid.uuid4())
    with _store_lock:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        row = _get_owner_conversation(cursor, conversation_id, owner)
        if not row:
            conn.close()
            raise KeyError(conversation_id)
        cursor.execute(
            """
            INSERT INTO chat_messages (id, conversation_id, tenant_id, role, content, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (msg_id, str(conversation_id), tid, role_value, text_value, now),
        )
        title = row[3] or "New chat"
        if role_value == "user" and title == "New chat":
            title = _title_from_text(text_value)
        cursor.execute(
            "UPDATE chat_conversations SET title = ?, updated_at = ? WHERE id = ?",
            (title, now, str(conversation_id)),
        )
        conn.commit()
        detail = _conversation_detail(cursor, conversation_id, owner)
        conn.close()
    logger.info("[CHAT] message_added role=%s id=%s tenant=%s", role_value, conversation_id, tid)
    return detail or {}


def append_conversation_message(
    conversation_id: str,
    role: str,
    text: str,
    tenant_id=None,
    owner: str | None = None,
    **_kwargs,
) -> dict:
    """Compatibility wrapper matching legacy signature."""
    return append_message(conversation_id, role, text, tenant_id, owner=owner)


def get_active_tenant_id(conversation_id: str, owner: str | None = None) -> int | None:
    init_chat_store_schema()
    with _store_lock:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        if not _get_owner_conversation(cursor, conversation_id, owner):
            conn.close()
            return None
        active = _get_active_tenant_id(cursor, conversation_id)
        conn.close()
    return active


def set_active_tenant(
    conversation_id: str,
    active_tenant_id,
    owner: str | None = None,
    *,
    system_message: str | None = None,
    message_tenant_id=None,
) -> dict:
    tid = _coerce_tenant_id(active_tenant_id)
    now = _utc_now_iso()
    with _store_lock:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        if not _get_owner_conversation(cursor, conversation_id, owner):
            conn.close()
            raise KeyError(conversation_id)
        cursor.execute(
            """
            INSERT INTO chat_conversation_state (conversation_id, active_tenant_id, last_changed_at)
            VALUES (?, ?, ?)
            ON CONFLICT(conversation_id) DO UPDATE SET
                active_tenant_id = excluded.active_tenant_id,
                last_changed_at = excluded.last_changed_at
            """,
            (str(conversation_id), tid, now),
        )
        conn.commit()
        conn.close()
    if system_message:
        msg_tid = _coerce_tenant_id(message_tenant_id if message_tenant_id is not None else tid)
        append_message(conversation_id, "system", system_message, msg_tid, owner=owner)
    logger.info("[CHAT] active_tenant_set id=%s tenant=%s", conversation_id, tid)
    detail = get_conversation(conversation_id, owner)
    return detail or {}


def rename_conversation(conversation_id: str, title: str, owner: str | None = None, **_kwargs) -> dict:
    title_value = re.sub(r"\s+", " ", str(title or "")).strip()
    if not title_value:
        raise ValueError("title must not be empty")
    if len(title_value) > 80:
        title_value = title_value[:80].rstrip()
    now = _utc_now_iso()
    with _store_lock:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        if not _get_owner_conversation(cursor, conversation_id, owner):
            conn.close()
            raise KeyError(conversation_id)
        cursor.execute(
            "UPDATE chat_conversations SET title = ?, updated_at = ? WHERE id = ?",
            (title_value, now, str(conversation_id)),
        )
        conn.commit()
        conn.close()
    return {"id": conversation_id, "title": title_value, "updated_at": now}


def delete_conversation(conversation_id: str, owner: str | None = None, **_kwargs) -> None:
    with _store_lock:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        if not _get_owner_conversation(cursor, conversation_id, owner):
            conn.close()
            raise KeyError(conversation_id)
        cursor.execute("DELETE FROM chat_messages WHERE conversation_id = ?", (str(conversation_id),))
        cursor.execute(
            "DELETE FROM chat_conversation_state WHERE conversation_id = ?",
            (str(conversation_id),),
        )
        cursor.execute("DELETE FROM chat_conversations WHERE id = ?", (str(conversation_id),))
        conn.commit()
        conn.close()
    logger.info("[CHAT] deleted id=%s", conversation_id)


def delete_all_conversations(owner: str | None = None, **_kwargs) -> int:
    owner_val = str(owner or "").strip()
    with _store_lock:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        if owner_val:
            cursor.execute("SELECT id FROM chat_conversations WHERE owner = ?", (owner_val,))
        else:
            cursor.execute("SELECT id FROM chat_conversations")
        ids = [r[0] for r in cursor.fetchall()]
        for conv_id in ids:
            cursor.execute("DELETE FROM chat_messages WHERE conversation_id = ?", (conv_id,))
            cursor.execute(
                "DELETE FROM chat_conversation_state WHERE conversation_id = ?",
                (conv_id,),
            )
            cursor.execute("DELETE FROM chat_conversations WHERE id = ?", (conv_id,))
        conn.commit()
        conn.close()
    return len(ids)


def load_conversation_messages(conversation_id: str, owner: str | None = None, **_kwargs) -> list[dict]:
    conv = get_conversation(conversation_id, owner)
    if not conv:
        raise KeyError(conversation_id)
    return conv.get("messages") or []


def purge_tenant_chat_data(tenant_id: int) -> dict:
    """Remove chat messages and reset active tenant pointers for a deleted business."""
    tid = _coerce_tenant_id(tenant_id)
    with _store_lock:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM chat_messages WHERE tenant_id = ?", (tid,))
        messages_deleted = cursor.rowcount if cursor.rowcount >= 0 else 0
        cursor.execute(
            """
            UPDATE chat_conversation_state
            SET active_tenant_id = ?, last_changed_at = ?
            WHERE active_tenant_id = ?
            """,
            (DEFAULT_TENANT_ID, _utc_now_iso(), tid),
        )
        states_reset = cursor.rowcount if cursor.rowcount >= 0 else 0
        conn.commit()
        conn.close()
    logger.info(
        "[CHAT] purge_tenant tenant=%s messages_deleted=%s states_reset=%s",
        tid,
        messages_deleted,
        states_reset,
    )
    return {"messages_deleted": messages_deleted, "states_reset": states_reset}


def migrate_from_json(json_path: Path, default_tenant_id=None) -> int:
    """Import conversations.json into normalized chat tables."""
    import json

    init_chat_store_schema()
    path = Path(json_path)
    if not path.exists():
        return 0
    try:
        data = json.loads(path.read_text(encoding="utf-8") or "{}")
    except Exception:
        return 0
    conversations = data.get("conversations") or []
    default_tid = _coerce_tenant_id(default_tenant_id)
    imported = 0
    for conv in conversations:
        if not isinstance(conv, dict) or not conv.get("id"):
            continue
        conv_id = str(conv["id"])
        if get_conversation(conv_id, conv.get("owner")):
            continue
        conv_tid = _coerce_tenant_id(conv.get("tenant_id") or default_tid)
        owner = str(conv.get("owner") or "legacy").strip() or "legacy"
        title = conv.get("title") or "New chat"
        created = conv.get("created_at") or _utc_now_iso()
        updated = conv.get("updated_at") or created
        messages = conv.get("messages") or []
        last_msg_tid = conv_tid
        with _store_lock:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR IGNORE INTO chat_conversations
                (id, owner, session_id, title, created_at, updated_at)
                VALUES (?, ?, NULL, ?, ?, ?)
                """,
                (conv_id, owner, title, created, updated),
            )
            for msg in messages:
                if not isinstance(msg, dict):
                    continue
                role = str(msg.get("role") or "user").lower()
                if role not in VALID_ROLES:
                    role = "user"
                content = str(msg.get("text") or msg.get("content") or "")
                msg_tid = _coerce_tenant_id(msg.get("tenant_id") or conv_tid)
                last_msg_tid = msg_tid
                cursor.execute(
                    """
                    INSERT OR IGNORE INTO chat_messages
                    (id, conversation_id, tenant_id, role, content, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (str(uuid.uuid4()), conv_id, msg_tid, role, content, updated),
                )
            cursor.execute(
                """
                INSERT OR REPLACE INTO chat_conversation_state
                (conversation_id, active_tenant_id, last_changed_at)
                VALUES (?, ?, ?)
                """,
                (conv_id, last_msg_tid, updated),
            )
            conn.commit()
            conn.close()
        imported += 1
    return imported
