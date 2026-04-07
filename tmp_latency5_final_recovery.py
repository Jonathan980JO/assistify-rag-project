import asyncio
import json
import time
import websockets

QUERIES = [
    "What is scientific management?",
    "What is administrative management?",
    "What is bureaucracy?",
    "Who is Frederick Taylor?",
    "Advantages of scientific management",
]


async def ask(q: str):
    uri = "ws://127.0.0.1:7000/ws"
    started = time.perf_counter()
    async with websockets.connect(uri, max_size=2**22, ping_interval=20, ping_timeout=20) as ws:
        await ws.send(json.dumps({"text": q, "language": "en"}))
        done = None
        chunks = []
        for _ in range(1200):
            msg = await asyncio.wait_for(ws.recv(), timeout=180)
            if isinstance(msg, (bytes, bytearray)):
                continue
            data = json.loads(msg)
            if data.get("type") == "aiResponseChunk":
                chunk = (data.get("text") or "").strip()
                if chunk:
                    chunks.append(chunk)
            elif data.get("type") == "aiResponseDone":
                done = data
                break
    total_ms = round((time.perf_counter() - started) * 1000, 1)
    answer = ((done or {}).get("fullText") or " ".join(chunks)).strip()
    return {
        "query": q,
        "latency_ms": total_ms,
        "not_found": answer.lower() == "not found in the document.",
        "preview": answer[:220],
    }


async def main():
    rows = []
    for q in QUERIES:
        rows.append(await ask(q))
    print(json.dumps(rows, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
