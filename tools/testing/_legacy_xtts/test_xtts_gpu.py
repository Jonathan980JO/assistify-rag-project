"""
XTTS v2 GPU Load & VRAM Test Script
====================================
Usage: python scripts/test_xtts_gpu.py
Tests:
  1. XTTS v2 loads on GPU (no ImportError)
  2. VRAM usage before/after load
  3. Synthesis of 5 test phrases (latency measurement)
  4. 20-round stress test (memory leak / OOM detection)
"""
import os, sys, time, gc, warnings, io, wave
import numpy as np

# Force UTF-8 output on Windows to avoid charmap encoding errors
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ('utf-8', 'utf8'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except AttributeError:
        pass  # Python < 3.7 fallback

os.environ["COQUI_TOS_AGREED"] = "1"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
warnings.filterwarnings("ignore")

import torch

def vram_mb():
    if torch.cuda.is_available():
        return torch.cuda.memory_reserved(0) / 1024**2
    return 0.0

def vram_allocated_mb():
    if torch.cuda.is_available():
        return torch.cuda.memory_allocated(0) / 1024**2
    return 0.0

print("=" * 60)
print("  XTTS v2 GPU Load & VRAM Test")
print("=" * 60)

# ── baseline VRAM ─────────────────────────────────────────
torch.cuda.empty_cache()
vram_base = vram_mb()
total_vram = torch.cuda.get_device_properties(0).total_memory / 1024**2
print(f"\n[GPU] {torch.cuda.get_device_name(0)}")
print(f"[VRAM] Total     : {total_vram:.0f} MB")
print(f"[VRAM] Baseline  : {vram_base:.0f} MB")

# ── import XTTS ───────────────────────────────────────────
print("\n[1/5] Importing TTS API...")
t0 = time.time()
from TTS.api import TTS as CoquiTTS
print(f"      Import OK ({time.time()-t0:.2f}s)")

# ── load model ────────────────────────────────────────────
print("\n[2/5] Loading XTTS v2 model on GPU...")
t0 = time.time()
try:
    xtts = CoquiTTS("tts_models/multilingual/multi-dataset/xtts_v2", gpu=True)
    load_time = time.time() - t0
    vram_after_load = vram_mb()
    vram_used = vram_after_load - vram_base
    print(f"      Load OK   ({load_time:.2f}s)")
    print(f"[VRAM] After TTS load : {vram_after_load:.0f} MB")
    print(f"[VRAM] TTS used       : {vram_used:.0f} MB  (~{vram_used/1024:.2f} GB)")
except Exception as e:
    print(f"      FAILED: {e}")
    import traceback; traceback.print_exc()
    sys.exit(1)

# ── synthesis latency test ────────────────────────────────
TEST_PHRASES = [
    "Hello, I am Assistify, your AI voice assistant.",
    "The quick brown fox jumps over the lazy dog.",
    "VRAM usage is within safe limits for the RTX 3070.",
    "Voice synthesis is working correctly end to end.",
    "System is production-ready for the graduation demo.",
]

SPEAKER  = "Claribel Dervla"   # Verified correct XTTS v2 speaker name
LANGUAGE = "en"
SAMPLE_RATE = 24000

print(f"\n[3/5] Synthesis latency test ({len(TEST_PHRASES)} phrases)...")
latencies = []
for i, phrase in enumerate(TEST_PHRASES):
    t0 = time.time()
    try:
        samples = xtts.tts(text=phrase, speaker=SPEAKER, language=LANGUAGE)
        lat = (time.time() - t0) * 1000
        latencies.append(lat)
        audio_dur_ms = len(samples) / SAMPLE_RATE * 1000
        rtf = lat / audio_dur_ms
        print(f"  [{i+1}] {lat:.0f}ms latency | {audio_dur_ms:.0f}ms audio | RTF={rtf:.2f} | OK")
    except Exception as e:
        print(f"  [{i+1}] FAILED: {e}")

if latencies:
    print(f"\n  Avg latency : {sum(latencies)/len(latencies):.0f} ms")
    print(f"  Min latency : {min(latencies):.0f} ms")
    print(f"  Max latency : {max(latencies):.0f} ms")

# ── VRAM after warm-up ─────────────────────────────────────
vram_warm = vram_mb()
print(f"\n[VRAM] After warm-up  : {vram_warm:.0f} MB  ({vram_warm/1024:.2f} GB)")
print(f"[VRAM] Remaining free : {(total_vram - vram_warm):.0f} MB  ({(total_vram - vram_warm)/1024:.2f} GB)")
print(f"[VRAM] For LLM (est.) : {(total_vram - vram_warm):.0f} MB available")

SAFE_LIMIT_MB = 7.5 * 1024  # 7.5 GB
if vram_warm < SAFE_LIMIT_MB:
    print(f"[VRAM] PASS: WITHIN safe limit (< 7.5 GB)")
else:
    print(f"[VRAM] FAIL: EXCEEDS safe limit! ({vram_warm:.0f} MB > {SAFE_LIMIT_MB:.0f} MB)")

# ── 20-round stress test ───────────────────────────────────
print(f"\n[4/5] Running 20-round stress test...")
STRESS_PHRASE = "This is stress test iteration number {i} of twenty."
oom_count = 0
error_count = 0
stress_latencies = []
vram_samples = []

for i in range(1, 21):
    try:
        t0 = time.time()
        samples = xtts.tts(
            text=STRESS_PHRASE.format(i=i),
            speaker=SPEAKER,
            language=LANGUAGE
        )
        lat = (time.time() - t0) * 1000
        stress_latencies.append(lat)
        # sample VRAM every 5 rounds
        if i % 5 == 0:
            v = vram_mb()
            vram_samples.append(v)
            print(f"  Round {i:02d}: {lat:.0f}ms | VRAM: {v:.0f} MB | OK")
        del samples
        gc.collect()
    except torch.cuda.OutOfMemoryError as e:
        oom_count += 1
        print(f"  Round {i:02d}: OOM ERROR - {e}")
        torch.cuda.empty_cache()
    except Exception as e:
        error_count += 1
        print(f"  Round {i:02d}: ERROR - {e}")

print(f"\n  Stress test complete:")
print(f"  OOM errors    : {oom_count}")
print(f"  Other errors  : {error_count}")
if stress_latencies:
    print(f"  Avg latency   : {sum(stress_latencies)/len(stress_latencies):.0f} ms")
    print(f"  Max latency   : {max(stress_latencies):.0f} ms")
if vram_samples:
    print(f"  Peak VRAM     : {max(vram_samples):.0f} MB ({max(vram_samples)/1024:.2f} GB)")
    # Check for memory leak: last sample significantly higher than first?
    if len(vram_samples) >= 2:
        drift = vram_samples[-1] - vram_samples[0]
        print(f"  VRAM drift    : {drift:+.0f} MB ({'POSSIBLE LEAK' if drift > 100 else 'STABLE'})")

# ── sentence-transformers smoke test ──────────────────────
print(f"\n[5/5] Sentence-transformers smoke test...")
try:
    from sentence_transformers import SentenceTransformer
    st_model = SentenceTransformer("all-MiniLM-L6-v2")
    emb = st_model.encode(["hello world"])
    print(f"  Embedding shape: {emb.shape} | OK")
    del st_model
    gc.collect()
except Exception as e:
    print(f"  FAILED: {e}")

# ── final VRAM ─────────────────────────────────────────────
torch.cuda.empty_cache()
vram_final = vram_mb()
print(f"\n[VRAM] Final reserved : {vram_final:.0f} MB ({vram_final/1024:.2f} GB)")
print(f"[VRAM] Allocated      : {vram_allocated_mb():.0f} MB")

print("\n" + "=" * 60)
print("  SUMMARY")
print("=" * 60)
print(f"  XTTS v2 load      : OK")
print(f"  transformers ver  : {__import__('transformers').__version__}")
print(f"  torch ver         : {torch.__version__}")
print(f"  CUDA ver          : {torch.version.cuda}")
print(f"  GPU               : {torch.cuda.get_device_name(0)}")
print(f"  XTTS VRAM         : ~{vram_used:.0f} MB")
if latencies:
    print(f"  TTS avg latency   : {sum(latencies)/len(latencies):.0f} ms (first 5 phrases)")
if stress_latencies:
    print(f"  Stress avg latency: {sum(stress_latencies)/len(stress_latencies):.0f} ms")
print(f"  OOM errors        : {oom_count}")
print(f"  Total errors      : {oom_count + error_count}")
if oom_count == 0 and error_count == 0:
    print("\n  [PASS] SYSTEM IS DEMO-READY")
else:
    print(f"\n  [FAIL] {oom_count + error_count} ERRORS - REVIEW REQUIRED")
print("=" * 60)
