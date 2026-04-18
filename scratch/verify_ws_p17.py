import asyncio, json, sys, time
import websockets

URI = "ws://localhost:7000/ws"
QUESTIONS = [
    "What are the six Ms of management?",
    "What are the characteristics of management?",
    "What is scientific management?",
    "What are Fayol's principles of management?",
    "What is quantum computing?",
]

async def ask(q: str) -> str:
    full = ""
    async with websockets.connect(URI, max_size=None) as ws:
        await ws.send(json.dumps({"text": q}))
        t0 = time.time()
        while True:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=180.0)
            except asyncio.TimeoutError:
                full += "\n[TIMEOUT]"
                break
            if isinstance(msg, (bytes, bytearray)):
                continue
            try:
                data = json.loads(msg)
            except Exception:
                continue
            t = data.get("type")
            if t == "aiResponseChunk":
                full += data.get("text", "")
            elif t == "aiResponseDone":
                if data.get("fullText"):
                    full = data["fullText"]
                break
            elif "error" in data:
                full += f"\n[ERROR] {data['error']}"
                break
        return full.strip(), time.time() - t0

async def main():
    label = sys.argv[1] if len(sys.argv) > 1 else "RUN"
    print(f"=== {label} ===")
    for q in QUESTIONS:
        ans, dur = await ask(q)
        print(f"\nQ: {q}\nT: {dur:.1f}s\nA: {ans}\n" + "-"*60)

if __name__ == "__main__":
    asyncio.run(main())
