"""Voice/LLM inference concurrency with user-visible backpressure."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

from fastapi import WebSocket

from backend.voice_audio import state

logger = logging.getLogger("voice_audio.concurrency")

BUSY_MESSAGE = (
    "The assistant is helping another user. Your request is queued — please wait."
)


@asynccontextmanager
async def voice_inference_slot(
    ws: Optional[WebSocket] = None,
    connection_id: str = "",
) -> AsyncIterator[None]:
    """
    Acquire the single voice/LLM slot. If another session holds it, notify the
    client before blocking so they know the system is busy (not frozen).
    """
    sem = state.voice_semaphore
    if sem.locked():
        logger.info("%s waiting for voice inference slot (busy)", connection_id or "ws")
        if ws is not None:
            try:
                await ws.send_json({
                    "type": "system_busy",
                    "message": BUSY_MESSAGE,
                    "voice_recoverable": True,
                })
            except Exception as exc:
                logger.debug("system_busy send failed: %s", exc)
    await sem.acquire()
    try:
        yield
    finally:
        sem.release()
