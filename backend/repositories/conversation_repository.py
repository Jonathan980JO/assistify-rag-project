"""Conversation persistence repository for the RAG backend.

The SQLite-backed conversation/message persistence already lives in
``backend/chat_store.py``. To formalize the repository layer introduced by the
architectural refactor (Phase 2) without changing any behavior, this module
re-exports that existing data-access API under the ``repositories`` namespace.

New code should depend on ``backend.repositories.conversation_repository``;
``backend/chat_store.py`` remains the single source of truth for the SQL.
"""
from backend.chat_store import (  # noqa: F401  (re-exported public API)
    init_chat_store_schema,
    create_conversation,
    get_conversation,
    get_or_create_conversation,
    list_conversations_summary,
    append_message,
    append_conversation_message,
    get_active_tenant_id,
    set_active_tenant,
    rename_conversation,
    delete_conversation,
    delete_all_conversations,
    load_conversation_messages,
    purge_tenant_chat_data,
    migrate_from_json,
)

__all__ = [
    "init_chat_store_schema",
    "create_conversation",
    "get_conversation",
    "get_or_create_conversation",
    "list_conversations_summary",
    "append_message",
    "append_conversation_message",
    "get_active_tenant_id",
    "set_active_tenant",
    "rename_conversation",
    "delete_conversation",
    "delete_all_conversations",
    "load_conversation_messages",
    "purge_tenant_chat_data",
    "migrate_from_json",
]
