"""Shared runtime state for voice STT/TTS."""
from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, Optional

import aiohttp

from backend.voice_audio.config import SAMPLE_RATE, XTTS_AVAILABLE  # noqa: F401

try:
    from faster_whisper import WhisperModel
    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False
    WhisperModel = None  # type: ignore[misc, assignment]

if TYPE_CHECKING:
    from faster_whisper import WhisperModel as _WhisperModel

voice_semaphore = asyncio.Semaphore(1)
interrupt_events: dict[str, asyncio.Event] = {}
ws_write_locks: dict[str, asyncio.Lock] = {}

llm_session: Optional[aiohttp.ClientSession] = None
tts_session: Optional[aiohttp.ClientSession] = None
whisper_model: Optional["WhisperModel"] = None
whisper_model_multilingual: Optional["WhisperModel"] = None
xtts_model: Any = None

arabic_ack_pcm: bytes = b""
arabic_offtopic_pcm: bytes = b""
arabic_opener_pcm: bytes = b""
arabic_opener_pool: dict[str, bytes] = {}

ws_tts_active_response_ids: dict[str, str] = {}
ws_tts_active_tasks: dict[str, asyncio.Task] = {}

arabic_download_task: asyncio.Task | None = None
arabic_download_status: dict[str, str] = {"state": "idle", "message": ""}
