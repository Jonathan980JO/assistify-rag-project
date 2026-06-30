"""Real /ws regression smoke test for the XTTS perceived-latency fix.

Sends a fixed set of text-mode questions to the live backend over the real
WebSocket /ws path, records timings and server-side TTS log lines, and prints
a pass/fail report. Does NOT bypass retrieval/grounding/answer logic — it
only exercises the backend the same way the browser does.

Usage:
    python tools/testing/regression_smoke_ws.py
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

import websockets  # type: ignore

WS_URL = "ws://127.0.0.1:8000/ws"

QUERIES = [
    "What is psychology?",
    "List the goals of psychology",
    "so what about the Control of human behavior in the goals of psychology what does it means",
    "What is psychology?",  # repeat — should hit TTS cache for any chunk identical to round 1
]

PER_QUERY_TIMEOUT_S = 180.0


async def run_one_query(ws, text: str, idx: int) -> dict:
    t0 = time.perf_counter()
    await ws.send(json.dumps({"text": text, "language": "en"}))
    chunks: list[str] = []
    full_text = ""
    first_chunk_at = None
    sources = None
    arabic_mode = None
    timing = None
    deadline = t0 + PER_QUERY_TIMEOUT_S
    while True:
        remaining = deadline - time.perf_counter()
        if remaining <= 0:
            break
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
        except asyncio.TimeoutError:
            break
        # Binary frames are TTS PCM — ignore for this text-mode smoke test.
        if isinstance(raw, (bytes, bytearray)):
            continue
        try:
            msg = json.loads(raw)
        except Exception:
            continue
        mtype = msg.get("type")
        if mtype == "aiResponseChunk":
            txt = msg.get("text") or ""
            if txt:
                if first_chunk_at is None:
                    first_chunk_at = time.perf_counter()
                chunks.append(txt)
            if msg.get("done"):
                # Some paths short-circuit and only send a single chunk with done=True.
                full_text = full_text or "".join(chunks)
        elif mtype == "aiResponseDone":
            full_text = msg.get("fullText") or "".join(chunks)
            sources = msg.get("sources")
            arabic_mode = msg.get("arabic_mode")
            timing = msg.get("timing")
            break
        elif mtype == "ttsAudioStart":
            pass
        elif mtype == "ttsAudioEnd":
            pass
        elif mtype == "ttsFallback":
            pass
        # ignore everything else
    t_done = time.perf_counter()
    return {
        "idx": idx,
        "query": text,
        "answer": full_text.strip(),
        "answer_chars": len(full_text.strip()),
        "first_chunk_ms": int((first_chunk_at - t0) * 1000) if first_chunk_at else None,
        "total_ms": int((t_done - t0) * 1000),
        "sources": sources,
        "arabic_mode": arabic_mode,
        "timing": timing,
    }


def evaluate(results: list[dict]) -> list[dict]:
    out = []
    for r in results:
        ans = (r["answer"] or "").strip().lower()
        passed = True
        reasons = []
        if not ans:
            passed = False
            reasons.append("empty answer")
        if r["total_ms"] is None or r["total_ms"] >= PER_QUERY_TIMEOUT_S * 1000:
            passed = False
            reasons.append("timeout")
        # Q1 / Q4 (definition) should not return Not found.
        if r["idx"] in (0, 3) and ans.startswith("not found"):
            passed = False
            reasons.append("definition returned Not found")
        out.append({**r, "pass": passed, "reasons": reasons})
    return out


async def main() -> int:
    print(f"[probe] connecting to {WS_URL}")
    try:
        async with websockets.connect(
            WS_URL,
            max_size=None,
            ping_interval=20,
            ping_timeout=20,
            open_timeout=15,
        ) as ws:
            print("[probe] connected")
            results = []
            for i, q in enumerate(QUERIES):
                print(f"\n[probe] === Q{i+1}: {q!r} ===")
                r = await run_one_query(ws, q, i)
                print(
                    f"[probe] Q{i+1} answer_chars={r['answer_chars']} "
                    f"first_chunk_ms={r['first_chunk_ms']} total_ms={r['total_ms']} "
                    f"sources={r['sources']}"
                )
                preview = (r["answer"] or "")[:240].replace("\n", " ")
                print(f"[probe] Q{i+1} preview: {preview}")
                results.append(r)
                # small gap so backend log lines don't interleave too tightly
                await asyncio.sleep(0.5)
    except Exception as e:
        print(f"[probe] FATAL: {e}")
        return 2

    evaluated = evaluate(results)
    print("\n========== SMOKE TEST REPORT ==========")
    rc = 0
    for r in evaluated:
        verdict = "PASS" if r["pass"] else "FAIL"
        print(
            f"  Q{r['idx']+1} {verdict:4s} | total_ms={r['total_ms']:>6} "
            f"| first_chunk_ms={r['first_chunk_ms']} | chars={r['answer_chars']:>4} "
            f"| sources={r['sources']} | reasons={r['reasons']}"
        )
        if not r["pass"]:
            rc = 1

    out_path = Path(__file__).resolve().parent / "regression_smoke_ws.last.json"
    out_path.write_text(json.dumps(evaluated, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n[probe] full report written to {out_path}")
    return rc


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
