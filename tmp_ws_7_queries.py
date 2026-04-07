import asyncio
import json
import time
from pathlib import Path

import websockets

QUERIES = [
    "what is bureaucracy",
    "tell me about management principles",
    "advantages of scientific management",
    "steps in planning process",
    "what is administrative management",
    "who is Frederick Taylor",
    "who is Elon Musk",
]

URI = "ws://localhost:7000/ws"


async def ask_one(query: str) -> dict:
    started = time.perf_counter()
    full_text = ""
    done_payload = None
    events = []
    err = None

    try:
        async with websockets.connect(URI, max_size=10 * 1024 * 1024) as websocket:
            await websocket.send(json.dumps({"text": query}))
            while True:
                raw = await asyncio.wait_for(websocket.recv(), timeout=90)
                if isinstance(raw, bytes):
                    continue
                payload = json.loads(raw)
                events.append(payload.get("type"))
                ptype = payload.get("type")
                if ptype == "aiResponseChunk":
                    full_text += payload.get("text", "")
                elif ptype == "aiResponse":
                    full_text = payload.get("text", "") or full_text
                    done_payload = payload
                    break
                elif ptype == "aiResponseDone":
                    full_text = payload.get("fullText", "") or full_text
                    done_payload = payload
                    break
                elif "error" in payload:
                    err = payload.get("error") or payload.get("text") or "unknown_error"
                    done_payload = payload
                    break
    except Exception as exc:
        err = str(exc)

    elapsed_ms = (time.perf_counter() - started) * 1000.0
    timing = (done_payload or {}).get("timing") if isinstance(done_payload, dict) else None
    return {
        "query": query,
        "answer": (full_text or "").strip(),
        "elapsed_ms": round(elapsed_ms, 2),
        "timing": timing,
        "events": events,
        "error": err,
    }


async def main(out_file: str):
    results = []
    for query in QUERIES:
        result = await ask_one(query)
        print(f"Q: {query}\n  ms={result['elapsed_ms']} error={result['error']}\n  ans={result['answer'][:220]}\n")
        results.append(result)

    out_path = Path(out_file)
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved: {out_path.resolve()}")


if __name__ == "__main__":
    import sys

    out = sys.argv[1] if len(sys.argv) > 1 else "ws_7_results.json"
    asyncio.run(main(out))
