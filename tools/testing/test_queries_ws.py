import asyncio
import websockets
import json
import time
import sys

async def test_query(uri, question):
    print(f"\nTesting query: '{question}'")
    try:
        async with websockets.connect(uri) as websocket:
            start_time = time.time()
            # The server expects a JSON with "text" field
            await websocket.send(json.dumps({"text": question}))
            
            full_response = ""
            while True:
                try:
                    msg = await asyncio.wait_for(websocket.recv(), timeout=120.0)
                    if isinstance(msg, bytes):
                        # Audio byte chunks from TTS - ignore
                        continue
                    
                    data = json.loads(msg)
                    
                    if data.get("type") == "aiResponseChunk":
                        chunk = data.get("text", "")
                        full_response += chunk
                    
                    if data.get("type") == "aiResponseDone":
                        if "fullText" in data:
                            full_response = data["fullText"]
                        break
                        
                    if "error" in data:
                        print(f"Error from server: {data['error']}")
                        break
                        
                except asyncio.TimeoutError:
                    print("\nTimeout waiting for response!")
                    break
            
            duration = time.time() - start_time
            print(f"Response received in {duration:.2f}s")
            print("-" * 20)
            print(f"Full Response:\n{full_response}")
            print("-" * 20)
            
            if "[COUNT BOOST]" in full_response:
                print("FAIL: Found '[COUNT BOOST]' in response.")
            else:
                print("PASS: '[COUNT BOOST]' NOT found in response.")
                
            return full_response
            
    except Exception as e:
        print(f"Connection failed: {e}")
        return None

async def main():
    uri = "ws://localhost:7000/ws"
    
    questions = [
        "What are the six Ms of management?",
        "What is scientific management?"
    ]
    
    for q in questions:
        await test_query(uri, q)

if __name__ == "__main__":
    asyncio.run(main())
