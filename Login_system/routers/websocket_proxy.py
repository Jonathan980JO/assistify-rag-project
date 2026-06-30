"""WebSocket proxy routes for the login system.

Extracted from ``login_server.py`` during the Phase 6 refactor.

HIGH RISK area: these endpoints bridge the browser's single-origin WebSocket to
the RAG server's ``/ws``. The message protocol, payloads, framing (text/binary),
auth, rate limiting, guest scoping and tenant behavior are preserved exactly.
Handler logic is byte-identical to the monolith; login_server-defined globals
(SESSION_COOKIE, serializer, RAG_WS_URL, WebSocketRateLimiter, log_security_event,
logger, _require_public_guest_chat) are read off the live server module passed
to the factory, which avoids an import cycle.

NOTE: module is named ``websocket_proxy`` (not ``ws_proxy``) because the repo
.gitignore ignores every ``ws_*`` path, which would leave a ``ws_proxy.py``
untracked.
"""
import asyncio
import json

import aiohttp
from fastapi import APIRouter, WebSocket

from Login_system import guest_session


def _is_voice_control_frame(text: str) -> bool:
    """Ping/control frames must not consume the text rate budget (voice + tunnels)."""
    try:
        payload = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return False
    if not isinstance(payload, dict):
        return False
    return payload.get("type") in ("ping", "pong", "control")


def build_ws_proxy_router(server) -> APIRouter:
    """Build the /ws and /ws/guest proxy router bound to the live server module."""
    router = APIRouter()

    @router.websocket("/ws")
    async def websocket_proxy(websocket: WebSocket):
        """Proxy a websocket connection from the browser (same-origin on the login server)
        to the backend RAG server websocket. This allows the frontend served from the
        login server to open a single-origin websocket while the actual voice/LLM
        processing runs on the RAG server.
        """
        await websocket.accept()

        token = websocket.cookies.get(server.SESSION_COOKIE)
        user = None
        if token:
            try:
                user = server.serializer.loads(token)
            except Exception:
                user = None

        if not user:
            server.log_security_event("websocket_unauthorized", {
                "client_ip": websocket.client.host if websocket.client else "unknown"
            }, severity="WARNING")
            await websocket.close(code=1008)
            return

        rate_limiter = server.WebSocketRateLimiter(max_messages=20, window_seconds=60)
        server.log_security_event("websocket_connected", {
            "username": user.get("username"),
            "role": user.get("role")
        })

        _ws_cookie = websocket.headers.get("cookie")
        _ws_fwd_headers = {"Cookie": _ws_cookie} if _ws_cookie else None
        await _bridge_rag_websocket(websocket, user, _ws_fwd_headers, rate_limiter)

    @router.websocket("/ws/guest")
    async def guest_websocket_proxy(websocket: WebSocket):
        """Public customer chat websocket (no login; scoped by guest_id cookie)."""
        await websocket.accept()
        server._require_public_guest_chat()

        guest_id = guest_session.get_guest_id(websocket)
        if not guest_id:
            await websocket.close(code=1008)
            return

        user = {"username": guest_id, "role": "guest"}
        rate_limiter = server.WebSocketRateLimiter(max_messages=20, window_seconds=60)
        server.log_security_event("guest_websocket_connected", {
            "guest_id": guest_id,
            "client_ip": websocket.client.host if websocket.client else "unknown",
        })

        fwd_headers = guest_session.guest_rag_headers(websocket, guest_id)
        await _bridge_rag_websocket(websocket, user, fwd_headers, rate_limiter)

    async def _bridge_rag_websocket(websocket: WebSocket, user, fwd_headers, rate_limiter):
        """Bridge browser websocket to RAG /ws with optional forwarded headers."""
        try:
            async with aiohttp.ClientSession() as session:
                backend_ws = None
                max_attempts = 5
                for attempt in range(1, max_attempts + 1):
                    try:
                        backend_ws = await session.ws_connect(
                            server.RAG_WS_URL,
                            headers=fwd_headers,
                            timeout=aiohttp.ClientTimeout(total=300, sock_connect=30),
                            heartbeat=25,
                            autoping=True,
                            max_msg_size=0,
                        )
                        break
                    except Exception as e:
                        logger = getattr(server, 'logger', None)
                        msg = f"Attempt {attempt}/{max_attempts} failed connecting to RAG ws: {e}"
                        if logger:
                            logger.warning(msg)
                        else:
                            print(msg)
                        if attempt < max_attempts:
                            await asyncio.sleep(0.6 * attempt)
                        else:
                            raise
                if backend_ws is None:
                    raise RuntimeError("Failed to establish backend websocket")
                async with backend_ws:
                    try:
                        await backend_ws.send_json({"type": "auth", "user": user})
                    except Exception:
                        pass

                    async def forward_client_to_backend():
                        try:
                            while True:
                                data = await websocket.receive()
                                if "text" in data:
                                    text = data["text"]
                                    if not _is_voice_control_frame(text) and not rate_limiter.is_allowed():
                                        remaining = rate_limiter.get_remaining_time()
                                        server.log_security_event("websocket_rate_limit", {
                                            "username": user.get("username"),
                                            "remaining_seconds": remaining
                                        }, severity="WARNING")
                                        await websocket.send_json({
                                            "error": f"Rate limit exceeded. Please slow down. Try again in {remaining}s."
                                        })
                                        continue
                                    await backend_ws.send_str(text)
                                elif "bytes" in data:
                                    await backend_ws.send_bytes(data["bytes"])
                                elif data.get("type") == "websocket.disconnect":
                                    await backend_ws.close()
                                    break
                        except Exception:
                            try:
                                await websocket.send_json({
                                    "type": "error",
                                    "message": "Voice connection lost.",
                                    "voice_recoverable": True,
                                })
                            except Exception:
                                pass
                            try:
                                await backend_ws.close()
                            except Exception:
                                pass

                    async def forward_backend_to_client():
                        try:
                            async for msg in backend_ws:
                                if msg.type == aiohttp.WSMsgType.TEXT:
                                    await websocket.send_text(msg.data)
                                elif msg.type == aiohttp.WSMsgType.BINARY:
                                    await websocket.send_bytes(msg.data)
                                elif msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED):
                                    await websocket.close(code=1000)
                                    break
                        except Exception:
                            try:
                                await websocket.send_json({
                                    "type": "error",
                                    "message": "Voice connection lost.",
                                    "voice_recoverable": True,
                                })
                            except Exception:
                                pass
                            try:
                                await websocket.close(code=1000)
                            except Exception:
                                pass

                    await asyncio.gather(
                        forward_client_to_backend(),
                        forward_backend_to_client(),
                    )
        except Exception as e:
            server.logger.error(f"Websocket proxy error: {e}")
            try:
                await websocket.send_json({
                    "type": "error",
                    "message": "Voice connection lost.",
                    "voice_recoverable": True,
                })
            except Exception:
                pass
            try:
                await websocket.close(code=1011)
            except Exception:
                pass

    return router
