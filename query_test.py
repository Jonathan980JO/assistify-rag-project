import asyncio
import websockets
import json

async def run_queries():
    uri = "ws://127.0.0.1:7000/ws"
    queries = [
        "What are the six Ms of management?",
        "What are the characteristics of management?",
        "What is scientific management?",
        "What are Fayol’s principles of management?",
        "What are the steps in the planning process?"
    ]
    
    try:
        async with websockets.connect(uri) as websocket:
            for query in queries:
                # Send the query in the format the server expects
                # Based on typical websocket LLM patterns, sending as text or JSON
                # If server expects a specific JSON format, we adjust. 
                # Common format: {"text": "query"} or just "query"
                # The task says "sends these exact queries"
                await websocket.send(query)
                
                full_text = ""
                while True:
                    try:
                        message = await websocket.recv()
                        if isinstance(message, bytes):
                            continue
                        
                        try:
                            data = json.loads(message)
                            if isinstance(data, dict):
                                if data.get("type") == "aiResponseDone" or data.get("event") == "aiResponseDone":
                                    break
                                # Extract text if JSON
                                text = data.get("text", data.get("content", ""))
                                full_text += text
                            else:
                                full_text += str(data)
                        except json.JSONDecodeError:
                            # Not JSON, handle as plain text
                            if "aiResponseDone" in message:
                                # Sometimes it's a delimiter in text
                                break
                            full_text += message
                    except websockets.exceptions.ConnectionClosed:
                        break
                
                print(f"Q: {query}")
                print(f"A: {full_text.strip()}")
                print("---")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(run_queries())
