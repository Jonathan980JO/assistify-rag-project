"""Conversation store and CRUD orchestration for the RAG backend.

Extracted verbatim from ``assistify_rag_server.py`` during the Phase 8C
refactor. This module owns the JSON conversation-store helpers and the
SQLite-backed CRUD wrappers that delegate to :mod:`backend.chat_store`.

Behavior-preserving notes:
- ``CONVERSATIONS_FILE`` resolves to ``backend/conversations.json`` exactly as
  the monolith did (``backend/`` is this file's parent's parent).
- The in-memory runtime maps (``conversation_history`` etc.) and the
  follow-up/websocket-coupled memory helpers stay in the server module; only
  the self-contained store and CRUD functions live here.
- This module never imports ``assistify_rag_server`` (avoids an import cycle).
"""
import json
import re
import uuid
import logging
from contextlib import contextmanager
from pathlib import Path
from threading import RLock

from backend import chat_store as _chat_store
from backend.tenant_access import (
    assert_chat_tenant_allowed,
    get_tenant_name,
    resolve_active_chat_tenant,
)
from backend.config_head import DEFAULT_TENANT_ID
from backend.core.tenant_context import current_tenant_id
from backend.utils.text import _utc_now_iso

logger = logging.getLogger("Assistify")

CONVERSATIONS_FILE = Path(__file__).resolve().parent.parent / "conversations.json"
_conversation_store_lock = RLock()


def _empty_conversation_store() -> dict:
    return {"conversations": []}


def _ensure_conversation_store_file_unlocked() -> None:
    if not CONVERSATIONS_FILE.exists():
        CONVERSATIONS_FILE.write_text(
            json.dumps(_empty_conversation_store(), indent=2),
            encoding="utf-8",
        )


def _ensure_conversation_store_file() -> None:
    with _conversation_store_lock:
        _ensure_conversation_store_file_unlocked()


def _load_conversation_store_unlocked() -> dict:
    _ensure_conversation_store_file_unlocked()
    try:
        data = json.loads(CONVERSATIONS_FILE.read_text(encoding="utf-8") or "{}")
    except Exception:
        logger.exception("[CONV] failed to read conversation store; using empty store")
        data = _empty_conversation_store()
    if not isinstance(data, dict):
        data = _empty_conversation_store()
    conversations = data.get("conversations")
    if not isinstance(conversations, list):
        data["conversations"] = []
    return data


def _save_conversation_store_unlocked(data: dict) -> None:
    _ensure_conversation_store_file_unlocked()
    tmp_path = CONVERSATIONS_FILE.with_suffix(".json.tmp")
    tmp_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp_path.replace(CONVERSATIONS_FILE)


@contextmanager
def _mutating_conversation_store():
    """Hold the store lock across read-modify-write to prevent lost updates."""
    with _conversation_store_lock:
        data = _load_conversation_store_unlocked()
        yield data
        _save_conversation_store_unlocked(data)


def _load_conversation_store() -> dict:
    with _conversation_store_lock:
        return _load_conversation_store_unlocked()


def _save_conversation_store(data: dict) -> None:
    with _conversation_store_lock:
        _save_conversation_store_unlocked(data)


def _find_conversation(data: dict, conversation_id: str) -> dict | None:
    for conversation in data.get("conversations", []) or []:
        if isinstance(conversation, dict) and conversation.get("id") == conversation_id:
            return conversation
    return None


def _coerce_owner(user) -> str | None:
    """Extract the owning username from a session-user dict (or None)."""
    if isinstance(user, dict):
        name = str(user.get("username") or "").strip()
        return name or None
    if isinstance(user, str):
        return user.strip() or None
    return None


def _conv_tenant_of(conversation: dict) -> int:
    """Tenant a stored conversation belongs to (legacy rows default tenant)."""
    val = conversation.get("tenant_id") if isinstance(conversation, dict) else None
    if val is None:
        return DEFAULT_TENANT_ID
    try:
        return int(val)
    except (TypeError, ValueError):
        return DEFAULT_TENANT_ID


def _conversation_in_scope(conversation: dict, tenant_id: int | None = None, owner: str | None = None) -> bool:
    """Return True if a conversation may be accessed by owner (cross-tenant threads allowed)."""
    if conversation is None:
        return False
    if owner is None:
        return True
    c_owner = conversation.get("owner")
    if c_owner is None or str(c_owner) == "":
        return owner is None
    return str(c_owner) == str(owner)


def _resolve_chat_tenant_id(request_tenant_id, conversation_id: str | None, owner: str | None) -> int:
    return resolve_active_chat_tenant(
        request_tenant_id,
        conversation_id,
        owner,
        _chat_store.get_active_tenant_id,
    )


def set_conversation_active_tenant(
    conversation_id: str,
    active_tenant_id,
    owner: str | None = None,
    *,
    from_tenant_id: int | None = None,
    emit_system_message: bool = True,
) -> dict:
    tid = assert_chat_tenant_allowed(None, active_tenant_id)
    system_msg = None
    if emit_system_message and from_tenant_id is not None and int(from_tenant_id) != tid:
        from_name = get_tenant_name(int(from_tenant_id))
        to_name = get_tenant_name(tid)
        system_msg = f"Switched from {from_name} to {to_name}"
    return _chat_store.set_active_tenant(
        conversation_id,
        tid,
        owner=owner,
        system_message=system_msg,
        message_tenant_id=tid,
    )


def _try_claim_ownerless_conversation(conversation: dict, tenant_id: int, owner: str | None) -> bool:
    """Claim a legacy owner-less conversation for the first accessor."""
    if not isinstance(conversation, dict) or not owner:
        return False
    c_owner = conversation.get("owner")
    if c_owner is not None and str(c_owner).strip():
        return False
    if _conv_tenant_of(conversation) != int(tenant_id):
        return False
    conversation["owner"] = str(owner)
    return True


def _stamp_conversation_scope(conversation: dict, tenant_id: int, owner: str | None) -> None:
    """Persistently tag a conversation with its tenant/owner if not already set."""
    if not isinstance(conversation, dict):
        return
    if conversation.get("tenant_id") is None:
        try:
            conversation["tenant_id"] = int(tenant_id)
        except (TypeError, ValueError):
            conversation["tenant_id"] = DEFAULT_TENANT_ID
    if owner and not conversation.get("owner"):
        conversation["owner"] = str(owner)


def _conversation_title_from_text(text: str) -> str:
    words = re.findall(r"\S+", str(text or "").strip())
    if not words:
        return "New chat"
    title = " ".join(words[:8])
    if len(words) > 8:
        title += "..."
    return title[:80]


def _create_conversation_unlocked(
    data: dict,
    title: str | None = None,
    tenant_id=None,
    owner: str | None = None,
) -> dict:
    now = _utc_now_iso()
    try:
        tid = int(tenant_id) if tenant_id is not None else current_tenant_id()
    except (TypeError, ValueError):
        tid = DEFAULT_TENANT_ID
    conversation = {
        "id": str(uuid.uuid4()),
        "title": (title or "New chat").strip() or "New chat",
        "messages": [],
        "tenant_id": tid,
        "owner": str(owner).strip() if owner else None,
        "created_at": now,
        "updated_at": now,
    }
    data["conversations"].insert(0, conversation)
    logger.info("[CONV] created id=%s tenant=%s owner=%s", conversation["id"], tid, owner)
    return conversation


def create_conversation(
    title: str | None = None,
    tenant_id=None,
    owner: str | None = None,
    active_tenant_id=None,
) -> dict:
    tid = active_tenant_id if active_tenant_id is not None else tenant_id
    if tid is None:
        tid = DEFAULT_TENANT_ID
    return _chat_store.create_conversation(owner=owner, active_tenant_id=tid, title=title)


def get_or_create_conversation(
    conversation_id: str | None = None,
    tenant_id=None,
    owner: str | None = None,
    active_tenant_id=None,
) -> dict:
    tid = active_tenant_id if active_tenant_id is not None else tenant_id
    return _chat_store.get_or_create_conversation(conversation_id, owner=owner, active_tenant_id=tid)


def list_conversations_summary(tenant_id=None, owner: str | None = None) -> list[dict]:
    return _chat_store.list_conversations_summary(owner=owner)


def load_conversation_messages(conversation_id: str, tenant_id=None, owner: str | None = None) -> list[dict]:
    return _chat_store.load_conversation_messages(conversation_id, owner=owner)


def append_conversation_message(
    conversation_id: str,
    role: str,
    text: str,
    tenant_id=None,
    owner: str | None = None,
) -> dict:
    tid = tenant_id
    if tid is None:
        tid = _chat_store.get_active_tenant_id(conversation_id, owner)
    if tid is None:
        tid = DEFAULT_TENANT_ID
    assert_chat_tenant_allowed(None, tid)
    return _chat_store.append_message(conversation_id, role, text, tid, owner=owner)


def _conversation_summary(conversation: dict) -> dict:
    return {
        "id": conversation.get("id"),
        "title": conversation.get("title") or "New chat",
        "updated_at": conversation.get("updated_at"),
    }


def rename_conversation(conversation_id: str, title: str, tenant_id=None, owner: str | None = None) -> dict:
    return _chat_store.rename_conversation(conversation_id, title, owner=owner)


def _history_from_conversation_messages(conversation_id: str) -> list[dict]:
    try:
        messages = load_conversation_messages(conversation_id)
    except KeyError:
        return []
    history: list[dict] = []
    for message in messages:
        role = message.get("role")
        text = message.get("text") or message.get("content")
        if role in {"user", "assistant"}:
            history.append({"role": role, "content": str(text or "")})
    return history
