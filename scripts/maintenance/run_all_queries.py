import asyncio
import websockets
import json
import time

async def test_query(uri, question):
    # Try both 'text' and 'query' payload keys since scripts differ
    for payload_key in ['text', 'query']:
        try:
            async with websockets.connect(uri) as websocket:
                payload = {payload_key: question}
                await websocket.send(json.dumps(payload))
                
                full_response = ""
                while True:
                    try:
                        msg = await asyncio.wait_for(websocket.recv(), timeout=30.0)
                        if isinstance(msg, bytes):
                            continue
                        
                        data = json.loads(msg)
                        
                        # Handle varied response formats
                        if data.get("type") == "aiResponseChunk":
                            chunk = data.get("text", "")
                            full_response += chunk
                        
                        if data.get("type") == "aiResponseDone":
                            if "fullText" in data:
                                full_response = data["fullText"]
                            break
                        
                        if "fullText" in data and data.get("type") is None:
                             full_response = data["fullText"]
                             break
                             
                        if "error" in data:
                            break
                            
                    except asyncio.TimeoutError:
                        break
                
                if full_response:
                    return full_response
        except Exception:
            continue
    return "FAILED TO GET RESPONSE"

async def main():
    uri = "ws://localhost:7000/ws"
    
    questions = [
        "What are the characteristics of management?",
        "What are the steps in the planning process?",
        "What is scientific management?",
        "What are the six Ms of management?",
        "What is quantum computing?"
    ]
    
    print("STARTING TEST QUERIES")
    for q in questions:
        res = await test_query(uri, q)
        print(f"QUERY: {q}")
        print(f"REPORT_ANSWER: {res}")
        print("---")

if __name__ == "__main__":
    asyncio.run(main())
