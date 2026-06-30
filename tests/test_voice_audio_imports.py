"""Regression tests for voice_audio module import integrity."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

AUDIO_PIPELINE_PATH = (
    REPO_ROOT / "backend" / "voice_audio" / "ws" / "audio_pipeline.py"
)


def test_audio_pipeline_source_imports_cancel_active_ws_tts():
    """Ensure run_auto_transcribe can call cancel_active_ws_tts (regression for NameError)."""
    source = AUDIO_PIPELINE_PATH.read_text(encoding="utf-8")
    assert "from backend.voice_audio.tts.streaming import cancel_active_ws_tts" in source
    assert "cancel_active_ws_tts(conn_id" in source


def test_audio_pipeline_has_pipeline_error_handler():
    """Unexpected failures must notify the client instead of hanging on processing."""
    source = AUDIO_PIPELINE_PATH.read_text(encoding="utf-8")
    assert '"pipeline_error"' in source
    assert "client_notified" in source
    assert "memory_guard.active_voice_task = None" in source


def test_concurrency_voice_inference_slot_importable():
    mod = importlib.import_module("backend.voice_audio.concurrency")
    assert hasattr(mod, "voice_inference_slot")
