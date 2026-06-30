"""Dependency injection for WebSocket voice handler (avoids circular imports)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional

from fastapi import WebSocket


@dataclass
class VoiceWebSocketDeps:
    """Callbacks implemented by assistify_rag_server for RAG routing."""

    resolve_request_tenant: Callable[[Any], int]
    coerce_owner: Callable[[Any], Optional[str]]
    get_or_create_conversation: Callable
    bind_conversation_memory: Callable
    append_conversation_message: Callable
    persist_runtime_memory: Callable
    send_final_response: Callable
    process_voice_transcript: Callable
    process_text_message: Callable
    emit_perf_report: Optional[Callable] = None
    session_cookie: str = "session"
    serializer: Any = None
    set_request_tenant_id: Optional[Callable[[int], None]] = None
    resolve_chat_tenant_id: Optional[Callable] = None
    set_conversation_active_tenant: Optional[Callable] = None
    assert_chat_tenant_allowed: Optional[Callable] = None
    get_tenant_name: Optional[Callable] = None
    default_tenant_id: int = 1
    get_memory_snapshot: Callable = lambda: {"gpu_reserved_mb": 0, "gpu_allocated_mb": 0, "cpu_rss_mb": 0}
    get_stable_memory_snapshot: Callable = None
    on_ws_connect: Optional[Callable] = None
    on_ws_disconnect: Optional[Callable] = None
    on_ws_disconnect: Optional[Callable[[str], None]] = None
    conversation_history: Any = None
    conversation_timestamps: Any = None
    active_ws_connections: Any = None
    active_ws_tenants: Any = None
