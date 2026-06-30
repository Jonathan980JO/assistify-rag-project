"""Conversation REST routes for the RAG backend.

Extracted from ``assistify_rag_server.py`` during the Phase 8C refactor.

The handlers read live server state (conversation CRUD functions, chat store,
request models and auth dependencies). To keep behavior byte-identical and
avoid an import cycle with the server module, the router is built by a factory
that receives the live server module and reads attributes from it at request
time. Paths, methods, and response bodies are unchanged.
"""
from fastapi import APIRouter, Body, Depends, HTTPException


def build_conversation_router(server) -> APIRouter:
    """Build the /conversations router bound to the live server module."""
    router = APIRouter()

    @router.get("/conversations")
    async def get_conversations(principal=Depends(server.require_chat_access())):
        owner = principal["owner"]
        return {"conversations": server.list_conversations_summary(owner=owner)}

    @router.get("/conversations/{conversation_id}")
    async def get_conversation(conversation_id: str, principal=Depends(server.require_chat_access())):
        owner = principal["owner"]
        conversation = server._chat_store.get_conversation(conversation_id, owner)
        if conversation is None:
            raise HTTPException(status_code=404, detail="Conversation not found.")
        server.logger.info("[CONV] loaded id=%s", conversation_id)
        return conversation

    @router.post("/conversations")
    async def post_conversation(
        data: server.ConversationCreateRequest = Body(default_factory=server.ConversationCreateRequest),
        principal=Depends(server.require_chat_access()),
    ):
        owner = principal["owner"]
        user = principal.get("user")
        body = data or server.ConversationCreateRequest()
        tid = body.active_tenant_id if body.active_tenant_id is not None else server.DEFAULT_TENANT_ID
        server.assert_chat_tenant_allowed(user, tid)
        return server.create_conversation(
            title=body.title,
            owner=owner,
            active_tenant_id=tid,
        )

    @router.patch("/conversations/{conversation_id}/active-tenant")
    async def patch_conversation_active_tenant(
        conversation_id: str,
        data: server.ConversationActiveTenantRequest,
        principal=Depends(server.require_chat_access()),
    ):
        owner = principal["owner"]
        conv = server._chat_store.get_conversation(conversation_id, owner)
        if conv is None:
            raise HTTPException(status_code=404, detail="Conversation not found.")
        from_tid = conv.get("active_tenant_id")
        try:
            updated = server.set_conversation_active_tenant(
                conversation_id,
                data.active_tenant_id,
                owner=owner,
                from_tenant_id=from_tid,
                emit_system_message=True,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Conversation not found.") from exc
        new_tid = int(updated.get("active_tenant_id") or data.active_tenant_id)
        return {
            "conversation_id": conversation_id,
            "active_tenant_id": new_tid,
            "from_tenant_id": from_tid,
            "to_tenant_id": new_tid,
            "from_name": server.get_tenant_name(int(from_tid)) if from_tid is not None else None,
            "to_name": server.get_tenant_name(new_tid),
        }

    @router.patch("/conversations/{conversation_id}")
    async def patch_conversation(
        conversation_id: str,
        data: server.ConversationRenameRequest,
        principal=Depends(server.require_chat_access()),
    ):
        owner = principal["owner"]
        try:
            return server.rename_conversation(conversation_id, data.title, owner=owner)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Conversation not found.") from exc

    @router.delete("/conversations")
    async def delete_all_conversations_endpoint(principal=Depends(server.require_chat_access())):
        owner = principal["owner"]
        deleted_count = server.delete_all_conversations(owner=owner)
        return {"success": True, "deleted_count": deleted_count}

    @router.delete("/conversations/{conversation_id}")
    async def delete_conversation_endpoint(conversation_id: str, principal=Depends(server.require_chat_access())):
        owner = principal["owner"]
        try:
            server.delete_conversation(conversation_id, owner=owner)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Conversation not found.") from exc
        return {"success": True, "id": conversation_id}

    @router.post("/conversations/{conversation_id}/message")
    async def post_conversation_message(
        conversation_id: str,
        data: server.ConversationMessageRequest,
        principal=Depends(server.require_chat_access()),
    ):
        owner = principal["owner"]
        try:
            chat_tid = server._resolve_chat_tenant_id(data.tenant_id, conversation_id, owner)
            conversation = server.append_conversation_message(
                conversation_id, data.role, data.text, tenant_id=chat_tid, owner=owner
            )
        except HTTPException:
            raise
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Conversation not found.") from exc
        return conversation

    return router
