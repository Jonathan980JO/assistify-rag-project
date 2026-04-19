import asyncio, json, time, websockets

URI = "ws://localhost:7000/ws"
QS = [
    "What are the six Ms of management?",
    "What is scientific management?",
    "What are the characteristics of management?",
    "What is quantum computing?",
]

async def ask(q):
    full = ""
    async with websockets.connect(URI, max_size=None) as w:
        await w.send(json.dumps({"text": q}))
        t0 = time.time()
        while True:
            m = await asyncio.wait_for(w.recv(), timeout=180)
            if isinstance(m, (bytes, bytearray)):
                continue
            d = json.loads(m)
            t = d.get("type")
            if t == "aiResponseChunk":
                full += d.get("text", "")
            elif t == "aiResponseDone":
                if d.get("fullText"): full = d["fullText"]
                return full.strip(), time.time()-t0

async def main():
    print("=== MPC0 REAL /ws (4 queries) ===")
    for q in QS:
        a, dur = await ask(q)
        print(f"\nQ: {q}\nT: {dur:.1f}s\nA: {a}\n" + "-"*60)

asyncio.run(main())
