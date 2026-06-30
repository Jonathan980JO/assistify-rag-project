"""
XTTS Microservice Stress Test
==============================
Tests the /synthesize endpoint with 20 consecutive requests and measures:
  - Cold start latency (first request after model load)
  - Warm latency (subsequent requests)
  - Peak VRAM
  - Any errors / memory leaks
"""
import time
import statistics
import requests

BASE_URL = "http://127.0.0.1:5002"
SPEAKER = "Claribel Dervla"
LANGUAGE = "en"
PHRASES = [
    "Hello, I am Assistify, your AI voice assistant.",
    "The quick brown fox jumps over the lazy dog.",
    "VRAM usage is within safe limits for the RTX 3070.",
    "Voice synthesis is working correctly end to end.",
    "System is production-ready for the graduation demo.",
    "Welcome to the Assistify intelligent knowledge assistant.",
    "Your question has been processed and the answer is ready.",
    "Please wait while I search the knowledge base for you.",
    "The system has loaded all necessary models successfully.",
    "All components are operational and running on GPU.",
]


def check_health():
    r = requests.get(f"{BASE_URL}/health", timeout=10)
    r.raise_for_status()
    data = r.json()
    print(f"  GPU     : {data.get('gpu')}")
    print(f"  VRAM    : {data.get('vram_used_mb')} MB")
    print(f"  Load    : {data.get('model_load_time_s')} s")
    return data


def synthesize(phrase: str) -> tuple[int, float, float]:
    """Returns (bytes, latency_ms, vram_mb)"""
    r = requests.post(
        f"{BASE_URL}/synthesize",
        json={"text": phrase, "speaker": SPEAKER, "language": LANGUAGE},
        timeout=120,
    )
    r.raise_for_status()
    latency = float(r.headers.get("X-Latency-Ms", 0))
    vram = float(r.headers.get("X-VRAM-MB", 0))
    return len(r.content), latency, vram


def run_stress_test(n: int = 20):
    print(f"\n{'='*60}")
    print(f"  XTTS Microservice Stress Test  ({n} requests)")
    print(f"{'='*60}")

    # Health check
    print("\n[1/3] Health check...")
    h = check_health()
    print(f"  Status  : {h.get('status')}")

    # 5-phrase warm-up / latency measurement
    print("\n[2/3] Latency test (5 phrases)...")
    latencies = []
    vrams = []
    for i, phrase in enumerate(PHRASES[:5], 1):
        try:
            sz, lat, vram = synthesize(phrase)
            latencies.append(lat)
            vrams.append(vram)
            print(f"  [{i}] {lat:.0f} ms | {sz//1024} KB | VRAM {vram:.0f} MB | OK")
        except Exception as exc:
            print(f"  [{i}] FAILED: {exc}")

    if latencies:
        print(f"\n  Avg latency : {statistics.mean(latencies):.0f} ms")
        print(f"  Min latency : {min(latencies):.0f} ms")
        print(f"  Max latency : {max(latencies):.0f} ms")

    # 20-round stress test
    print(f"\n[3/3] {n}-round stress test...")
    STRESS = "This is stress test iteration number {i} of {n}."
    oom_count = 0
    err_count = 0
    stress_lats = []
    stress_vrams = []

    for i in range(1, n + 1):
        try:
            _, lat, vram = synthesize(STRESS.format(i=i, n=n))
            stress_lats.append(lat)
            if i % 5 == 0:
                stress_vrams.append(vram)
                print(f"  Round {i:02d}: {lat:.0f} ms | VRAM {vram:.0f} MB | OK")
        except requests.exceptions.HTTPError as exc:
            err_count += 1
            print(f"  Round {i:02d}: HTTP ERROR - {exc}")
        except Exception as exc:
            err_count += 1
            print(f"  Round {i:02d}: ERROR - {exc}")

    # Final health check
    h2 = requests.get(f"{BASE_URL}/health").json()

    print(f"\n{'='*60}")
    print(f"  SUMMARY")
    print(f"{'='*60}")
    print(f"  OOM errors        : {oom_count}")
    print(f"  Other errors      : {err_count}")
    if stress_lats:
        print(f"  Stress avg lat    : {statistics.mean(stress_lats):.0f} ms")
        print(f"  Stress max lat    : {max(stress_lats):.0f} ms")
    if stress_vrams:
        print(f"  Peak VRAM         : {max(stress_vrams):.0f} MB")
        drift = stress_vrams[-1] - stress_vrams[0] if len(stress_vrams) >= 2 else 0
        print(f"  VRAM drift        : {drift:+.0f} MB ({'STABLE' if abs(drift) < 100 else 'POSSIBLE LEAK'})")
    print(f"  Final VRAM (srv)  : {h2.get('vram_used_mb')} MB")
    total_errors = oom_count + err_count
    if total_errors == 0:
        print(f"\n  [PASS] {n}/{n} requests succeeded - DEMO READY")
    else:
        print(f"\n  [FAIL] {total_errors} errors - REVIEW REQUIRED")
    print(f"{'='*60}")


if __name__ == "__main__":
    run_stress_test(20)
