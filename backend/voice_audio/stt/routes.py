"""STT-related HTTP routes."""
from __future__ import annotations

import asyncio
import logging
from typing import Callable

import torch
from fastapi import APIRouter, Depends

from backend.voice_audio import config, state
from backend.voice_audio.stt.loader import (
    MULTILINGUAL_MODEL_PATH,
    arabic_multilingual_model_ready,
    load_multilingual_whisper_model_if_available,
)

logger = logging.getLogger("voice_audio.stt.routes")
router = APIRouter(tags=["voice-stt"])


def register_stt_routes(app_router: APIRouter, require_login: Callable) -> None:
    @app_router.get("/arabic/status")
    async def arabic_status(user=Depends(require_login())):
        model_on_disk = MULTILINGUAL_MODEL_PATH.exists() or arabic_multilingual_model_ready()
        model_loaded = state.whisper_model_multilingual is not None
        return {
            "multilingual_model_ready": model_on_disk or model_loaded,
            "multilingual_model_loaded": model_loaded,
            "multilingual_model_on_disk": model_on_disk,
            "xtts_arabic_ready": state.xtts_model is not None,
            "download_state": state.arabic_download_status.get("state", "idle"),
            "download_message": state.arabic_download_status.get("message", ""),
            "model_path": str(MULTILINGUAL_MODEL_PATH),
        }

    @app_router.post("/arabic/download")
    async def arabic_download_models(user=Depends(require_login())):
        if arabic_multilingual_model_ready():
            return {"status": "already_ready", "message": "Multilingual model already present."}
        if state.arabic_download_task and not state.arabic_download_task.done():
            return {"status": "downloading", "message": "Download already in progress."}

        async def _do_download():
            state.arabic_download_status = {"state": "downloading", "message": "Downloading..."}
            dest = MULTILINGUAL_MODEL_PATH
            dest.mkdir(parents=True, exist_ok=True)
            try:
                from faster_whisper import WhisperModel
                from config import WHISPER_DEVICE, WHISPER_COMPUTE_TYPE
                import os
                dl_kwargs = {"device": WHISPER_DEVICE, "compute_type": WHISPER_COMPUTE_TYPE, "download_root": str(dest.parent)}
                if WHISPER_DEVICE == "cpu":
                    dl_kwargs.update({"cpu_threads": int(os.getenv("WHISPER_CPU_THREADS", "4")), "num_workers": 1})
                state.whisper_model_multilingual = WhisperModel("small", **dl_kwargs)
                state.arabic_download_status = {"state": "ready", "message": "Multilingual model ready."}
            except Exception as exc:
                state.arabic_download_status = {"state": "error", "message": str(exc)}

        state.arabic_download_task = asyncio.create_task(_do_download())
        return {"status": "downloading", "message": "Download started in background."}

    @app_router.get("/internal/asr-status")
    def asr_status():
        try:
            from config import WHISPER_MODEL_SIZE, WHISPER_DEVICE, WHISPER_COMPUTE_TYPE, WHISPER_BEAM_SIZE, WHISPER_VAD_FILTER
        except Exception:
            WHISPER_MODEL_SIZE = "tiny.en"
            WHISPER_DEVICE = "cpu"
            WHISPER_COMPUTE_TYPE = "int8"
            WHISPER_BEAM_SIZE = 1
            WHISPER_VAD_FILTER = True
        return {
            "engine": "faster-whisper",
            "model_size": WHISPER_MODEL_SIZE,
            "device": WHISPER_DEVICE,
            "compute_type": WHISPER_COMPUTE_TYPE,
            "beam_size": WHISPER_BEAM_SIZE,
            "vad_enabled": WHISPER_VAD_FILTER,
            "sample_rate": config.SAMPLE_RATE,
            "model_loaded": state.whisper_model is not None,
            "gpu_available": torch.cuda.is_available() if state.WHISPER_AVAILABLE else False,
        }
