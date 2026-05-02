"""
End-to-end test: LLM question → XTTS voice → save WAV to Desktop.
------------------------------------------------------------------
Steps:
  1. Send a question to Ollama (qwen2.5:3b) via /api/chat
  2. Take the LLM text response
  3. Send it to XTTS service (/synthesize) on port 5002
  4. Save the resulting WAV file to the Desktop
  5. Print timing + VRAM stats

Usage:
  conda activate assistify_main
  python scripts/test_xtts_e2e.py
"""

import os, sys, time, json, pathlib, requests

# ── Config ──────────────────────────────────────────────────────
OLLAMA_URL   = "http://127.0.0.1:11434/api/chat"
XTTS_URL     = "http://127.0.0.1:5002/synthesize"
XTTS_HEALTH  = "http://127.0.0.1:5002/health"
RAG_TTS_URL  = "http://127.0.0.1:7000/tts"             # proxy on RAG server

OLLAMA_MODEL = "qwen2.5:3b"
SPEAKER      = "Claribel Dervla"
LANGUAGE     = "en"

DESKTOP      = pathlib.Path.home() / "Desktop"
OUTPUT_FILE  = DESKTOP / "assistify_xtts_test.wav"

QUESTION     = "What is artificial intelligence? Answer briefly in 2 sentences."

# ── Helpers ─────────────────────────────────────────────────────
def check_service(name, url, timeout=5):
    try:
        r = requests.get(url, timeout=timeout)
        r.raise_for_status()
        print(f"  ✔ {name} is UP  ({url})  status={r.status_code}")
        return True, r
    except Exception as e:
        print(f"  ✘ {name} is DOWN ({url})  error={e}")
        return False, None


def ask_llm(question: str) -> str:
    """Send a question to Ollama and return the text response."""
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": "You are a helpful assistant. Keep responses under 80 words."},
            {"role": "user", "content": question},
        ],
        "stream": False,
        "options": {
            "num_ctx": 2048,
            "temperature": 0.6,
            "top_p": 0.9,
            "num_predict": 180,
        },
    }
    print(f"\n[1/3] Asking LLM: \"{question}\"")
    t0 = time.time()
    r = requests.post(OLLAMA_URL, json=payload, timeout=120)
    r.raise_for_status()
    data = r.json()
    text = data["message"]["content"].strip()
    elapsed = time.time() - t0
    word_count = len(text.split())
    print(f"      LLM response ({elapsed:.1f}s, {word_count} words):")
    print(f"      \"{text}\"")
    return text


def synthesize_xtts_direct(text: str) -> bytes:
    """Call XTTS microservice directly on port 5002."""
    payload = {"text": text, "speaker": SPEAKER, "language": LANGUAGE}
    print(f"\n[2/3] Synthesizing via XTTS (direct → {XTTS_URL})...")
    t0 = time.time()
    r = requests.post(XTTS_URL, json=payload, timeout=180)
    elapsed = time.time() - t0

    print(f"      Status: {r.status_code}")
    print(f"      Content-Type: {r.headers.get('Content-Type', '?')}")
    print(f"      Size: {len(r.content) / 1024:.1f} KB")
    print(f"      Latency: {elapsed:.2f}s")
    if "X-Latency-Ms" in r.headers:
        print(f"      Server latency: {r.headers['X-Latency-Ms']} ms")
    if "X-VRAM-MB" in r.headers:
        print(f"      VRAM used: {r.headers['X-VRAM-MB']} MB")

    if r.status_code != 200:
        print(f"      ERROR body: {r.text[:500]}")
        raise RuntimeError(f"XTTS returned {r.status_code}: {r.text[:200]}")

    return r.content


def synthesize_via_rag(text: str) -> bytes:
    """Call TTS through the RAG server proxy on port 7000."""
    payload = {"text": text, "speaker": SPEAKER, "language": LANGUAGE}
    print(f"\n[2b] Synthesizing via RAG proxy → {RAG_TTS_URL} ...")
    t0 = time.time()
    r = requests.post(RAG_TTS_URL, json=payload, timeout=180)
    elapsed = time.time() - t0

    print(f"      Status: {r.status_code}")
    print(f"      Content-Type: {r.headers.get('Content-Type', '?')}")
    print(f"      Size: {len(r.content) / 1024:.1f} KB")
    print(f"      Latency: {elapsed:.2f}s")

    if r.status_code != 200:
        print(f"      ERROR body: {r.text[:500]}")
        raise RuntimeError(f"RAG /tts returned {r.status_code}: {r.text[:200]}")

    return r.content


def save_wav(wav_bytes: bytes, path: pathlib.Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(wav_bytes)
    print(f"\n[3/3] Saved WAV file → {path}")
    print(f"      File size: {path.stat().st_size / 1024:.1f} KB")


# ── Main ────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("  ASSISTIFY — End-to-End TTS Test")
    print("=" * 60)

    # 0. Check services
    print("\nChecking services...")
    ollama_ok, _ = check_service("Ollama", "http://127.0.0.1:11434/api/tags")
    xtts_ok, xtts_resp = check_service("XTTS", XTTS_HEALTH)
    rag_ok, _ = check_service("RAG", "http://127.0.0.1:7000/health")

    if xtts_ok and xtts_resp:
        try:
            health = xtts_resp.json()
            print(f"      XTTS model: {health.get('model', '?')}")
            print(f"      GPU: {health.get('gpu', '?')}")
            print(f"      VRAM: {health.get('vram_used_mb', '?')} MB")
            print(f"      CUDA: {health.get('cuda_available', '?')}")
        except Exception:
            pass

    if not ollama_ok:
        print("\n❌ Ollama is not running. Start it with: ollama serve")
        sys.exit(1)
    if not xtts_ok:
        print("\n❌ XTTS is not running. Start it with: start_xtts_service.bat")
        sys.exit(1)

    # 1. Ask LLM
    total_t0 = time.time()
    llm_text = ask_llm(QUESTION)

    # 2. Synthesize with XTTS (direct)
    try:
        wav_data = synthesize_xtts_direct(llm_text)
    except Exception as e:
        print(f"\n⚠ Direct XTTS failed: {e}")
        print("   Trying via RAG proxy...")
        wav_data = synthesize_via_rag(llm_text)

    # 3. Save to Desktop
    save_wav(wav_data, OUTPUT_FILE)

    total_elapsed = time.time() - total_t0
    print(f"\n{'=' * 60}")
    print(f"  ✅ TOTAL pipeline: {total_elapsed:.2f}s")
    print(f"  File: {OUTPUT_FILE}")
    print(f"  Open it and listen — it should be a natural voice,")
    print(f"  NOT a robotic browser voice.")
    print(f"{'=' * 60}")

    # Also test RAG proxy if RAG server is up
    if rag_ok:
        print(f"\n--- Bonus: testing RAG /tts proxy ---")
        try:
            wav2 = synthesize_via_rag(llm_text)
            out2 = DESKTOP / "assistify_xtts_test_via_rag.wav"
            save_wav(wav2, out2)
            print(f"  ✅ RAG proxy also works! Saved → {out2}")
        except Exception as e:
            print(f"  ❌ RAG /tts proxy FAILED: {e}")
            print(f"     This means the browser would fall back to robotic voice!")
            print(f"     Check RAG server logs for the error.")


if __name__ == "__main__":
    main()
