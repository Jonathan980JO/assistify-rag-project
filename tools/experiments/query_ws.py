import asyncio
import websockets
import json

async def query_server():
    uri = "ws://localhost:7000/ws"
    try:
        async with websockets.connect(uri) as websocket:
            query = {"query": "What are the characteristics of management?"}
            await websocket.send(json.dumps(query))
            
            while True:
                try:
                    message = await asyncio.wait_for(websocket.recv(), timeout=240.0)
                    data = json.loads(message)
                    if "fullText" in data:
                        print(data["fullText"])
                        break
                    # If the server sends other messages, we might need to handle them or continue waiting
                except asyncio.TimeoutError:
                    print("Timeout waiting for response")
                    break
    except Exception as e:
        print(f"Error: {e}")

asyncio.run(query_server())
