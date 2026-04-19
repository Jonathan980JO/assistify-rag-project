import asyncio, json, sys
import websockets

QUESTIONS = [
    "What are the characteristics of management?",
    "What are the steps in the planning process?",
    "What is scientific management?",
    "What are the six Ms of management?",
    "What is quantum computing?",
]

async def ask(uri, q):
    async with websockets.connect(uri, max_size=None, ping_interval=None) as ws:
        await ws.send(json.dumps({"text": q}))
        full = ""
        while True:
            msg = await asyncio.wait_for(ws.recv(), timeout=240)
            if isinstance(msg, bytes):
                continue
            try:
                data = json.loads(msg)
            except Exception:
                continue
            t = data.get("type")
            if t == "aiResponseChunk":
                full += data.get("text", "")
            if t == "aiResponseDone":
                if "fullText" in data:
                    full = data["fullText"]
                return full

async def main():
    uri = "ws://localhost:7000/ws"
    for q in QUESTIONS:
        print(f"\n=== Q: {q} ===")
        try:
            ans = await ask(uri, q)
            print(ans)
        except Exception as e:
            print(f"ERROR: {e!r}")
        print("=== END ===")

asyncio.run(main())
