import asyncio
import json
import websockets

QUERIES = [
    "What is scientific management?",
    "Who is Frederick Taylor?",
]


async def ask(q: str):
    uri = "ws://127.0.0.1:7000/ws"
    async with websockets.connect(uri, max_size=2**22, ping_interval=20, ping_timeout=20) as ws:
        await ws.send(json.dumps({"text": q, "language": "en"}))
        done = {}
        for _ in range(1400):
            msg = await asyncio.wait_for(ws.recv(), timeout=180)
            if isinstance(msg, (bytes, bytearray)):
                continue
            data = json.loads(msg)
            if data.get("type") == "aiResponseDone":
                done = data
                break
    print("\nQ:", q)
    print("done_keys:", sorted(done.keys()))
    print("fullText:", (done.get("fullText") or "")[:250])
    srcs_raw = done.get("sources")
    srcs = done.get("sourceContexts") or done.get("contexts") or []
    if isinstance(srcs_raw, int):
        print("sources_count:", srcs_raw)
    else:
        try:
            print("sources_count:", len(srcs_raw or srcs))
        except Exception:
            print("sources_count:", 0)
    if srcs:
        first = srcs[0]
        if isinstance(first, dict):
            txt = first.get("text") or first.get("page_content") or first.get("content") or ""
            print("source0_keys:", sorted(first.keys()))
            print("source0_preview:", str(txt)[:400])
        else:
            print("source0:", str(first)[:400])


async def main():
    for q in QUERIES:
        await ask(q)


if __name__ == "__main__":
    asyncio.run(main())
