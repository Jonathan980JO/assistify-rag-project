import asyncio
import websockets
import json

async def test_ws(query):
    uri = "ws://localhost:7000/ws"
    async with websockets.connect(uri) as websocket:
        # Send initial message (often needed to start the session or just send the query)
        # Based on typical RAG servers, we might just send the query or a json with 'message'
        await websocket.send(json.dumps({"message": query}))
        
        full_response = ""
        try:
            while True:
                message = await asyncio.wait_for(websocket.recv(), timeout=20.0)
                # Check for [COUNT BOOST] in the raw message
                if "[COUNT BOOST]" in message:
                    print(f"Error: Found [COUNT BOOST] in message: {message}")
                
                try:
                    data = json.loads(message)
                    if isinstance(data, dict):
                        if "text" in data:
                            full_response += data["text"]
                        elif "content" in data:
                            full_response += data["content"]
                        elif "message" in data:
                            full_response += data["message"]
                        
                        if data.get("type") == "end" or data.get("end_of_stream"):
                            break
                    else:
                        full_response += str(data)
                except json.JSONDecodeError:
                    full_response += message
        except asyncio.TimeoutError:
            print("Response timed out")
        except websockets.exceptions.ConnectionClosed:
            print("Connection closed")
        
        print(f"Query: {query}")
        print(f"Response: {full_response}")
        print("-" * 20)

async def main():
    await test_ws("What are the six Ms of management?")
    await test_ws("What is scientific management?")

if __name__ == '__main__':
    asyncio.run(main())
