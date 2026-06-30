"""WebSocket wrapper that persists assistant messages."""
from __future__ import annotations

from typing import Callable

from fastapi import WebSocket


class ConversationCaptureWebSocket:
    def __init__(
        self,
        websocket: WebSocket,
        conversation_id: str,
        runtime_id: str,
        append_message: Callable,
        persist_memory: Callable,
    ):
        self._websocket = websocket
        self._conversation_id = conversation_id
        self._runtime_id = runtime_id
        self._assistant_saved = False
        self._append = append_message
        self._persist = persist_memory

    async def send_json(self, payload):
        if isinstance(payload, dict):
            payload.setdefault("conversation_id", self._conversation_id)
        await self._websocket.send_json(payload)
        if (
            isinstance(payload, dict)
            and payload.get("type") == "aiResponseDone"
            and not self._assistant_saved
        ):
            assistant_text = str(payload.get("fullText") or payload.get("text") or "").strip()
            if assistant_text:
                try:
                    self._append(self._conversation_id, "assistant", assistant_text)
                    self._assistant_saved = True
                except Exception:
                    pass
            self._persist(self._runtime_id, self._conversation_id)

    async def send_bytes(self, data):
        await self._websocket.send_bytes(data)

    def __getattr__(self, name: str):
        return getattr(self._websocket, name)
