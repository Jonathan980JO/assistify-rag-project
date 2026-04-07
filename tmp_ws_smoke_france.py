import asyncio
import json
import websockets


async def main():
    uri = "ws://127.0.0.1:7000/ws"
    async with websockets.connect(uri, max_size=2**22, ping_interval=20, ping_timeout=20) as ws:
        await ws.send(json.dumps({"text": "what is the capital of france", "language": "en"}))
        done = None
        chunks = 0
        for _ in range(400):
            msg = await asyncio.wait_for(ws.recv(), timeout=120)
            if isinstance(msg, (bytes, bytearray)):
                continue
            data = json.loads(msg)
            if data.get("type") == "aiResponseChunk":
                chunks += 1
            if data.get("type") == "aiResponseDone":
                done = data
                break
        print("chunks", chunks)
        print("full", (done or {}).get("fullText", ""))
        print("done", bool(done))


if __name__ == "__main__":
    asyncio.run(main())
