"""System/infrastructure routes for the login system.

Extracted from ``login_server.py`` during the Phase 4 refactor.

These handlers read live server module state (FAVICON_PATH, RAG_WS_URL). To keep
behavior byte-identical and avoid an import cycle with the server module, the
router is built by a factory that receives the live server module and reads
those attributes at request time. Paths, methods, schema visibility and
response bodies are unchanged.
"""
from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, Response


def build_system_router(server) -> APIRouter:
    """Build the favicon + RAG-WS health-check router bound to the live server module."""
    router = APIRouter()

    def get_server():
        """Dependency provider for the live server module (Phase 5 DI)."""
        return server

    @router.get("/favicon.ico", include_in_schema=False)
    def favicon(srv=Depends(get_server)):
        if srv.FAVICON_PATH.is_file():
            return FileResponse(str(srv.FAVICON_PATH), media_type="image/x-icon")
        return Response(status_code=204)

    @router.get("/internal/check_rag_ws")
    async def internal_check_rag_ws(srv=Depends(get_server)):
        """Lightweight endpoint to check whether the login server can connect to the
        RAG server websocket. Returns JSON with status and any exception text.
        """
        try:
            import aiohttp
            timeout = aiohttp.ClientTimeout(total=3)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.ws_connect(srv.RAG_WS_URL) as ws:
                    # send a ping and await pong/close
                    await ws.send_json({"type": "ping"})
                    try:
                        msg = await ws.receive(timeout=2)
                        return {"ok": True, "backend_msg_type": getattr(msg, 'type', str(type(msg)))}
                    except Exception as e:
                        return {"ok": True, "note": "connected but no immediate response", "detail": str(e)}
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            return {"ok": False, "error": str(e), "trace": tb}

    @router.get("/api/public-tunnel")
    def public_tunnel_info():
        """Expose active --public tunnel URL for the local login-page QR code."""
        try:
            from scripts.public_tunnel import read_public_tunnel_url

            data = read_public_tunnel_url()
        except Exception:
            data = None
        if not data:
            return {"active": False}
        base = str(data.get("url") or "").rstrip("/")
        if not base:
            return {"active": False}
        guest_chat_url = f"{base}/frontend/guest/"
        return {
            "active": True,
            "url": base,
            "login_url": f"{base}/login",
            "guest_chat_url": guest_chat_url,
            "provider": data.get("provider"),
        }

    return router
