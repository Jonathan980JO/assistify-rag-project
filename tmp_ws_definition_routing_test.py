import asyncio
import json
import time
from datetime import datetime

import websockets

URI = "ws://127.0.0.1:7000/ws"
QUERIES = [
    "explain structuralism",
    "what does structuralism focus on",
    "how does operant conditioning work",
    "what is the idea behind operant conditioning",
    "what is structuralism",
    "define operant conditioning",
    "what is blockchain",
    "what is artificial intelligence",
]


async def ask(query: str) -> dict:
    started = time.perf_counter()
    answer = ""
    events = []
    err = None
    async with websockets.connect(URI, max_size=8_000_000) as ws:
        await ws.send(json.dumps({"text": query}))
        while True:
            raw = await asyncio.wait_for(ws.recv(), timeout=120)
            if isinstance(raw, bytes):
                continue
            payload = json.loads(raw)
            t = payload.get("type")
            events.append(t)
            if t == "aiResponseChunk":
                answer += payload.get("text", "")
            elif t == "aiResponse":
                answer = payload.get("text", "") or answer
                break
            elif t == "aiResponseDone":
                answer = payload.get("fullText", "") or answer
                break
            elif payload.get("error"):
                err = payload.get("error")
                break
    elapsed_ms = round((time.perf_counter() - started) * 1000.0, 2)
    return {"query": query, "answer": answer.strip(), "elapsed_ms": elapsed_ms, "events": events, "error": err}


async def main():
    out = {"ts": datetime.now().isoformat(), "uri": URI, "results": []}
    for q in QUERIES:
        r = await ask(q)
        out["results"].append(r)
        print(f"Q: {q}\nA: {r['answer']}\n---")
    out_path = f"run_queries_results_ui_ws_definition_routing_{int(time.time())}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(out_path)


if __name__ == "__main__":
    asyncio.run(main())
