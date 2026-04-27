"""Strict follow-up regression probe over the real /ws endpoint.

Usage:
    python tools/testing/followup_strict_ws_regression.py

The script sends the required three-turn scenario through the same websocket
path used by the UI and writes a JSON report next to this file.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import websockets  # type: ignore


WS_URL = os.environ.get("ASSISTIFY_WS_URL", "ws://127.0.0.1:7000/ws")
PER_QUERY_TIMEOUT_S = float(os.environ.get("ASSISTIFY_WS_TIMEOUT", "120"))
NO_MATCH = "Not found in the document."

SCENARIO = [
    ("Q1", "What are the goals of psychology?", None),
    ("Q2", "Explain prediction goal", "prediction"),
    ("Q3", "Explain control of human behavior", "control"),
]


async def run_one_query(ws: Any, label: str, text: str) -> dict[str, Any]:
    start = time.perf_counter()
    await ws.send(json.dumps({"text": text, "language": "en"}))
    chunks: list[str] = []
    full_text = ""
    first_chunk_at: float | None = None
    sources = None
    timing = None
    deadline = start + PER_QUERY_TIMEOUT_S

    while True:
        remaining = deadline - time.perf_counter()
        if remaining <= 0:
            break
        try:
            raw_message = await asyncio.wait_for(ws.recv(), timeout=remaining)
        except asyncio.TimeoutError:
            break
        if isinstance(raw_message, (bytes, bytearray)):
            continue
        try:
            message = json.loads(raw_message)
        except Exception:
            continue
        message_type = message.get("type")
        if message_type == "aiResponseChunk":
            chunk_text = message.get("text") or ""
            if chunk_text:
                if first_chunk_at is None:
                    first_chunk_at = time.perf_counter()
                chunks.append(chunk_text)
            if message.get("done"):
                full_text = full_text or "".join(chunks)
        elif message_type == "aiResponseDone":
            full_text = message.get("fullText") or "".join(chunks)
            sources = message.get("sources")
            timing = message.get("timing")
            break

    done = time.perf_counter()
    answer = full_text.strip()
    return {
        "label": label,
        "query": text,
        "answer": answer,
        "answer_chars": len(answer),
        "first_chunk_ms": int((first_chunk_at - start) * 1000) if first_chunk_at else None,
        "total_ms": int((done - start) * 1000),
        "sources": sources,
        "timing": timing,
    }


def evaluate(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    evaluated: list[dict[str, Any]] = []
    previous_answer = ""
    for index, result in enumerate(results):
        answer = str(result.get("answer") or "").strip()
        answer_low = answer.lower()
        target = SCENARIO[index][2]
        reasons: list[str] = []

        if not answer:
            reasons.append("empty answer")
        if result.get("total_ms", 0) >= int(PER_QUERY_TIMEOUT_S * 1000):
            reasons.append("timeout")
        if index == 0 and answer == NO_MATCH:
            reasons.append("initial list returned not-found")
        if index in (1, 2):
            if answer == NO_MATCH:
                reasons.append("follow-up returned not-found")
            if target and target not in answer_low:
                reasons.append(f"target term {target!r} absent from answer")
            if previous_answer and answer == previous_answer:
                reasons.append("answer repeated previous turn exactly")

        evaluated.append({**result, "pass": not reasons, "reasons": reasons})
        previous_answer = answer
    return evaluated


async def main() -> int:
    print(f"[followup-probe] connecting to {WS_URL}")
    results: list[dict[str, Any]] = []
    try:
        async with websockets.connect(
            WS_URL,
            max_size=None,
            ping_interval=20,
            ping_timeout=20,
            open_timeout=15,
        ) as ws:
            print("[followup-probe] connected")
            for label, query, _target in SCENARIO:
                print(f"\n[followup-probe] {label}: {query!r}")
                result = await run_one_query(ws, label, query)
                preview = result["answer"][:260].replace("\n", " ")
                print(
                    f"[followup-probe] {label} first_chunk_ms={result['first_chunk_ms']} "
                    f"total_ms={result['total_ms']} chars={result['answer_chars']} "
                    f"sources={result['sources']}"
                )
                print(f"[followup-probe] {label} preview: {preview}")
                results.append(result)
                await asyncio.sleep(0.2)
    except Exception as exc:
        print(f"[followup-probe] FATAL: {exc}")
        return 2

    evaluated = evaluate(results)
    print("\n========== FOLLOW-UP STRICT WS REPORT ==========")
    exit_code = 0
    for result in evaluated:
        verdict = "PASS" if result["pass"] else "FAIL"
        print(
            f"{result['label']} {verdict} | total_ms={result['total_ms']} "
            f"| first_chunk_ms={result['first_chunk_ms']} "
            f"| chars={result['answer_chars']} | reasons={result['reasons']}"
        )
        if not result["pass"]:
            exit_code = 1

    out_path = Path(__file__).resolve().parent / "followup_strict_ws_regression.last.json"
    out_path.write_text(json.dumps(evaluated, indent=2, ensure_ascii=True), encoding="utf-8")
    print(f"\n[followup-probe] full report written to {out_path}")
    return exit_code


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))