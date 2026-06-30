"""Whisper model loading."""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from backend.voice_audio import state

try:
    from config import WHISPER_MODEL_PATH, WHISPER_DEVICE, WHISPER_COMPUTE_TYPE
except Exception:
    WHISPER_MODEL_PATH = Path(__file__).resolve().parent.parent.parent / "Models" / "faster-whisper-small"
    WHISPER_DEVICE = "cpu"
    WHISPER_COMPUTE_TYPE = "int8"

logger = logging.getLogger("voice_audio.stt.loader")

MULTILINGUAL_MODEL_PATH = Path(WHISPER_MODEL_PATH).parent / "faster-whisper-small"


def resolve_multilingual_model_path() -> Path | None:
    """Return the best available multilingual Whisper model path, or None."""
    if MULTILINGUAL_MODEL_PATH.exists() and any(MULTILINGUAL_MODEL_PATH.iterdir()):
        return MULTILINGUAL_MODEL_PATH
    hf_snapshots = (
        MULTILINGUAL_MODEL_PATH.parent / "models--Systran--faster-whisper-small" / "snapshots"
    )
    if hf_snapshots.exists():
        snapshots = sorted(hf_snapshots.iterdir())
        if snapshots:
            return snapshots[-1]
    return None


def load_multilingual_whisper_model_if_available() -> bool:
    """Load the multilingual Whisper model for Arabic STT if it is available."""
    if state.whisper_model_multilingual is not None:
        return True
    if not state.WHISPER_AVAILABLE or state.WhisperModel is None:
        return False

    resolved_path = resolve_multilingual_model_path()
    if resolved_path is None:
        return False

    try:
        ml_device = WHISPER_DEVICE
        ml_compute = WHISPER_COMPUTE_TYPE
        ml_kwargs: dict[str, Any] = {
            "device": ml_device,
            "compute_type": ml_compute,
            "download_root": None,
        }
        if ml_device == "cpu":
            cpu_threads = int(os.getenv("WHISPER_CPU_THREADS", str(min(os.cpu_count() or 4, 8))))
            ml_kwargs.update({"cpu_threads": cpu_threads, "num_workers": 1})
        state.whisper_model_multilingual = state.WhisperModel(str(resolved_path), **ml_kwargs)
        logger.info(
            "Multilingual faster-whisper loaded for Arabic STT (path=%s, device=%s, compute=%s)",
            resolved_path,
            ml_device,
            ml_compute,
        )
        return True
    except Exception as exc:
        logger.warning(
            "Multilingual Whisper model is present but failed to load: %s",
            exc,
        )
        state.whisper_model_multilingual = None
        return False


def arabic_multilingual_model_ready() -> bool:
    if state.whisper_model_multilingual is not None:
        return True
    return resolve_multilingual_model_path() is not None
