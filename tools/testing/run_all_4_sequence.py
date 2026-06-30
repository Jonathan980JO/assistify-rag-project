"""Test all 4 phase-2 queries in one WebSocket session.
Q1 and Q2 prime the context so Q3 is detected as a valid follow-up.
Q4 is asked in its own fresh connection to avoid stale state.
"""
import asyncio
import json
import websockets

WS_URL = "ws://127.0.0.1:7000/ws"
TIMEOUT = 180  # seconds per response


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


async def ask(ws, question):
    await ws.send(json.dumps({"text": question}))
    return await recv_done(ws)


async def main():
    print("=" * 60)
    print("SESSION 1: Q1, Q2, Q3 in one connection (Q3 = follow-up)")
    print("=" * 60)
    async with websockets.connect(WS_URL, max_size=10 * 1024 * 1024, ping_interval=None) as ws:
        # Consume greeting if any
        try:
            await asyncio.wait_for(ws.recv(), timeout=3)
        except Exception:
            pass

        # Q1
        q = "What is psychology?"
        print(f"\nQ1: {q}")
        r = await ask(ws, q)
        print(f"A1: {r}")
        await asyncio.sleep(1)

        # Q2
        q = "What are the goals of psychology?"
        print(f"\nQ2: {q}")
        r = await ask(ws, q)
        print(f"A2: {r}")
        await asyncio.sleep(1)

        # Q3 — follow-up to Q2
        q = "Explain the control of human behavior goal"
        print(f"\nQ3: {q}")
        r = await ask(ws, q)
        print(f"A3: {r}")

    await asyncio.sleep(2)

    print("\n" + "=" * 60)
    print("SESSION 2: Q4 in a fresh connection")
    print("=" * 60)
    async with websockets.connect(WS_URL, max_size=10 * 1024 * 1024, ping_interval=None) as ws:
        try:
            await asyncio.wait_for(ws.recv(), timeout=3)
        except Exception:
            pass

        q = "What are the main perspectives of psychology?"
        print(f"\nQ4: {q}")
        r = await ask(ws, q)
        print(f"A4: {r}")


asyncio.run(main())
