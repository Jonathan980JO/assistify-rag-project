import asyncio
import json
import time
import websockets

QUESTIONS = [
    "What is psychology?",
    "Who founded the first psychological laboratory and when?",
    "What are the main goals of psychology?",
    "ما هو علم النفس؟",
    "اشرح المدرسة السلوكية",
    "List ONLY the goals of psychology.",
    "Extract the list of psychology branches only.",
    "What is the capital of France?",
    "Explain psychology AND mention its goals AND give one real-life application.",
]


async def ask(q: str):
    uri = "ws://127.0.0.1:7000/ws"
    t0 = time.perf_counter()
    async with websockets.connect(uri, max_size=2**22, ping_interval=20, ping_timeout=20) as ws:
        await ws.send(json.dumps({"text": q, "language": "auto"}, ensure_ascii=False))
        chunks = 0
        done = None
        first_chunk_ms = None
        while True:
            msg = await asyncio.wait_for(ws.recv(), timeout=120)
            if isinstance(msg, (bytes, bytearray)):
                continue
            data = json.loads(msg)
            if data.get("type") == "aiResponseChunk":
                chunks += 1
                if first_chunk_ms is None:
                    first_chunk_ms = (time.perf_counter() - t0) * 1000
            if data.get("type") == "aiResponseDone":
                done = data
                break
        total_ms = (time.perf_counter() - t0) * 1000
        return {
            "q": q,
            "done": bool(done),
            "chunks": chunks,
            "sources": (done or {}).get("sources"),
            "first_chunk_ms": round(first_chunk_ms, 1) if first_chunk_ms is not None else None,
            "total_ms": round(total_ms, 1),
            "answer": (done or {}).get("fullText", ""),
        }


async def main():
    results = []
    for q in QUESTIONS:
        try:
            result = await ask(q)
        except Exception as exc:
            result = {"q": q, "done": False, "error": str(exc), "answer": ""}
        results.append(result)
        print("Q:", result["q"])
        if result.get("error"):
            print("ERROR:", result.get("error"))
        print("DONE:", result.get("done"), "chunks:", result.get("chunks"), "sources:", result.get("sources"), "first_chunk_ms:", result.get("first_chunk_ms"), "total_ms:", result.get("total_ms"))
        print("A:", (result.get("answer") or "")[:300])
        print("-" * 90)

    with open("rag_eval_results_ws.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    asyncio.run(main())
