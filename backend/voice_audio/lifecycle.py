"""Startup/shutdown for voice STT/TTS subsystems."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

import aiohttp
import torch
from fastapi import FastAPI

from backend.voice_audio import config, state
from backend.voice_audio.stt.loader import (
    MULTILINGUAL_MODEL_PATH,
    load_multilingual_whisper_model_if_available,
    resolve_multilingual_model_path,
)
from backend.voice_audio.tts.client import xtts_synth_sem

logger = logging.getLogger("voice_audio.lifecycle")

try:
    from config import WHISPER_MODEL_PATH, WHISPER_MODEL_SIZE, WHISPER_DEVICE, WHISPER_COMPUTE_TYPE, WHISPER_BEAM_SIZE, WHISPER_VAD_FILTER
except Exception:
    from pathlib import Path
    WHISPER_MODEL_PATH = Path(__file__).resolve().parent.parent / "Models" / "faster-whisper-small"
    WHISPER_MODEL_SIZE = "small.en"
    WHISPER_DEVICE = "cpu"
    WHISPER_COMPUTE_TYPE = "int8"
    WHISPER_BEAM_SIZE = 1
    WHISPER_VAD_FILTER = True


async def init_voice_audio(app: FastAPI, *, safe_mode: bool = False, disable_warmup: bool = False) -> None:
    """Load Whisper, create TTS session, probe Piper."""
    if safe_mode:
        logger.warning("Safe mode: skipping voice audio initialization")
        return

    if not state.WHISPER_AVAILABLE:
        raise ImportError("CRITICAL: faster-whisper not installed")

    from faster_whisper import WhisperModel

    whisper_device = WHISPER_DEVICE
    whisper_compute = WHISPER_COMPUTE_TYPE
    if not torch.cuda.is_available() and whisper_device == "cuda":
        whisper_device = "cpu"
        whisper_compute = "int8"

    logger.info("Loading faster-whisper '%s' on %s...", WHISPER_MODEL_SIZE, whisper_device)
    if WHISPER_MODEL_PATH.exists():
        state.whisper_model = WhisperModel(
            str(WHISPER_MODEL_PATH),
            device=whisper_device,
            compute_type=whisper_compute,
            download_root=None,
        )
    else:
        WHISPER_MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        state.whisper_model = WhisperModel(
            WHISPER_MODEL_SIZE,
            device=whisper_device,
            compute_type=whisper_compute,
            download_root=str(WHISPER_MODEL_PATH.parent),
        )
    logger.info("faster-whisper loaded")

    tts_connector = aiohttp.TCPConnector(limit=4, limit_per_host=2, force_close=False, enable_cleanup_closed=True)
    state.tts_session = aiohttp.ClientSession(
        connector=tts_connector,
        timeout=aiohttp.ClientTimeout(total=None, sock_connect=5, sock_read=None),
        headers={"Connection": "keep-alive"},
    )

    if config.ASSISTIFY_DISABLE_TTS:
        state.xtts_model = None
        config.EFFECTIVE_DISABLE_TTS = True
    else:
        import json
        import urllib.request as _urllib_req
        try:
            req = _urllib_req.urlopen(f"{config.XTTS_SERVICE_URL}/health", timeout=5)
            health = json.loads(req.read().decode())
            if health.get("status") == "ok" and health.get("engine") == "piper" and health.get("ready"):
                state.xtts_model = True
                config.EFFECTIVE_DISABLE_TTS = False
            else:
                state.xtts_model = None
                config.EFFECTIVE_DISABLE_TTS = True
        except Exception as exc:
            logger.warning("Piper not reachable: %s", exc)
            state.xtts_model = None
            config.EFFECTIVE_DISABLE_TTS = True

    ml = resolve_multilingual_model_path()
    if ml:
        load_multilingual_whisper_model_if_available()
    else:
        logger.info("Multilingual Whisper not found at %s", MULTILINGUAL_MODEL_PATH)

    if not disable_warmup and not config.EFFECTIVE_DISABLE_WARMUP:
        asyncio.create_task(_warmup_tts())


async def _warmup_tts() -> None:
    await asyncio.sleep(10)
    if config.EFFECTIVE_DISABLE_TTS:
        return
    try:
        async with xtts_synth_sem:
            if state.tts_session and not state.tts_session.closed:
                async with state.tts_session.post(
                    f"{config.XTTS_SERVICE_URL}/synthesize",
                    json={"text": "warmup", "speaker": config.XTTS_SPEAKER, "language": config.XTTS_LANGUAGE},
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    if resp.status == 200:
                        await resp.read()
    except Exception as exc:
        logger.warning("TTS warmup failed: %s", exc)


async def shutdown_voice_audio() -> None:
    if state.tts_session and not state.tts_session.closed:
        await state.tts_session.close()
