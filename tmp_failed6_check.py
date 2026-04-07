import asyncio
import json
import time
import websockets

QUERIES = [
    "What is scientific management?",
    "Define management.",
    "What is decision-making?",
    "What is administrative management?",
    "Who is Max Weber?",
    "Who introduced administrative theory?",
]


async def ask(q: str):
    uri = "ws://127.0.0.1:7000/ws"
    t0 = time.perf_counter()
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
                part = (data.get("text") or "").strip()
                if part:
                    chunks.append(part)
            elif data.get("type") == "aiResponseDone":
                done = data
                break
    total_ms = round((time.perf_counter() - t0) * 1000, 1)
    ans = ((done or {}).get("fullText") or " ".join(chunks)).strip()
    return {
        "query": q,
        "latency_ms": total_ms,
        "not_found": ans.lower() == "not found in the document.",
        "answer": ans,
    }


async def main():
    out = []
    for q in QUERIES:
        out.append(await ask(q))
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
