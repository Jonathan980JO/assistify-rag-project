import asyncio
import websockets
import json

async def query_websocket(question):
    uri = "ws://localhost:7000/ws"
    try:
        async with websockets.connect(uri) as websocket:
            payload = {
                "clientId": "test_client",
                "message": question,
                "userId": "test_user",
                "collectionName": "default"
            }
            await websocket.send(json.dumps(payload))
            
            full_text = ""
            while True:
                try:
                    message = await websocket.recv()
                    data = json.loads(message)
                    if data.get("type") == "aiResponseDone":
                        full_text = data.get("fullText", "")
                        break
                except websockets.exceptions.ConnectionClosed:
                    break
            return full_text
    except Exception as e:
        return f"Error: {str(e)}"

async def main():
    questions = [
        "What are the six Ms of management?",
        "What are the characteristics of management?",
        "What is scientific management?",
        "What are Fayol’s principles of management?",
        "What are the steps in the planning process?",
        "What is management?",
        "What is planning?"
    ]
    
    for q in questions:
        print(f"Q: {q}")
        answer = await query_websocket(q)
        print(f"A: {answer}\n" + "-"*50)

if __name__ == '__main__':
    asyncio.run(main())
