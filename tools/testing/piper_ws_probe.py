"""
WS probe: end-to-end /ws round-trip + TTS smoke for the Piper-only TTS engine.

Runs from the assistify_main env. Speaks to the real RAG WebSocket on
ws://127.0.0.1:7000/ws and the real /tts HTTP endpoint at
http://127.0.0.1:7000/tts (which proxies to the Piper service on :5002).

Per-test pass/fail is reported. Audio is NOT played; we only verify that the
server returns audio bytes and the answer text.
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
import wave
import io
from typing import Any

import requests
import websockets


WS_URI = "ws://127.0.0.1:7000/ws"
TTS_URL = "http://127.0.0.1:7000/tts"
DIRECT_PIPER_URL = "http://127.0.0.1:5002/synthesize"
PIPER_HEALTH = "http://127.0.0.1:5002/health"


async def run_ws_query(question: str, *, language: str = "en", timeout: float = 180.0) -> dict:
    """Send a single text query over /ws, collect text + audio metadata."""
    full_text = ""
    audio_bytes_total = 0
    audio_chunk_count = 0
    first_text_t = None
    first_audio_t = None
    done = False
    err: str | None = None
    t0 = time.perf_counter()

    try:
        async with websockets.connect(WS_URI, max_size=2**24) as ws:
            await ws.send(json.dumps({"text": question, "language": language}))
            while True:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=timeout)
                except asyncio.TimeoutError:
                    err = "timeout"
                    break
                if isinstance(msg, (bytes, bytearray)):
                    audio_chunk_count += 1
                    audio_bytes_total += len(msg)
                    if first_audio_t is None:
                        first_audio_t = time.perf_counter() - t0
                    continue
                try:
                    data = json.loads(msg)
                except Exception:
                    continue
                kind = data.get("type")
                if kind == "aiResponseChunk":
                    chunk = data.get("text") or ""
                    full_text += chunk
                    if first_text_t is None and chunk.strip():
                        first_text_t = time.perf_counter() - t0
                elif kind == "aiResponseDone":
                    if data.get("fullText"):
                        full_text = data["fullText"]
                    done = True
                    break
                elif kind == "error":
                    err = data.get("message") or "ws error"
                    break
    except Exception as e:
        err = f"connect_error: {e}"

    return {
        "question": question,
        "language": language,
        "answer": full_text.strip(),
        "answer_len": len(full_text.strip()),
        "audio_chunks": audio_chunk_count,
        "audio_bytes": audio_bytes_total,
        "first_text_ms": int(first_text_t * 1000) if first_text_t else None,
        "first_audio_ms": int(first_audio_t * 1000) if first_audio_t else None,
        "total_ms": int((time.perf_counter() - t0) * 1000),
        "done": done,
        "error": err,
    }


def http_tts(text: str, language: str) -> dict:
    t0 = time.perf_counter()
    try:
        r = requests.post(
            TTS_URL,
            json={"text": text, "language": language},
            timeout=120,
        )
    except Exception as e:
        return {"text": text, "language": language, "error": f"connect: {e}"}
    elapsed = int((time.perf_counter() - t0) * 1000)
    if r.status_code != 200:
        return {
            "text": text, "language": language, "status": r.status_code,
            "body": r.text[:200], "ms": elapsed,
        }
    raw = r.content
    sr = None
    n_samples = None
    try:
        with wave.open(io.BytesIO(raw), "rb") as wf:
            sr = wf.getframerate()
            n_samples = wf.getnframes()
    except Exception:
        pass
    return {
        "text": text, "language": language, "status": 200,
        "bytes": len(raw), "sample_rate": sr, "samples": n_samples,
        "duration_s": (n_samples / sr) if (sr and n_samples) else None,
        "ms": elapsed,
    }


def piper_health() -> dict:
    try:
        r = requests.get(PIPER_HEALTH, timeout=5)
        return {"status": r.status_code, "body": r.json() if r.status_code == 200 else r.text[:200]}
    except Exception as e:
        return {"error": str(e)}


def report(label: str, payload: Any) -> None:
    print(f"\n=== {label} ===")
    if isinstance(payload, dict):
        for k, v in payload.items():
            if k == "answer":
                snippet = (v or "")[:300].replace("\n", " ")
                print(f"  {k}: {snippet}")
            else:
                print(f"  {k}: {v}")
    else:
        print(payload)


async def main() -> int:
    print("=" * 60)
    print(" Assistify Piper-only WS probe")
    print("=" * 60)

    # 1) Piper service health
    h = piper_health()
    report("piper /health", h)
    if "body" not in h or (isinstance(h.get("body"), dict) and not h["body"].get("ready")):
        print("ABORT: Piper service is not ready.")
        return 2

    # 2) WS round-trips (English)
    q1 = await run_ws_query("What is psychology?", language="en")
    report("WS test 1 — English: 'What is psychology?'", q1)

    q2 = await run_ws_query("What is psychology?", language="en")
    report("WS test 2 — English repeat", q2)

    q3 = await run_ws_query("List the goals of psychology", language="en")
    report("WS test 3 — List", q3)

    q4 = await run_ws_query(
        "so what about the Control of human behavior in the goals of psychology what does it means",
        language="en",
    )
    report("WS test 4 — Follow-up", q4)

    # 5) Arabic direct TTS (HTTP /tts)
    a1 = http_tts("مرحبا كيف حالك اليوم", "ar")
    report("HTTP /tts test 5 — Arabic direct", a1)

    # 6) English direct TTS sanity
    a2 = http_tts("This is a short English sentence for Piper.", "en")
    report("HTTP /tts test 6 — English direct sanity", a2)

    # Pass/fail summary
    print("\n" + "=" * 60)
    print(" Summary")
    print("=" * 60)
    failures: list[str] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {name}  {detail}")
        if not ok:
            failures.append(name)

    check("WS 1 English answered",
          q1["done"] and q1["answer_len"] > 0 and not q1["error"],
          f"len={q1['answer_len']} done={q1['done']} err={q1['error']}")
    check("WS 1 audio streamed",
          (q1["audio_bytes"] or 0) > 0,
          f"bytes={q1['audio_bytes']} chunks={q1['audio_chunks']}")
    check("WS 2 English repeat answered",
          q2["done"] and q2["answer_len"] > 0,
          f"len={q2['answer_len']}")
    check("WS 3 List answered",
          q3["done"] and q3["answer_len"] > 0,
          f"len={q3['answer_len']}")
    check("WS 4 Follow-up answered",
          q4["done"] and q4["answer_len"] > 0,
          f"len={q4['answer_len']}")
    check("HTTP /tts Arabic returns WAV",
          a1.get("status") == 200 and (a1.get("bytes") or 0) > 1000,
          f"bytes={a1.get('bytes')} sr={a1.get('sample_rate')} dur={a1.get('duration_s')}")
    check("HTTP /tts English returns WAV",
          a2.get("status") == 200 and (a2.get("bytes") or 0) > 1000,
          f"bytes={a2.get('bytes')} sr={a2.get('sample_rate')} dur={a2.get('duration_s')}")

    print("\nFailures:", failures if failures else "none")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
