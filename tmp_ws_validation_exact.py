import asyncio
import json
import time
from pathlib import Path

import websockets

QUERIES = [
    "what is management in general",
    "what is mangement in general",
    "what is scientific management",
    "who is Frederick Taylor",
    "what is bureaucracy",
    "tell me about management principles",
    "tell me about mangement principles",
    "advantages of scientific management",
    "steps in planning process",
    "what is administrative management",
    "who introduced administrative theory",
    "what is machine learning",
    "who is Elon Musk",
]

URI = "ws://localhost:7000/ws"
OUT_PATH = Path("validation_ws_exact_results.json")


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


async def main():
    results = []
    for query in QUERIES:
        result = await ask_one(query)
        print(f"Q: {query}\n  ms={result['elapsed_ms']} error={result['error']}\n  ans={result['answer'][:180]}\n")
        results.append(result)

    OUT_PATH.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved: {OUT_PATH.resolve()}")


if __name__ == "__main__":
    asyncio.run(main())
