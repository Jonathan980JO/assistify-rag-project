import asyncio
import json
import time
from pathlib import Path

import websockets

QUERIES = [
    "What is scientific management?",
    "Define management.",
    "What is planning?",
    "What is decision-making?",
    "What is administrative management?",
    "What is bureaucracy?",
    "Who is Frederick Taylor?",
    "Who is Henry Fayol?",
    "Who is Max Weber?",
    "Who is considered the father of scientific management?",
    "Who introduced administrative theory?",
    "Steps in planning process",
    "Advantages of scientific management",
    "Disadvantages of scientific management",
    "Types of management approaches",
    "Phases of management process",
    "Levels of management",
    "Functions of management",
    "What are the disadvantages of bureaucracy?",
    "What are the advantages of administrative management?",
    "What topics are covered in Chapter 2?",
    "What is discussed in Chapter 1?",
    "What are the main sections in this document?",
    "What does this document talk about?",
    "What is the difference between scientific management and administrative management?",
    "What happens in planning?",
    "Explain planning process",
]

WS_URL = "ws://127.0.0.1:7000/ws"
OUT_JSON = Path("tmp/final_answer_quality_results.json")


def classify(q: str) -> str:
    low = q.lower().strip()
    if low.startswith(("what is", "define", "who is", "who was", "who introduced")):
        return "definition"
    if any(k in low for k in ["advantages", "disadvantages", "steps", "phases", "levels", "types", "functions", "process", "what happens"]):
        return "list"
    return "overview_compare"


def raw_chunk_dump_flag(ans: str, q_type: str) -> bool:
    text = (ans or "").strip()
    if not text:
        return False
    words = text.split()
    if q_type == "definition":
        return len(words) > 70
    if q_type == "list":
        has_list_lines = sum(1 for ln in text.splitlines() if ln.strip().startswith("- ")) >= 3
        return (not has_list_lines) and len(words) > 120
    return len(words) > 220 and "\n- " not in text


async def ask_one(ws, q: str):
    await ws.send(json.dumps({"text": q, "language": "en"}))
    chunks = []
    done = None
    t0 = time.perf_counter()
    for _ in range(800):
        msg = await asyncio.wait_for(ws.recv(), timeout=180)
        if isinstance(msg, (bytes, bytearray)):
            continue
        data = json.loads(msg)
        t = data.get("type")
        if t == "aiResponseChunk":
            c = (data.get("text") or "").strip()
            if c:
                chunks.append(c)
        elif t == "aiResponseDone":
            done = data
            break
    latency_ms = int((time.perf_counter() - t0) * 1000)
    full = (done or {}).get("fullText", "")
    if not full and chunks:
        full = " ".join(chunks).strip()
    return full.strip(), latency_ms


async def main():
    results = []
    async with websockets.connect(WS_URL, max_size=2**23, ping_interval=20, ping_timeout=20) as ws:
        for q in QUERIES:
            answer, latency_ms = await ask_one(ws, q)
            q_type = classify(q)
            list_items = [ln.strip() for ln in answer.splitlines() if ln.strip().startswith("- ")]
            results.append(
                {
                    "query": q,
                    "type": q_type,
                    "answer": answer,
                    "latency_ms": latency_ms,
                    "word_count": len(answer.split()),
                    "line_count": len([ln for ln in answer.splitlines() if ln.strip()]),
                    "list_items_count": len(list_items),
                    "raw_chunk_dump_flag": raw_chunk_dump_flag(answer, q_type),
                }
            )

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    dump_count = sum(1 for r in results if r["raw_chunk_dump_flag"])
    print(f"saved={OUT_JSON}")
    print(f"queries={len(results)}")
    print(f"raw_chunk_dump_flags={dump_count}")


if __name__ == "__main__":
    asyncio.run(main())
