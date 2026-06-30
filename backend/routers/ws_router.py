"""WebSocket router for the RAG backend.

Phase 8K consolidates the former ``backend/routers/ws.py`` and absorbs the voice
WebSocket dependency binding (``_build_voice_ws_deps``) and handler creation
(``create_rag_ws_handler``) that previously lived in
``assistify_rag_server.py``. The monolith now only registers this router.

HIGH RISK area: the WebSocket message protocol, payloads, auth and tenant
behavior are preserved exactly. Handler bodies are byte-identical to the
monolith; the only change is that module-global references are read from the
live server module (passed to the factory) at registration/request time, which
avoids an import cycle. ``/ws`` still delegates to the handler returned by
``create_rag_ws_handler``.
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException

from backend.voice_audio.deps import VoiceWebSocketDeps
from backend.voice_audio.ws.handler import create_rag_ws_handler


def _build_voice_ws_deps(server) -> VoiceWebSocketDeps:
    """Build the voice WS deps bag from the live server module.

    Moved verbatim from the monolith; every reference now reads off ``server``
    so the deps bind to the same callables and shared state as before.
    """
    return VoiceWebSocketDeps(
        resolve_request_tenant=server.resolve_request_tenant,
        coerce_owner=server._coerce_owner,
        get_or_create_conversation=server.get_or_create_conversation,
        bind_conversation_memory=server.bind_conversation_memory,
        append_conversation_message=server.append_conversation_message,
        persist_runtime_memory=server.persist_runtime_memory,
        send_final_response=server.send_final_response,
        process_voice_transcript=server._process_voice_transcript_ws,
        process_text_message=server._process_ws_text_message,
        emit_perf_report=server._emit_perf_report,
        session_cookie=server.SESSION_COOKIE,
        serializer=server.serializer,
        set_request_tenant_id=server._request_tenant_id.set,
        resolve_chat_tenant_id=server._resolve_chat_tenant_id,
        set_conversation_active_tenant=server.set_conversation_active_tenant,
        assert_chat_tenant_allowed=server.assert_chat_tenant_allowed,
        get_tenant_name=server.get_tenant_name,
        default_tenant_id=server.DEFAULT_TENANT_ID,
        get_memory_snapshot=server._get_memory_snapshot,
        get_stable_memory_snapshot=server._get_stable_memory_snapshot,
        on_ws_disconnect=server._on_ws_disconnect,
        conversation_history=server.conversation_history,
        conversation_timestamps=server.conversation_timestamps,
        active_ws_connections=server._active_ws_connections,
        active_ws_tenants=server._active_ws_tenants,
    )


def build_ws_router(server) -> APIRouter:
    """Build the /ws and /ws/kb-events router bound to the live server module."""
    router = APIRouter()
    rag_ws_handler = create_rag_ws_handler(_build_voice_ws_deps(server))
    # Backward-compat: expose the handler on the server module as before.
    server._rag_ws_handler = rag_ws_handler

    @router.websocket("/ws")
    async def rag_ws_endpoint(websocket: WebSocket):  # pyright: ignore
        await rag_ws_handler(websocket)

    @router.websocket("/ws/kb-events")
    async def kb_events_ws(websocket: WebSocket):
        """Admin-only WebSocket that streams real-time KB mutation events.

        The admin monitoring page subscribes here to receive a live event feed.
        """
        await websocket.accept()
        token = websocket.cookies.get(server.SESSION_COOKIE)
        user = None
        if token:
            user, _err = server.load_and_validate_session_token(server.serializer, token)
        if not user or user.get("role") not in ("admin", "master_admin", "superadmin"):
            await websocket.send_json({"type": "error", "message": "Unauthorized"})
            await websocket.close(code=4003)
            return

        try:
            sub_tenant_id = server.require_request_tenant(user)
        except HTTPException:
            await websocket.send_json({"type": "error", "message": "No business assigned"})
            await websocket.close(code=4003)
            return

        server._kb_event_subscribers[websocket] = int(sub_tenant_id)
        server.logger.info(f"KB-events subscriber connected for tenant={sub_tenant_id} ({len(server._kb_event_subscribers)} total)")
        await websocket.send_json({
            "type": "connected",
            "kb_version": server._kb_global_version,
            "active_sessions": len(server._active_ws_connections),
            "message": "Subscribed to live KB events",
        })
        try:
            while True:
                msg = await websocket.receive()
                if msg.get("type") == "websocket.disconnect":
                    break
        except WebSocketDisconnect:
            pass
        except Exception:
            pass
        finally:
            server._kb_event_subscribers.pop(websocket, None)
            server.logger.info(f"KB-events subscriber disconnected ({len(server._kb_event_subscribers)} remaining)")

    return router
