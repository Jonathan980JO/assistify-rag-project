"""
Arabic TTS Regression Test Script
==================================
Runs three controlled test cases against the live XTTS service at 127.0.0.1:5002
and reports per-test audio statistics.

Usage:
    conda activate assistify_xtts
    python tests/test_arabic_tts.py

Or with a custom speaker:
    python tests/test_arabic_tts.py --speaker "Claribel Dervla"

Outputs:
    test_A_english.wav
    test_B_arabic_simple.wav
    test_C_arabic_sentence.wav
"""

import argparse
import io
import json
import struct
import sys
import time
import wave

import numpy as np
import requests

SERVICE_URL = "http://127.0.0.1:5002"
DEFAULT_SPEAKER = "Claribel Dervla"

TEST_CASES = [
    {
        "id": "A",
        "label": "English baseline",
        "text": "Hello, this is a voice quality test.",
        "language": "en",
        "out_file": "test_A_english.wav",
    },
    {
        "id": "B",
        "label": "Simple Arabic",
        "text": "\u0645\u0631\u062d\u0628\u0627 \u0643\u064a\u0641 \u062d\u0627\u0644\u0643 \u0627\u0644\u064a\u0648\u0645",
        "language": "ar",
        "out_file": "test_B_arabic_simple.wav",
    },
    {
        "id": "C",
        "label": "Full Arabic sentence",
        "text": "\u0647\u0630\u0627 \u0627\u062e\u062a\u0628\u0627\u0631 \u0644\u0644\u0635\u0648\u062a \u0627\u0644\u0639\u0631\u0628\u064a \u0641\u064a \u0627\u0644\u0646\u0638\u0627\u0645",
        "language": "ar",
        "out_file": "test_C_arabic_sentence.wav",
    },
    {
        "id": "D",
        "label": "Arabic with number (regression: number must NOT become English words)",
        "text": "\u0641\u064a \u0639\u0627\u0645 2023 \u0643\u0627\u0646 \u0645\u062c\u0645\u0648\u0639 \u0627\u0644\u0637\u0644\u0627\u0628 500 \u0637\u0627\u0644\u0628",
        "language": "ar",
        "out_file": "test_D_arabic_number.wav",
    },
    {
        "id": "E",
        "label": "Arabic with colon (regression: colon must NOT become comma)",
        "text": "\u0627\u0644\u062a\u0639\u0631\u064a\u0641: \u0645\u0641\u0647\u0648\u0645 \u064a\u0634\u064a\u0631 \u0625\u0644\u0649 \u0627\u0644\u0637\u0627\u0642\u0629",
        "language": "ar",
        "out_file": "test_E_arabic_colon.wav",
    },
]


def analyze_wav(raw_bytes: bytes) -> dict:
    """Parse raw bytes returned by the service into per-channel stats."""
    stats = {
        "total_bytes": len(raw_bytes),
        "error": None,
    }
    try:
        buf = io.BytesIO(raw_bytes)
        with wave.open(buf, "rb") as wf:
            n_frames = wf.getnframes()
            sample_rate = wf.getframerate()
            n_channels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            raw_frames = wf.readframes(n_frames)
        pcm = np.frombuffer(raw_frames, dtype=np.int16).astype(np.float32) / 32768.0
        duration_s = len(pcm) / sample_rate if sample_rate else 0
        stats.update({
            "sample_rate": sample_rate,
            "n_channels": n_channels,
            "sampwidth": sampwidth,
            "n_frames": n_frames,
            "duration_s": round(duration_s, 3),
            "n_samples": len(pcm),
            "min": round(float(pcm.min()), 5) if pcm.size else None,
            "max": round(float(pcm.max()), 5) if pcm.size else None,
            "mean_abs": round(float(np.abs(pcm).mean()), 5) if pcm.size else None,
            "near_silent": (float(np.abs(pcm).mean()) < 0.005) if pcm.size else True,
        })
    except Exception as exc:
        stats["error"] = str(exc)
    return stats


def run_test(tc: dict, speaker: str) -> dict:
    label = f"Test {tc['id']} — {tc['label']}"
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"  text: {repr(tc['text'])}")
    print(f"  codepoints: {[hex(ord(c)) for c in tc['text'][:10]]}")
    print(f"  language: {tc['language']}  speaker: {speaker}")
    print(f"{'='*60}")

    payload = {
        "text": tc["text"],
        "language": tc["language"],
        "speaker": speaker,
    }

    try:
        t0 = time.perf_counter()
        resp = requests.post(
            f"{SERVICE_URL}/synthesize",
            json=payload,
            timeout=120,
            stream=True,
        )
        latency_ms = (time.perf_counter() - t0) * 1000
        resp.raise_for_status()
        raw = resp.content
        elapsed_ms = (time.perf_counter() - t0) * 1000

        print(f"  HTTP {resp.status_code}  total_bytes={len(raw)}  latency={latency_ms:.0f}ms  total={elapsed_ms:.0f}ms")

        stats = analyze_wav(raw)
        print(f"  WAV stats: duration={stats.get('duration_s')}s  "
              f"n_samples={stats.get('n_samples')}  "
              f"mean_abs={stats.get('mean_abs')}  "
              f"min={stats.get('min')}  max={stats.get('max')}")
        if stats.get("near_silent"):
            print(f"  WARNING: near-silent audio detected (mean_abs < 0.005)!")
        if stats.get("error"):
            print(f"  WAV parse error: {stats['error']}")

        # Save audio file
        with open(tc["out_file"], "wb") as f:
            f.write(raw)
        print(f"  Saved: {tc['out_file']}")

        return {
            "test_id": tc["id"],
            "label": label,
            "status": "ok",
            "http_status": resp.status_code,
            "latency_ms": round(latency_ms, 1),
            "total_ms": round(elapsed_ms, 1),
            **stats,
        }

    except requests.exceptions.ConnectionError:
        print(f"  FAILED: Cannot connect to {SERVICE_URL} — is the XTTS service running?")
        return {"test_id": tc["id"], "label": label, "status": "connection_error"}
    except requests.exceptions.Timeout:
        print(f"  FAILED: Request timed out after 120s")
        return {"test_id": tc["id"], "label": label, "status": "timeout"}
    except requests.exceptions.HTTPError as exc:
        print(f"  FAILED: HTTP error {exc}")
        return {"test_id": tc["id"], "label": label, "status": f"http_error_{exc.response.status_code}"}


def check_health() -> bool:
    try:
        resp = requests.get(f"{SERVICE_URL}/health", timeout=5)
        data = resp.json()
        print(f"Service health: {json.dumps(data, indent=2)}")
        return data.get("status") == "ok"
    except Exception as exc:
        print(f"Health check failed: {exc}")
        return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--speaker", default=DEFAULT_SPEAKER, help="Speaker name")
    args = parser.parse_args()

    print("=" * 60)
    print("XTTS Arabic Regression Test")
    print("=" * 60)

    if not check_health():
        print("\nWARNING: Service is not healthy. Tests may fail.")
        print("Continuing anyway...\n")

    # Get available speakers
    try:
        resp = requests.get(f"{SERVICE_URL}/speakers", timeout=5)
        data = resp.json()
        print(f"Available speakers: {data.get('count', 0)}")
        if args.speaker not in (data.get("speakers") or []):
            print(f"WARNING: Requested speaker '{args.speaker}' not in speakers list!")
            print(f"First 5 available: {(data.get('speakers') or [])[:5]}")
    except Exception as exc:
        print(f"Could not fetch speakers: {exc}")

    results = []
    for tc in TEST_CASES:
        result = run_test(tc, args.speaker)
        results.append(result)

    # Summary comparison
    print("\n" + "=" * 60)
    print("SUMMARY COMPARISON")
    print("=" * 60)
    print(f"{'Test':<6} {'Lang':<5} {'Duration':<12} {'mean_abs':<12} {'near_silent':<12} {'status'}")
    print("-" * 60)
    for r in results:
        tc_info = next((t for t in TEST_CASES if t["id"] == r["test_id"]), {})
        print(
            f"{r['test_id']:<6} {tc_info.get('language','?'):<5} "
            f"{str(r.get('duration_s','?'))+'s':<12} "
            f"{str(r.get('mean_abs','?')):<12} "
            f"{str(r.get('near_silent','?')):<12} "
            f"{r.get('status','?')}"
        )

    # Print package versions for environment diagnosis
    print("\n" + "=" * 60)
    print("ENVIRONMENT VERSIONS")
    print("=" * 60)
    try:
        import importlib.metadata as meta
        for pkg in ["TTS", "torch", "numpy", "gruut", "phonemizer", "tokenizers", "transformers"]:
            try:
                v = meta.version(pkg)
                print(f"  {pkg}: {v}")
            except meta.PackageNotFoundError:
                print(f"  {pkg}: NOT INSTALLED")
    except Exception as exc:
        print(f"  Could not read package versions: {exc}")

    # Print sys.path for import diagnosis
    print("\n  sys.path (first 5 entries):")
    for p in sys.path[:5]:
        print(f"    {p}")

    # Check TTS import source
    try:
        import TTS
        print(f"\n  TTS module location: {getattr(TTS, '__file__', 'unknown')}")
    except ImportError:
        print("\n  TTS module: CANNOT IMPORT")


if __name__ == "__main__":
    main()
