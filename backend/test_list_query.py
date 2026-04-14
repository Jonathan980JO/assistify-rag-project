import asyncio
import websockets
import json

async def test_query(query_text):
    uri = "ws://127.0.0.1:7000/ws"
    async with websockets.connect(uri) as websocket:
        # Send the query with correct message format
        await websocket.send(json.dumps({"text": query_text}))
        
        # Collect responses
        responses = []
        full_text = ""
        try:
            while True:
                response = await asyncio.wait_for(websocket.recv(), timeout=30.0)
                data = json.loads(response)
                responses.append(data)
                
                if data.get("type") == "aiResponseChunk":
                    full_text += data.get("text", "")
                elif data.get("type") == "aiResponseDone":
                    full_text = data.get("fullText", full_text)
                    break
        except asyncio.TimeoutError:
            print("Timeout waiting for response")
        except websockets.exceptions.ConnectionClosed:
            pass
        
    return full_text, responses

if __name__ == "__main__":
    query = "List the goals of psychology"
    print(f"\n{'='*60}")
    print(f"Testing: {query}")
    print(f"{'='*60}\n")
    
    full_text, responses = asyncio.run(test_query(query))
    
    print(f"\n{'='*60}")
    print("FINAL RESULT:")
    print(f"{'='*60}")
    print(full_text)
    print(f"\n{'='*60}")
