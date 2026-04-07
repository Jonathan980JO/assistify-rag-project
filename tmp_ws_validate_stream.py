import asyncio
import json
import websockets

QUERIES = [
    "Disadvantages of scientific management",
    "Steps in planning process",
    "What is scientific management",
]

async def ws_once(q):
    uri = "ws://127.0.0.1:7000/ws"
    chunks = []
    done = None
    async with websockets.connect(uri, max_size=2**22, ping_interval=20, ping_timeout=20) as ws:
        await ws.send(json.dumps({"text": q, "language": "en"}))
        for _ in range(1200):
            msg = await asyncio.wait_for(ws.recv(), timeout=90)
            if isinstance(msg, (bytes, bytearray)):
                continue
            data = json.loads(msg)
            if data.get("type") == "aiResponseChunk":
                chunks.append(data.get("text", ""))
            elif data.get("type") == "aiResponseDone":
                done = data
                break
    stream_text = "".join(chunks).strip()
    done_text = (done or {}).get("fullText", "")
    return stream_text, done_text

async def main():
    for q in QUERIES:
        print(f"--- WS: {q}")
        try:
            stream_text, done_text = await ws_once(q)
            print("STREAM:", stream_text[:600])
            print("DONE:", done_text[:600])
        except Exception as e:
            print("ERROR:", e)

if __name__ == "__main__":
    asyncio.run(main())
