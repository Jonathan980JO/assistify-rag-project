import asyncio, json, websockets

async def main():
    q = "how does operant conditioning work"
    uri = "ws://127.0.0.1:7000/ws"
    out = ""
    try:
        async with websockets.connect(uri, max_size=8_000_000) as ws:
            await ws.send(json.dumps({"text": q}))
            while True:
                raw = await asyncio.wait_for(ws.recv(), timeout=120)
                if isinstance(raw, bytes):
                    continue
                p = json.loads(raw)
                t = p.get("type")
                if t == "aiResponseChunk":
                    out += p.get("text", "")
                elif t == "aiResponse":
                    out = p.get("text", "") or out
                    break
                elif t == "aiResponseDone":
                    out = p.get("fullText", "") or out
                    break
                elif p.get("error"):
                    print("ERROR", p)
                    break
        print("ANSWER", out.strip())
    except Exception as e:
        print("EXC", repr(e))

asyncio.run(main())
