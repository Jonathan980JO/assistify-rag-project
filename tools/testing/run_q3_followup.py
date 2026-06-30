"""Test Q3 (follow-up) — primes context with Q1+Q2 in same session, then asks Q3."""
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


async def main():
    async with websockets.connect(WS_URL, max_size=10 * 1024 * 1024, ping_interval=None) as ws:
        try:
            await asyncio.wait_for(ws.recv(), timeout=3)
        except Exception:
            pass

        # Prime context: Q1
        print("Priming Q1...")
        await ws.send(json.dumps({"text": "What is psychology?"}))
        r1 = await recv_done(ws)
        print(f"A1: {r1}\n")
        await asyncio.sleep(1)

        # Prime context: Q2
        print("Priming Q2...")
        await ws.send(json.dumps({"text": "What are the goals of psychology?"}))
        r2 = await recv_done(ws)
        print(f"A2: {r2}\n")
        await asyncio.sleep(1)

        # Q3: follow-up
        print("Q3: Explain the control of human behavior goal")
        await ws.send(json.dumps({"text": "Explain the control of human behavior goal"}))
        r3 = await recv_done(ws)
        print(f"A3: {r3}\n")


asyncio.run(main())
