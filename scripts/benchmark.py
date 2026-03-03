"""
═══════════════════════════════════════════════════════════════════
  Assistify Ultimate System Benchmark
═══════════════════════════════════════════════════════════════════

Measures *every* component in the pipeline end-to-end so you can see
exactly where time is spent and what settings suit your hardware.

Components tested:
  1. GPU / CPU hardware detection
  2. Ollama LLM inference (first-token, full-response)
  3. XTTS v2 synthesis (first-chunk, total, real-time factor)
  4. faster-whisper STT (transcription speed)
  5. ChromaDB RAG search (embedding + similarity)
  6. Full pipeline simulation (STT→RAG→LLM→TTS)

Usage:
  cd G:\\Grad_Project\\assistify-rag-project-main
  python scripts/benchmark.py

Prerequisites:
  - Ollama running  (ollama serve)
  - XTTS running    (start_xtts_service.bat)
  - RAG server NOT required (we import directly)

The script prints a final report with recommended settings.
"""

import asyncio
import io
import json
import os
import struct
import sys
import time
import wave
from pathlib import Path

# ── Make sure project root is on sys.path ──
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

import numpy as np

# ── Optional imports (graceful degrade) ──
try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False

try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False


# ═══════════════════════════════════════════════════════════════
# 1. Hardware Detection
# ═══════════════════════════════════════════════════════════════

def detect_hardware() -> dict:
    """Gather CPU, RAM, GPU info."""
    info = {
        "cpu_name": "N/A",
        "cpu_cores": os.cpu_count(),
        "ram_total_gb": 0,
        "gpu_name": "N/A",
        "gpu_vram_total_mb": 0,
        "gpu_vram_free_mb": 0,
        "cuda_available": False,
    }

    if PSUTIL_AVAILABLE:
        info["ram_total_gb"] = round(psutil.virtual_memory().total / 1024**3, 1)
        import platform
        info["cpu_name"] = platform.processor() or "N/A"

    if TORCH_AVAILABLE and torch.cuda.is_available():
        info["cuda_available"] = True
        info["gpu_name"] = torch.cuda.get_device_name(0)
        props = torch.cuda.get_device_properties(0)
        info["gpu_vram_total_mb"] = round(props.total_memory / 1024**2)
        info["gpu_vram_free_mb"] = round(
            (props.total_memory - torch.cuda.memory_reserved(0)) / 1024**2
        )

    return info


# ═══════════════════════════════════════════════════════════════
# 2. Ollama LLM Benchmark
# ═══════════════════════════════════════════════════════════════

async def bench_ollama(model: str = "qwen2.5:3b", host: str = "127.0.0.1",
                       port: int = 11434, runs: int = 3) -> dict:
    """Measure Ollama first-token and full-response latency."""
    url = f"http://{host}:{port}/api/chat"
    results = {"first_token_ms": [], "full_response_ms": [], "tokens_per_sec": [], "error": None}

    prompts = [
        "Say hello in one sentence.",
        "What is 2+2? Answer in one word.",
        "Name one color.",
    ]

    try:
        async with aiohttp.ClientSession() as session:
            for i in range(min(runs, len(prompts))):
                payload = {
                    "model": model,
                    "messages": [{"role": "user", "content": prompts[i]}],
                    "stream": True,
                    "options": {"num_ctx": 512, "temperature": 0.0, "num_predict": 30},
                }

                t_start = time.perf_counter()
                first_token_time = None
                token_count = 0

                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    if resp.status != 200:
                        results["error"] = f"HTTP {resp.status}"
                        break
                    async for line in resp.content:
                        chunk = json.loads(line)
                        if chunk.get("message", {}).get("content"):
                            token_count += 1
                            if first_token_time is None:
                                first_token_time = time.perf_counter()

                t_end = time.perf_counter()
                if first_token_time:
                    results["first_token_ms"].append((first_token_time - t_start) * 1000)
                    elapsed = t_end - t_start
                    results["full_response_ms"].append(elapsed * 1000)
                    if elapsed > 0:
                        results["tokens_per_sec"].append(token_count / elapsed)
    except Exception as e:
        results["error"] = str(e)

    return results


# ═══════════════════════════════════════════════════════════════
# 3. XTTS TTS Benchmark
# ═══════════════════════════════════════════════════════════════

async def bench_xtts(xtts_url: str = "http://127.0.0.1:5002", runs: int = 3) -> dict:
    """Measure XTTS synthesis time for different text lengths."""
    results = {
        "short": {"text": "Hello there.", "first_byte_ms": [], "total_ms": [], "audio_sec": []},
        "medium": {"text": "The quick brown fox jumps over the lazy dog near the river bank.", "first_byte_ms": [], "total_ms": [], "audio_sec": []},
        "long": {"text": "Artificial intelligence has transformed many aspects of modern life, from healthcare to education, and continues to evolve rapidly with new breakthroughs in natural language processing and computer vision.", "first_byte_ms": [], "total_ms": [], "audio_sec": []},
        "error": None,
    }

    try:
        async with aiohttp.ClientSession() as session:
            # Check health first
            async with session.get(f"{xtts_url}/health", timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status != 200:
                    results["error"] = f"XTTS health check failed: HTTP {resp.status}"
                    return results
                health = await resp.json()
                results["gpu_name"] = health.get("gpu", "N/A")
                results["vram_mb"] = health.get("vram_used_mb", 0)

            for key in ["short", "medium", "long"]:
                text = results[key]["text"]
                for _ in range(runs):
                    t_start = time.perf_counter()
                    first_byte_time = None
                    audio_data = b""

                    async with session.post(
                        f"{xtts_url}/synthesize",
                        json={"text": text, "speaker": "Claribel Dervla", "language": "en"},
                        timeout=aiohttp.ClientTimeout(total=60),
                    ) as resp:
                        if resp.status != 200:
                            results["error"] = f"Synthesis failed: HTTP {resp.status}"
                            return results
                        async for chunk in resp.content.iter_chunked(4096):
                            if first_byte_time is None:
                                first_byte_time = time.perf_counter()
                            audio_data += chunk

                    t_end = time.perf_counter()

                    if first_byte_time:
                        results[key]["first_byte_ms"].append((first_byte_time - t_start) * 1000)
                    results[key]["total_ms"].append((t_end - t_start) * 1000)

                    # Calculate audio duration from WAV
                    if len(audio_data) > 44:
                        audio_sec = (len(audio_data) - 44) / (24000 * 2)  # 24kHz, 16-bit
                        results[key]["audio_sec"].append(audio_sec)

    except Exception as e:
        results["error"] = str(e)

    return results


# ═══════════════════════════════════════════════════════════════
# 4. faster-whisper STT Benchmark
# ═══════════════════════════════════════════════════════════════

def bench_whisper(runs: int = 3) -> dict:
    """Measure STT speed by synthesizing a test tone and transcribing it."""
    results = {"transcribe_ms": [], "model_info": {}, "error": None}

    try:
        from config import WHISPER_MODEL_PATH, WHISPER_MODEL_SIZE, WHISPER_DEVICE, WHISPER_COMPUTE_TYPE, WHISPER_BEAM_SIZE
        from faster_whisper import WhisperModel

        # Load model
        t_load_start = time.perf_counter()
        if WHISPER_MODEL_PATH.exists():
            model = WhisperModel(str(WHISPER_MODEL_PATH), device=WHISPER_DEVICE, compute_type=WHISPER_COMPUTE_TYPE)
        else:
            model = WhisperModel(WHISPER_MODEL_SIZE, device=WHISPER_DEVICE, compute_type=WHISPER_COMPUTE_TYPE)
        t_load_end = time.perf_counter()

        results["model_info"] = {
            "model": WHISPER_MODEL_SIZE,
            "device": WHISPER_DEVICE,
            "compute_type": WHISPER_COMPUTE_TYPE,
            "beam_size": WHISPER_BEAM_SIZE,
            "load_time_ms": round((t_load_end - t_load_start) * 1000),
        }

        # Generate test audio: 3 seconds of 440Hz tone (simulates speech energy)
        sr = 16000
        duration = 3.0
        t = np.linspace(0, duration, int(sr * duration), dtype=np.float32)
        tone = 0.3 * np.sin(2 * np.pi * 440 * t)
        # Add some noise to make it more speech-like
        tone += np.random.normal(0, 0.02, len(tone)).astype(np.float32)

        for _ in range(runs):
            t_start = time.perf_counter()
            segments, info = model.transcribe(
                tone, language="en", beam_size=WHISPER_BEAM_SIZE,
                vad_filter=True, vad_parameters=dict(threshold=0.3, min_silence_duration_ms=300),
            )
            _ = list(segments)  # force evaluation
            t_end = time.perf_counter()
            results["transcribe_ms"].append((t_end - t_start) * 1000)

        del model

    except Exception as e:
        results["error"] = str(e)

    return results


# ═══════════════════════════════════════════════════════════════
# 5. ChromaDB RAG Search Benchmark
# ═══════════════════════════════════════════════════════════════

def bench_chromadb(runs: int = 5) -> dict:
    """Measure embedding + similarity search time."""
    results = {"search_ms": [], "doc_count": 0, "error": None}

    try:
        from backend.knowledge_base import search_documents, get_or_create_collection
        from sentence_transformers import SentenceTransformer

        collection = get_or_create_collection()
        results["doc_count"] = collection.count() if collection else 0

        queries = [
            "say my name", "best player in the world",
            "how to reset password", "what is machine learning",
            "tell me a joke",
        ]

        for i in range(min(runs, len(queries))):
            t_start = time.perf_counter()
            _ = search_documents(queries[i])
            t_end = time.perf_counter()
            results["search_ms"].append((t_end - t_start) * 1000)

    except Exception as e:
        results["error"] = str(e)

    return results


# ═══════════════════════════════════════════════════════════════
# 6. Full Pipeline Simulation
# ═══════════════════════════════════════════════════════════════

async def bench_full_pipeline(xtts_url: str = "http://127.0.0.1:5002",
                              ollama_model: str = "qwen2.5:3b") -> dict:
    """Simulate the full voice pipeline: RAG search → LLM → TTS."""
    results = {"stages": {}, "total_ms": 0, "error": None}

    query = "Tell me about the say my name scene"

    try:
        t_total_start = time.perf_counter()

        # Stage 1: RAG search
        t = time.perf_counter()
        from backend.knowledge_base import search_documents
        docs = search_documents(query)
        results["stages"]["rag_search_ms"] = round((time.perf_counter() - t) * 1000)
        results["stages"]["rag_docs_found"] = len(docs)

        # Stage 2: LLM (first sentence)
        context = docs[0][:500] if docs else ""
        system_prompt = f"Answer based on this context: {context}" if context else "Answer briefly."

        t = time.perf_counter()
        first_token_t = None
        full_response = ""

        async with aiohttp.ClientSession() as session:
            payload = {
                "model": ollama_model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": query},
                ],
                "stream": True,
                "options": {"num_ctx": 2048, "temperature": 0.3, "num_predict": 60},
            }
            async with session.post(
                f"http://127.0.0.1:11434/api/chat", json=payload,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                async for line in resp.content:
                    chunk = json.loads(line)
                    tok = chunk.get("message", {}).get("content", "")
                    if tok:
                        if first_token_t is None:
                            first_token_t = time.perf_counter()
                        full_response += tok

        results["stages"]["llm_first_token_ms"] = round((first_token_t - t) * 1000) if first_token_t else -1
        results["stages"]["llm_full_ms"] = round((time.perf_counter() - t) * 1000)
        results["stages"]["llm_response_len"] = len(full_response)

        # Stage 3: TTS (synthesize the LLM response)
        tts_text = full_response.strip()[:200] or "This is a test."
        t = time.perf_counter()
        first_byte_t = None
        audio_bytes = b""

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{xtts_url}/synthesize",
                json={"text": tts_text, "speaker": "Claribel Dervla", "language": "en"},
                timeout=aiohttp.ClientTimeout(total=60),
            ) as resp:
                async for chunk in resp.content.iter_chunked(4096):
                    if first_byte_t is None:
                        first_byte_t = time.perf_counter()
                    audio_bytes += chunk

        results["stages"]["tts_first_byte_ms"] = round((first_byte_t - t) * 1000) if first_byte_t else -1
        results["stages"]["tts_total_ms"] = round((time.perf_counter() - t) * 1000)
        if len(audio_bytes) > 44:
            results["stages"]["tts_audio_sec"] = round((len(audio_bytes) - 44) / (24000 * 2), 2)

        results["total_ms"] = round((time.perf_counter() - t_total_start) * 1000)

    except Exception as e:
        results["error"] = str(e)

    return results


# ═══════════════════════════════════════════════════════════════
# Report Generator
# ═══════════════════════════════════════════════════════════════

def _avg(lst):
    return sum(lst) / len(lst) if lst else 0

def _min(lst):
    return min(lst) if lst else 0

def generate_recommendations(hw: dict, ollama: dict, xtts: dict,
                              whisper: dict, chroma: dict, pipeline: dict) -> list[str]:
    """Produce actionable settings recommendations based on benchmark results."""
    recs = []

    # ── TTS recommendations ──
    if not xtts.get("error"):
        avg_short = _avg(xtts["short"]["first_byte_ms"])
        avg_medium = _avg(xtts["medium"]["first_byte_ms"])

        if avg_short > 3000:
            recs.append("🔴 TTS CRITICAL: Short text takes {:.0f}ms first byte. "
                        "XTTS may be on CPU. Verify GPU with: curl http://127.0.0.1:5002/health"
                        .format(avg_short))
        elif avg_short > 1500:
            recs.append("🟡 TTS SLOW: Short text takes {:.0f}ms. Consider reducing MAX_CHUNK_CHARS in xtts_server.py."
                        .format(avg_short))
        else:
            recs.append("🟢 TTS OK: Short text first byte in {:.0f}ms.".format(avg_short))

        # Real-time factor
        for key in ["short", "medium", "long"]:
            if xtts[key]["audio_sec"] and xtts[key]["total_ms"]:
                audio = _avg(xtts[key]["audio_sec"])
                synth = _avg(xtts[key]["total_ms"]) / 1000
                rtf = synth / audio if audio > 0 else 999
                if rtf > 1.0:
                    recs.append(f"🔴 TTS {key}: Synthesis is {rtf:.1f}x SLOWER than real-time — audio will stutter.")
                else:
                    recs.append(f"🟢 TTS {key}: {rtf:.2f}x real-time (faster than playback).")

    # ── LLM recommendations ──
    if not ollama.get("error"):
        avg_ft = _avg(ollama["first_token_ms"])
        avg_tps = _avg(ollama["tokens_per_sec"])
        if avg_ft > 1000:
            recs.append(f"🟡 LLM: First token takes {avg_ft:.0f}ms. Consider warming up or using a smaller model.")
        else:
            recs.append(f"🟢 LLM: First token in {avg_ft:.0f}ms.")
        recs.append(f"   LLM throughput: {avg_tps:.1f} tokens/sec")

    # ── STT recommendations ──
    if not whisper.get("error"):
        avg_stt = _avg(whisper["transcribe_ms"])
        info = whisper.get("model_info", {})
        if avg_stt > 2000:
            recs.append(f"🔴 STT SLOW: {avg_stt:.0f}ms per transcription. Switch to tiny.en on CPU with beam=1.")
        elif avg_stt > 800:
            recs.append(f"🟡 STT: {avg_stt:.0f}ms. Currently on {info.get('device', '?')} / {info.get('compute_type', '?')}.")
        else:
            recs.append(f"🟢 STT fast: {avg_stt:.0f}ms on {info.get('device', '?')} / {info.get('compute_type', '?')}.")

    # ── RAG recommendations ──
    if not chroma.get("error"):
        avg_rag = _avg(chroma["search_ms"])
        recs.append(f"{'🟢' if avg_rag < 100 else '🟡'} RAG search: {avg_rag:.0f}ms avg ({chroma['doc_count']} docs)")

    # ── Overall pipeline ──
    if not pipeline.get("error"):
        total = pipeline["total_ms"]
        stages = pipeline.get("stages", {})
        if total > 8000:
            recs.append(f"🔴 PIPELINE SLOW: {total}ms total. Focus on TTS optimization.")
        elif total > 5000:
            recs.append(f"🟡 PIPELINE OK: {total}ms total. Room for improvement.")
        else:
            recs.append(f"🟢 PIPELINE FAST: {total}ms total. Good performance!")

        # Bottleneck identification
        bottleneck_name = ""
        bottleneck_time = 0
        for name, val in stages.items():
            if name.endswith("_ms") and isinstance(val, (int, float)) and val > bottleneck_time:
                bottleneck_time = val
                bottleneck_name = name

        if bottleneck_name:
            recs.append(f"   ⏱  Bottleneck: {bottleneck_name} = {bottleneck_time}ms")

    # ── GPU VRAM budget ──
    if hw["cuda_available"]:
        total_vram = hw["gpu_vram_total_mb"]
        if total_vram <= 6000:
            recs.append(f"\n💡 GPU has {total_vram}MB VRAM — tight budget:")
            recs.append(f"   • Whisper on CPU (int8) ✓ already configured")
            recs.append(f"   • XTTS on GPU (~1.5GB)")
            recs.append(f"   • Ollama on GPU (~2-3GB for qwen2.5:3b)")
            recs.append(f"   • ChromaDB embeddings on CPU ✓")
        elif total_vram <= 8000:
            recs.append(f"\n💡 GPU has {total_vram}MB VRAM — adequate:")
            recs.append(f"   • All models can coexist on GPU")
            recs.append(f"   • Keep Whisper on CPU to avoid VRAM pressure")
        else:
            recs.append(f"\n💡 GPU has {total_vram}MB VRAM — generous:")
            recs.append(f"   • Could move Whisper to GPU for faster STT")

    # ── Adaptive chunk recommendation ──
    if not xtts.get("error"):
        avg_short_total = _avg(xtts["short"]["total_ms"])
        if avg_short_total < 1500:
            recs.append("\n📊 RECOMMENDED ADAPTIVE SETTINGS:")
            recs.append("   TIER_FAST   = words=12-15, buffer=0.0s")
            recs.append("   TIER_MEDIUM = words=10-12, buffer=0.1s")
            recs.append("   TIER_SLOW   = words=6-8,   buffer=0.3s")
        elif avg_short_total < 3000:
            recs.append("\n📊 RECOMMENDED ADAPTIVE SETTINGS:")
            recs.append("   TIER_FAST   = words=10-12, buffer=0.0s")
            recs.append("   TIER_MEDIUM = words=8-10,  buffer=0.2s")
            recs.append("   TIER_SLOW   = words=5-7,   buffer=0.4s")
        else:
            recs.append("\n📊 RECOMMENDED ADAPTIVE SETTINGS (TTS is slow):")
            recs.append("   TIER_FAST   = words=8-10,  buffer=0.1s")
            recs.append("   TIER_MEDIUM = words=6-8,   buffer=0.3s")
            recs.append("   TIER_SLOW   = words=4-6,   buffer=0.5s")

    # ── Silence detection recommendation ──
    if not whisper.get("error"):
        avg_stt = _avg(whisper["transcribe_ms"])
        recs.append(f"\n🎙  RECOMMENDED VAD SETTINGS:")
        if avg_stt < 500:
            recs.append("   silence_chunks_needed = 10  (~500ms)")
            recs.append("   silence_threshold_energy = 0.008")
            recs.append("   min_audio_buffer = 48000 bytes (1.5s)")
        else:
            recs.append("   silence_chunks_needed = 12  (~600ms)")
            recs.append("   silence_threshold_energy = 0.008")
            recs.append("   min_audio_buffer = 48000 bytes (1.5s)")

    return recs


# ═══════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════

async def main():
    print()
    print("═" * 65)
    print("  ASSISTIFY ULTIMATE SYSTEM BENCHMARK")
    print("═" * 65)
    print()

    # ── 1. Hardware ──
    print("▶ [1/6] Detecting hardware...")
    hw = detect_hardware()
    print(f"  CPU:   {hw['cpu_name']} ({hw['cpu_cores']} cores)")
    print(f"  RAM:   {hw['ram_total_gb']} GB")
    if hw["cuda_available"]:
        print(f"  GPU:   {hw['gpu_name']}")
        print(f"  VRAM:  {hw['gpu_vram_total_mb']} MB total, {hw['gpu_vram_free_mb']} MB free")
    else:
        print("  GPU:   No CUDA GPU detected")
    print()

    # ── 2. Ollama LLM ──
    print("▶ [2/6] Benchmarking Ollama LLM (3 runs)...")
    ollama = await bench_ollama()
    if ollama["error"]:
        print(f"  ✗ Error: {ollama['error']}")
    else:
        print(f"  First token:    avg {_avg(ollama['first_token_ms']):.0f}ms  "
              f"(best {_min(ollama['first_token_ms']):.0f}ms)")
        print(f"  Full response:  avg {_avg(ollama['full_response_ms']):.0f}ms")
        print(f"  Throughput:     avg {_avg(ollama['tokens_per_sec']):.1f} tok/s")
    print()

    # ── 3. XTTS ──
    print("▶ [3/6] Benchmarking XTTS TTS (3 runs × 3 lengths)...")
    xtts = await bench_xtts()
    if xtts.get("error"):
        print(f"  ✗ Error: {xtts['error']}")
    else:
        print(f"  XTTS GPU: {xtts.get('gpu_name', 'N/A')}  VRAM: {xtts.get('vram_mb', 0)} MB")
        for key in ["short", "medium", "long"]:
            d = xtts[key]
            if d["first_byte_ms"]:
                audio = _avg(d["audio_sec"]) if d["audio_sec"] else 0
                total = _avg(d["total_ms"])
                rtf = (total / 1000) / audio if audio > 0 else 0
                print(f"  {key:6s}: first_byte={_avg(d['first_byte_ms']):.0f}ms  "
                      f"total={total:.0f}ms  "
                      f"audio={audio:.1f}s  "
                      f"RTF={rtf:.2f}x")
    print()

    # ── 4. Whisper ──
    print("▶ [4/6] Benchmarking faster-whisper STT (3 runs)...")
    whisper = bench_whisper()
    if whisper["error"]:
        print(f"  ✗ Error: {whisper['error']}")
    else:
        info = whisper.get("model_info", {})
        print(f"  Model:      {info.get('model', '?')} on {info.get('device', '?')} ({info.get('compute_type', '?')})")
        print(f"  Load time:  {info.get('load_time_ms', 0)}ms")
        print(f"  Transcribe: avg {_avg(whisper['transcribe_ms']):.0f}ms  "
              f"(best {_min(whisper['transcribe_ms']):.0f}ms)")
    print()

    # ── 5. ChromaDB ──
    print("▶ [5/6] Benchmarking ChromaDB RAG search (5 runs)...")
    chroma = bench_chromadb()
    if chroma["error"]:
        print(f"  ✗ Error: {chroma['error']}")
    else:
        print(f"  Documents:  {chroma['doc_count']}")
        print(f"  Search:     avg {_avg(chroma['search_ms']):.0f}ms  "
              f"(best {_min(chroma['search_ms']):.0f}ms)")
    print()

    # ── 6. Full Pipeline ──
    print("▶ [6/6] Full pipeline simulation (RAG → LLM → TTS)...")
    pipeline = await bench_full_pipeline()
    if pipeline.get("error"):
        print(f"  ✗ Error: {pipeline['error']}")
    else:
        stages = pipeline["stages"]
        print(f"  RAG search:     {stages.get('rag_search_ms', '?')}ms ({stages.get('rag_docs_found', 0)} docs)")
        print(f"  LLM first tok:  {stages.get('llm_first_token_ms', '?')}ms")
        print(f"  LLM full:       {stages.get('llm_full_ms', '?')}ms  ({stages.get('llm_response_len', 0)} chars)")
        print(f"  TTS first byte: {stages.get('tts_first_byte_ms', '?')}ms")
        print(f"  TTS total:      {stages.get('tts_total_ms', '?')}ms  ({stages.get('tts_audio_sec', 0)}s audio)")
        print(f"  ─────────────────────────────")
        print(f"  TOTAL:          {pipeline['total_ms']}ms")
    print()

    # ── Recommendations ──
    print("═" * 65)
    print("  RECOMMENDATIONS")
    print("═" * 65)
    recs = generate_recommendations(hw, ollama, xtts, whisper, chroma, pipeline)
    for r in recs:
        print(f"  {r}")
    print()
    print("═" * 65)
    print("  BENCHMARK COMPLETE")
    print("═" * 65)
    print()


if __name__ == "__main__":
    asyncio.run(main())
