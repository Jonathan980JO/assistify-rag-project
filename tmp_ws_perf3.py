import asyncio
import json
import time
import websockets

QUESTIONS = [
    "What is psychology?",
    "Who founded the first psychological laboratory and when?",
    "Give only psychology goals",
    "What is the capital of France?",
]


async def ask(q: str):
    uri = "ws://127.0.0.1:7000/ws"
    t0 = time.perf_counter()
    async with websockets.connect(uri, max_size=2**22, ping_interval=20, ping_timeout=20) as ws:
        await ws.send(json.dumps({"text": q, "language": "en"}))
        first_chunk_ms = None
        done = None
        while True:
            msg = await asyncio.wait_for(ws.recv(), timeout=120)
            if isinstance(msg, (bytes, bytearray)):
                continue
            data = json.loads(msg)
            if data.get("type") == "aiResponseChunk" and first_chunk_ms is None:
                first_chunk_ms = (time.perf_counter() - t0) * 1000
            if data.get("type") == "aiResponseDone":
                done = data
                break
        total_ms = (time.perf_counter() - t0) * 1000
        return q, round(first_chunk_ms or -1, 1), round(total_ms, 1), (done or {}).get("fullText", "")


async def main():
    for q in QUESTIONS:
        r = await ask(q)
        print("Q:", r[0])
        print("first_chunk_ms:", r[1], "total_ms:", r[2])
        print("A:", r[3][:250])
        print("-" * 70)


if __name__ == "__main__":
    asyncio.run(main())
