import asyncio, json
import websockets

async def main():
    async with websockets.connect("ws://localhost:7000/ws", max_size=None, ping_interval=None) as ws:
        await ws.send(json.dumps({"text":"What are the characteristics of management?"}))
        while True:
            msg = await asyncio.wait_for(ws.recv(), timeout=240)
            if isinstance(msg, bytes):
                continue
            data = json.loads(msg)
            print(f"TYPE={data.get('type')} keys={list(data.keys())}")
            if data.get("type") == "aiResponseDone":
                print("--- fullText repr ---")
                print(repr(data.get("fullText")))
                print("--- sources ---")
                print(json.dumps(data.get("sources"), default=str, indent=2)[:1500])
                print("--- timing ---")
                print(json.dumps(data.get("timing"), default=str)[:400])
                # dump entire payload
                print("--- full payload (truncated) ---")
                print(json.dumps(data, default=str)[:3000])
                break

asyncio.run(main())
