import asyncio
import websockets
import json

async def test_query(query):
    uri = "ws://localhost:7000/ws"
    try:
        async with websockets.connect(uri) as ws:
            await ws.send(json.dumps({"text": query}))
            full_text = ""
            while True:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=120)
                    data = json.loads(msg)
                    if data.get("type") == "aiResponseDone":
                        full_text = data.get("fullText", "")
                        break
                    elif data.get("type") == "error":
                        full_text = f"ERROR: {data}"
                        break
                except asyncio.TimeoutError:
                    full_text = "TIMEOUT"
                    break
    except Exception as e:
        full_text = f"CONNECTION ERROR: {e}"
    return full_text

async def main():
    queries = [
        "What are the six Ms of management?",
        "What are the characteristics of management?",
        "What are Fayol's principles of management?",
    ]
    for q in queries:
        print(f"\n{'=' * 60}")
        print(f"QUERY: {q}")
        print(f"{'=' * 60}")
        result = await test_query(q)
        print(f"ANSWER:\n{result}")
        print(f"{'=' * 60}")

asyncio.run(main())