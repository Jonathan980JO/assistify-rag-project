#!/usr/bin/env python3
"""One-time Phase 1 extractor: voice_audio package from assistify_rag_server.py."""
from __future__ import annotations

import re
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "backend" / "assistify_rag_server.py"
VOICE = ROOT / "backend" / "voice_audio"


def read_lines() -> list[str]:
    return SRC.read_text(encoding="utf-8").splitlines(keepends=True)


def slice_lines(lines: list[str], start: int, end: int) -> str:
    return "".join(lines[start - 1 : end])


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"  wrote {path.relative_to(ROOT)} ({len(content.splitlines())} lines)")


def main() -> None:
    lines = read_lines()
    print(f"Source: {len(lines)} lines")

    # --- scaffold ---
    write(VOICE / "deps.py", textwrap.dedent('''\
        """Dependency injection for WebSocket voice handler (avoids circular imports)."""
        from __future__ import annotations

        from dataclasses import dataclass
        from typing import Any, Awaitable, Callable, Optional

        from fastapi import WebSocket


        @dataclass
        class VoiceWebSocketDeps:
            """Callbacks implemented by assistify_rag_server for RAG routing."""

            resolve_request_tenant: Callable[[Any], int]
            coerce_owner: Callable[[Any], Optional[str]]
            get_or_create_conversation: Callable
            bind_conversation_memory: Callable
            append_conversation_message: Callable
            persist_runtime_memory: Callable
            send_final_response: Callable
            process_voice_transcript: Callable
            process_text_message: Callable
            emit_perf_report: Optional[Callable] = None
            session_cookie: str = "session"
            serializer: Any = None
            set_request_tenant_id: Optional[Callable[[int], None]] = None
            get_memory_snapshot: Callable = lambda: {"gpu_reserved_mb": 0, "gpu_allocated_mb": 0, "cpu_rss_mb": 0}
            get_stable_memory_snapshot: Callable = None
            on_ws_connect: Optional[Callable] = None
            on_ws_disconnect: Optional[Callable] = None
            conversation_history: Any = None
            conversation_timestamps: Any = None
            active_ws_connections: Any = None
    '''))

    write(VOICE / "config.py", textwrap.dedent('''\
        """Voice/STT/TTS configuration flags."""
        from __future__ import annotations

        import os


        def _env_flag_enabled(name: str, default: bool = False) -> bool:
            raw = os.environ.get(name)
            if raw is None:
                return default
            return str(raw).strip().lower() in {"1", "true", "yes", "on"}


        SAMPLE_RATE = 16000

        XTTS_SERVICE_URL = os.environ.get("XTTS_SERVICE_URL", "http://127.0.0.1:5002")
        XTTS_SPEAKER = "Claribel Dervla"
        XTTS_LANGUAGE = "en"
        XTTS_SAMPLE_RATE = 24000
        XTTS_MODEL_NAME = "tts_models/multilingual/multi-dataset/xtts_v2"
        XTTS_AVAILABLE = True

        ASSISTIFY_DISABLE_TTS: bool = _env_flag_enabled("ASSISTIFY_DISABLE_TTS", default=False)
        ASSISTIFY_DISABLE_WHISPER: bool = _env_flag_enabled("ASSISTIFY_DISABLE_WHISPER", default=False)
        ASSISTIFY_DISABLE_WARMUP: bool = _env_flag_enabled("ASSISTIFY_DISABLE_WARMUP", default=False)
        ASSISTIFY_ENABLE_ENGLISH_TTS_WARMUP: bool = _env_flag_enabled("ASSISTIFY_ENABLE_ENGLISH_TTS_WARMUP", default=False)
        ASSISTIFY_ENABLE_ARABIC_TTS_WARMUP: bool = _env_flag_enabled("ASSISTIFY_ENABLE_ARABIC_TTS_WARMUP", default=False)
        ASSISTIFY_ENABLE_TTS_OPENER_WARMUP: bool = _env_flag_enabled("ASSISTIFY_ENABLE_TTS_OPENER_WARMUP", default=False)

        EFFECTIVE_DISABLE_TTS = ASSISTIFY_DISABLE_TTS
        EFFECTIVE_DISABLE_WHISPER = ASSISTIFY_DISABLE_WHISPER
        EFFECTIVE_DISABLE_WARMUP = ASSISTIFY_DISABLE_WARMUP

        VOICE_MIN_TRANSCRIBE_BYTES = 48000
    '''))

    write(VOICE / "memory_guard.py", textwrap.dedent('''\
        """Voice session memory-leak detection globals."""
        from __future__ import annotations

        import asyncio

        SAFE_UNBLOCK_CPU_MB = 2000
        SAFE_UNBLOCK_GPU_MB = 2000
        GPU_GROWTH_DELTA_MB = 200
        GPU_HIGH_WATER_MB = 4000
        MEMORY_GROWTH_LIMIT = 3
        CPU_GROWTH_DELTA_MB = 500
        CPU_HIGH_WATER_MB = 4000

        pipeline_run_count = 0
        sessions_blocked = False
        sessions_blocked_since = 0.0
        consecutive_gpu_growth = 0
        consecutive_cpu_growth = 0
        last_gpu_reserved_mb = 0

        active_voice_task: asyncio.Task | None = None
        active_voice_conn_id: str | None = None


        def voice_transcribe_in_flight(conn_id: str | None = None) -> bool:
            if active_voice_task is None or active_voice_task.done():
                return False
            if conn_id is not None and active_voice_conn_id != conn_id:
                return False
            return True


        def assign_voice_transcribe_task(task: asyncio.Task, conn_id: str) -> None:
            global active_voice_task, active_voice_conn_id
            active_voice_task = task
            active_voice_conn_id = conn_id
    '''))

    write(VOICE / "state.py", textwrap.dedent('''\
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
    '''))

    # Extract raw blocks from source
    stt_helpers = slice_lines(lines, 21440, 21513)
    tts_text_block = slice_lines(lines, 35993, 36119) + slice_lines(lines, 8840, 8896) + slice_lines(lines, 36060, 36119)
    tts_streaming = slice_lines(lines, 36122, 36729)
    tts_client = slice_lines(lines, 43182, 43293)
    tts_route = slice_lines(lines, 43295, 43386)
    whisper_loader = slice_lines(lines, 6865, 6915)
    arabic_routes = slice_lines(lines, 41977, 42046)
    asr_route = slice_lines(lines, 44562, 44575)
    capture_cls = slice_lines(lines, 908, 937)
    ws_full = slice_lines(lines, 43390, 44490)
    auto_transcribe = slice_lines(lines, 43457, 43896)

    # --- stt/transcribe.py helpers ---
    stt_transcribe_body = slice_lines(lines, 43561, 43692)
    write(
        VOICE / "stt" / "__init__.py",
        'from backend.voice_audio.stt.transcribe import TranscriptionResult, run_transcription\n'
        'from backend.voice_audio.stt.loader import (\n'
        '    load_multilingual_whisper_model_if_available,\n'
        '    resolve_multilingual_model_path,\n'
        '    MULTILINGUAL_MODEL_PATH,\n'
        ')\n',
    )

    write(
        VOICE / "stt" / "transcribe.py",
        textwrap.dedent('''\
            """faster-whisper transcription."""
            from __future__ import annotations

            import asyncio
            import logging
            import re
            from pathlib import Path
            from typing import Any, NamedTuple

            import numpy as np

            from backend.voice_audio.config import EFFECTIVE_DISABLE_WHISPER
            from backend.voice_audio import state
            from backend.voice_audio.stt.loader import load_multilingual_whisper_model_if_available

            try:
                from config import (
                    WHISPER_MODEL_PATH,
                    WHISPER_MODEL_SIZE,
                    WHISPER_DEVICE,
                    WHISPER_COMPUTE_TYPE,
                    WHISPER_BEAM_SIZE,
                    WHISPER_VAD_FILTER,
                )
            except Exception:
                from pathlib import Path as _P
                WHISPER_MODEL_PATH = _P(__file__).resolve().parent.parent.parent / "Models" / "faster-whisper-tiny.en"
                WHISPER_MODEL_SIZE = "tiny.en"
                WHISPER_DEVICE = "cpu"
                WHISPER_COMPUTE_TYPE = "int8"
                WHISPER_BEAM_SIZE = 1
                WHISPER_VAD_FILTER = True

            logger = logging.getLogger("voice_audio.stt")

            ARABIC_STT_INITIAL_PROMPT: str | None = None

        ''') + stt_helpers + "\n\nclass TranscriptionResult(NamedTuple):\n    text: str\n    segments: list\n    model_label: str\n    transcribe_lang: str\n    retry_count: int\n\n\n" + textwrap.dedent('''\
            def _run_stt_sync(pcm16: np.ndarray, attempt_lang: str):
                from faster_whisper import WhisperModel

                attempt_lang = str(attempt_lang or "en").strip().lower()
                if attempt_lang == "ar":
                    if not load_multilingual_whisper_model_if_available() or state.whisper_model_multilingual is None:
                        raise RuntimeError(
                            "Arabic STT requires the multilingual Whisper model; English-only fallback is disabled."
                        )
                    model = state.whisper_model_multilingual
                    stt_lang = "ar"
                    model_label = "multilingual:ar"
                else:
                    if state.whisper_model is None and state.WHISPER_AVAILABLE:
                        logger.info("Lazy-loading Whisper model for voice endpoint...")
                        try:
                            state.whisper_model = WhisperModel(
                                str(WHISPER_MODEL_PATH) if WHISPER_MODEL_PATH.exists() else WHISPER_MODEL_SIZE,
                                device=WHISPER_DEVICE,
                                compute_type=WHISPER_COMPUTE_TYPE,
                                download_root=None if WHISPER_MODEL_PATH.exists() else str(WHISPER_MODEL_PATH.parent),
                            )
                        except Exception as exc:
                            logger.error("Failed to lazy-load Whisper model: %s", exc)
                    model = state.whisper_model
                    stt_lang = "en"
                    model_label = "english:en"

                if model is None:
                    raise RuntimeError("STT Model could not be loaded or is unavailable.")

                beam = 5 if attempt_lang == "ar" else WHISPER_BEAM_SIZE
                initial_prompt = ARABIC_STT_INITIAL_PROMPT if attempt_lang == "ar" else None
                segs_gen, info = model.transcribe(
                    pcm16,
                    language=stt_lang,
                    beam_size=beam,
                    temperature=0.0,
                    vad_filter=WHISPER_VAD_FILTER,
                    vad_parameters=dict(min_silence_duration_ms=300, threshold=0.3),
                    condition_on_previous_text=False,
                    compression_ratio_threshold=2.4,
                    log_prob_threshold=-1.0,
                    no_speech_threshold=0.8,
                    word_timestamps=False,
                    without_timestamps=True,
                    initial_prompt=initial_prompt,
                )
                return list(segs_gen), info, model_label, stt_lang


            async def run_transcription(pcm_bytes: bytes, lang: str = "en", timeout: float = 10.0) -> TranscriptionResult:
                requested = str(lang or "en").strip().lower()
                if requested not in {"en", "ar"}:
                    requested = "en"
                pcm16 = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
                retry_count = 0
                arabic_mode = requested == "ar"

                async def _attempt(attempt_lang: str):
                    loop = asyncio.get_event_loop()
                    return await asyncio.wait_for(
                        loop.run_in_executor(None, _run_stt_sync, pcm16, attempt_lang),
                        timeout=timeout,
                    )

                segments_list, _info, model_label, transcribe_lang = await _attempt(requested)
                full_text = " ".join([seg.text.strip() for seg in segments_list]).strip()

                if arabic_mode and _looks_like_english_stt_garbage_for_arabic(full_text, segments_list):
                    retry_count += 1
                    segments_list, _info, model_label, transcribe_lang = await _attempt("ar")
                    full_text = " ".join([seg.text.strip() for seg in segments_list]).strip()

                return TranscriptionResult(
                    text=full_text,
                    segments=segments_list,
                    model_label=model_label,
                    transcribe_lang=transcribe_lang,
                    retry_count=retry_count,
                )
        '''),
    )

    write(
        VOICE / "stt" / "loader.py",
        textwrap.dedent('''\
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
                WHISPER_MODEL_PATH = Path(__file__).resolve().parent.parent.parent / "Models" / "faster-whisper-tiny.en"
                WHISPER_DEVICE = "cpu"
                WHISPER_COMPUTE_TYPE = "int8"

            logger = logging.getLogger("voice_audio.stt.loader")

            MULTILINGUAL_MODEL_PATH = Path(WHISPER_MODEL_PATH).parent / "faster-whisper-small"

        ''') + whisper_loader,
    )

    # Fix loader to use state module
    loader_path = VOICE / "stt" / "loader.py"
    loader_text = loader_path.read_text(encoding="utf-8")
    loader_text = loader_text.replace("global whisper_model_multilingual", "global state.whisper_model_multilingual")
    loader_text = loader_text.replace("whisper_model_multilingual", "state.whisper_model_multilingual")
    loader_text = loader_text.replace("if not WHISPER_AVAILABLE or WhisperModel is None", "if not state.WHISPER_AVAILABLE or state.WhisperModel is None")
    loader_text = loader_text.replace("WhisperModel(str(resolved_path)", "state.WhisperModel(str(resolved_path)")
    loader_path.write_text(loader_text, encoding="utf-8")

    print("  patched stt/loader.py")

    print("Phase 1 scaffold + stt partial done. Run part 2 for tts/ws/main patch.")


if __name__ == "__main__":
    main()
