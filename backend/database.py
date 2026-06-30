# database.py - SQLite Database for Conversation History
import sqlite3
from datetime import datetime
from pathlib import Path
try:
    from config import DB_PATH
except Exception:
    DB_PATH = Path(__file__).resolve().parent / "conversations.db"

try:
    from config import DEFAULT_TENANT_ID
except Exception:
    DEFAULT_TENANT_ID = 1

# Ensure DB_PATH is a string path for sqlite3
DB_PATH = str(DB_PATH)
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Database")


def _coerce_tenant_id(tenant_id) -> int:
    """Normalize a tenant id, defaulting to the canonical tenant."""
    try:
        tid = int(tenant_id)
    except (TypeError, ValueError):
        return DEFAULT_TENANT_ID
    return tid if tid > 0 else DEFAULT_TENANT_ID


def _ensure_tenant_column(cursor, table: str):
    """Add tenant_id to an existing table and backfill onto the default tenant."""
    cursor.execute(f"PRAGMA table_info({table})")
    cols = [row[1] for row in cursor.fetchall()]
    if "tenant_id" not in cols:
        cursor.execute(
            f"ALTER TABLE {table} ADD COLUMN tenant_id INTEGER DEFAULT {DEFAULT_TENANT_ID}"
        )
        cursor.execute(
            f"UPDATE {table} SET tenant_id=? WHERE tenant_id IS NULL",
            (DEFAULT_TENANT_ID,),
        )


def init_database():
    """Initialize SQLite database with required tables"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Conversations table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id INTEGER DEFAULT 1,
                connection_id TEXT NOT NULL,
                user_message TEXT NOT NULL,
                ai_response TEXT NOT NULL,
                retrieved_docs TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Sessions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id INTEGER DEFAULT 1,
                connection_id TEXT UNIQUE NOT NULL,
                start_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                end_time DATETIME,
                message_count INTEGER DEFAULT 0
            )
        ''')

        # Backfill tenant_id for databases created before multi-tenancy.
        _ensure_tenant_column(cursor, "conversations")
        _ensure_tenant_column(cursor, "sessions")
        _ensure_ui_conversations_table(cursor)

        # Tenant-scoped indexes: most reads filter by (tenant_id, connection_id).
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_conversations_tenant_conn "
            "ON conversations (tenant_id, connection_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_sessions_tenant "
            "ON sessions (tenant_id)"
        )

        conn.commit()
        conn.close()
        logger.info("✓ Database initialized")
        return True
    except Exception as e:
        logger.error(f"Database initialization error: {e}")
        return False


def _ensure_ui_conversations_table(cursor) -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS ui_conversations (
            id TEXT PRIMARY KEY,
            tenant_id INTEGER NOT NULL,
            username TEXT NOT NULL,
            title TEXT NOT NULL DEFAULT 'New chat',
            messages_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_ui_conv_tenant_user "
        "ON ui_conversations (tenant_id, username)"
    )


def init_ui_conversations_schema() -> None:
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        _ensure_ui_conversations_table(cursor)
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"UI conversations schema error: {e}")


def ui_list_conversations(tenant_id: int, username: str) -> list[dict]:
    init_ui_conversations_schema()
    tid = _coerce_tenant_id(tenant_id)
    user = str(username or "").strip()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, title, updated_at
        FROM ui_conversations
        WHERE tenant_id = ? AND username = ?
        ORDER BY updated_at DESC
        """,
        (tid, user),
    )
    rows = cursor.fetchall()
    conn.close()
    return [{"id": r[0], "title": r[1], "updated_at": r[2]} for r in rows]


def ui_get_conversation(conversation_id: str, tenant_id: int, username: str) -> dict | None:
    init_ui_conversations_schema()
    tid = _coerce_tenant_id(tenant_id)
    user = str(username or "").strip()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, title, messages_json, created_at, updated_at
        FROM ui_conversations
        WHERE id = ? AND tenant_id = ? AND username = ?
        """,
        (str(conversation_id), tid, user),
    )
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    import json
    try:
        messages = json.loads(row[2] or "[]")
    except Exception:
        messages = []
    return {
        "id": row[0],
        "title": row[1],
        "messages": messages,
        "created_at": row[3],
        "updated_at": row[4],
    }


def ui_create_conversation(tenant_id: int, username: str, title: str | None = None) -> dict:
    import json
    import uuid
    from datetime import datetime, timezone

    init_ui_conversations_schema()
    tid = _coerce_tenant_id(tenant_id)
    user = str(username or "").strip()
    now = datetime.now(timezone.utc).isoformat()
    conv_id = str(uuid.uuid4())
    conv_title = (title or "New chat").strip() or "New chat"
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO ui_conversations (id, tenant_id, username, title, messages_json, created_at, updated_at)
        VALUES (?, ?, ?, ?, '[]', ?, ?)
        """,
        (conv_id, tid, user, conv_title, now, now),
    )
    conn.commit()
    conn.close()
    return {
        "id": conv_id,
        "title": conv_title,
        "messages": [],
        "created_at": now,
        "updated_at": now,
    }


def ui_append_message(
    conversation_id: str,
    tenant_id: int,
    username: str,
    role: str,
    text: str,
) -> dict | None:
    import json
    from datetime import datetime, timezone

    conv = ui_get_conversation(conversation_id, tenant_id, username)
    if conv is None:
        return None
    messages = list(conv.get("messages") or [])
    messages.append({"role": str(role).strip().lower(), "text": str(text or "").strip()})
    title = conv.get("title") or "New chat"
    if role == "user" and title == "New chat":
        words = str(text or "").split()
        title = (" ".join(words[:8]) + ("..." if len(words) > 8 else ""))[:80] or "New chat"
    now = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE ui_conversations
        SET messages_json = ?, title = ?, updated_at = ?
        WHERE id = ? AND tenant_id = ? AND username = ?
        """,
        (json.dumps(messages, ensure_ascii=False), title, now, conversation_id, _coerce_tenant_id(tenant_id), str(username or "").strip()),
    )
    conn.commit()
    conn.close()
    return ui_get_conversation(conversation_id, tenant_id, username)


def ui_rename_conversation(
    conversation_id: str,
    tenant_id: int,
    username: str,
    title: str,
) -> dict | None:
    from datetime import datetime, timezone

    conv = ui_get_conversation(conversation_id, tenant_id, username)
    if conv is None:
        return None
    now = datetime.now(timezone.utc).isoformat()
    title_value = str(title or "").strip()[:80] or "New chat"
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE ui_conversations SET title = ?, updated_at = ?
        WHERE id = ? AND tenant_id = ? AND username = ?
        """,
        (title_value, now, conversation_id, _coerce_tenant_id(tenant_id), str(username or "").strip()),
    )
    conn.commit()
    conn.close()
    return {"id": conversation_id, "title": title_value, "updated_at": now}


def ui_delete_conversation(conversation_id: str, tenant_id: int, username: str) -> bool:
    init_ui_conversations_schema()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM ui_conversations WHERE id = ? AND tenant_id = ? AND username = ?",
        (str(conversation_id), _coerce_tenant_id(tenant_id), str(username or "").strip()),
    )
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


def migrate_json_conversations_to_db(json_path, tenant_id=None, username: str = "legacy") -> int:
    """One-time import from conversations.json into tenant 1."""
    import json
    from pathlib import Path

    path = Path(json_path)
    if not path.exists():
        return 0
    try:
        data = json.loads(path.read_text(encoding="utf-8") or "{}")
    except Exception:
        return 0
    conversations = data.get("conversations") or []
    tid = _coerce_tenant_id(tenant_id)
    count = 0
    for conv in conversations:
        if not isinstance(conv, dict) or not conv.get("id"):
            continue
        if ui_get_conversation(conv["id"], tid, username):
            continue
        init_ui_conversations_schema()
        import uuid
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc).isoformat()
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR IGNORE INTO ui_conversations
            (id, tenant_id, username, title, messages_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                conv.get("id"),
                tid,
                username,
                conv.get("title") or "New chat",
                json.dumps(conv.get("messages") or [], ensure_ascii=False),
                conv.get("created_at") or now,
                conv.get("updated_at") or now,
            ),
        )
        conn.commit()
        conn.close()
        count += 1
    return count

def save_conversation(connection_id: str, user_msg: str, ai_msg: str, docs: list = None, tenant_id=None):
    """Save a conversation exchange to database"""
    try:
        tid = _coerce_tenant_id(tenant_id)
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        docs_str = "\n---\n".join(docs) if docs else None
        
        cursor.execute('''
            INSERT INTO conversations (tenant_id, connection_id, user_message, ai_response, retrieved_docs)
            VALUES (?, ?, ?, ?, ?)
        ''', (tid, connection_id, user_msg, ai_msg, docs_str))
        
        # Update session message count (scoped to the tenant)
        cursor.execute('''
            UPDATE sessions 
            SET message_count = message_count + 1 
            WHERE connection_id = ? AND tenant_id = ?
        ''', (connection_id, tid))
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Error saving conversation: {e}")
        return False

def start_session(connection_id: str, tenant_id=None):
    """Start a new session"""
    try:
        tid = _coerce_tenant_id(tenant_id)
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR IGNORE INTO sessions (connection_id, tenant_id)
            VALUES (?, ?)
        ''', (connection_id, tid))
        
        conn.commit()
        conn.close()
        logger.info(f"✓ Started session: {connection_id} (tenant={tid})")
        return True
    except Exception as e:
        logger.error(f"Error starting session: {e}")
        return False

def end_session(connection_id: str, tenant_id=None):
    """End a session"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        if tenant_id is None:
            cursor.execute('''
                UPDATE sessions 
                SET end_time = CURRENT_TIMESTAMP 
                WHERE connection_id = ? AND end_time IS NULL
            ''', (connection_id,))
        else:
            cursor.execute('''
                UPDATE sessions 
                SET end_time = CURRENT_TIMESTAMP 
                WHERE connection_id = ? AND tenant_id = ? AND end_time IS NULL
            ''', (connection_id, _coerce_tenant_id(tenant_id)))
        
        conn.commit()
        conn.close()
        logger.info(f"✓ Ended session: {connection_id}")
        return True
    except Exception as e:
        logger.error(f"Error ending session: {e}")
        return False

def get_conversation_history(connection_id: str, limit: int = 50, tenant_id=None):
    """Get conversation history for a connection (optionally scoped to a tenant)"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        if tenant_id is None:
            cursor.execute('''
                SELECT user_message, ai_response, timestamp 
                FROM conversations 
                WHERE connection_id = ? 
                ORDER BY timestamp DESC 
                LIMIT ?
            ''', (connection_id, limit))
        else:
            cursor.execute('''
                SELECT user_message, ai_response, timestamp 
                FROM conversations 
                WHERE connection_id = ? AND tenant_id = ?
                ORDER BY timestamp DESC 
                LIMIT ?
            ''', (connection_id, _coerce_tenant_id(tenant_id), limit))
        
        results = cursor.fetchall()
        conn.close()
        return results
    except Exception as e:
        logger.error(f"Error getting history: {e}")
        return []

def get_stats(tenant_id=None):
    """Get database statistics (optionally scoped to a single tenant)"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        if tenant_id is None:
            cursor.execute('SELECT COUNT(*) FROM conversations')
            total_messages = cursor.fetchone()[0]
            cursor.execute('SELECT COUNT(*) FROM sessions')
            total_sessions = cursor.fetchone()[0]
            cursor.execute('SELECT COUNT(*) FROM sessions WHERE end_time IS NOT NULL')
            completed_sessions = cursor.fetchone()[0]
        else:
            tid = _coerce_tenant_id(tenant_id)
            cursor.execute('SELECT COUNT(*) FROM conversations WHERE tenant_id = ?', (tid,))
            total_messages = cursor.fetchone()[0]
            cursor.execute('SELECT COUNT(*) FROM sessions WHERE tenant_id = ?', (tid,))
            total_sessions = cursor.fetchone()[0]
            cursor.execute('SELECT COUNT(*) FROM sessions WHERE tenant_id = ? AND end_time IS NOT NULL', (tid,))
            completed_sessions = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            "total_messages": total_messages,
            "total_sessions": total_sessions,
            "completed_sessions": completed_sessions,
            "active_sessions": total_sessions - completed_sessions
        }
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        return {}

if __name__ == "__main__":
    # Test database
    print("Testing Database...")
    init_database()
    
    test_id = "test_123"
    start_session(test_id)
    save_conversation(test_id, "Hello", "Hi there!", ["doc1"])
    
    stats = get_stats()
    print(f"\nDatabase Stats: {stats}")
    
    end_session(test_id)
