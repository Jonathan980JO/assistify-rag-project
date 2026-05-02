"""Test Q1, Q2, Q4 each with a fresh connection (no ping timeout)."""
import asyncio
import json
import websockets

WS_URL = "ws://127.0.0.1:7000/ws"
TIMEOUT = 150


async def recv_done(ws):
    full = ""
    while True:
        raw = await asyncio.wait_for(ws.recv(), timeout=TIMEOUT)
        msg = json.loads(raw)
        t = msg.get("type", "")
        if t == "aiResponseDone":
            return msg.get("fullText") or full
        if t == "aiResponseChunk":
            full += msg.get("text", "")
        if t == "error":
            return "[ERROR] " + str(msg)


async def ask_fresh(q):
    async with websockets.connect(WS_URL, max_size=10 * 1024 * 1024, ping_interval=None) as ws:
        try:
            await asyncio.wait_for(ws.recv(), timeout=3)
        except Exception:
            pass
        await ws.send(json.dumps({"text": q}))
        return await recv_done(ws)


async def main():
    queries = [
        "What is psychology?",
        "What are the goals of psychology?",
        "What are the main perspectives of psychology?",
    ]
    for q in queries:
        print(f"Q: {q}")
        try:
            r = await ask_fresh(q)
            print(f"A: {r}")
        except Exception as e:
            print(f"[EXCEPTION] {e}")
        print()
        await asyncio.sleep(3)


asyncio.run(main())
