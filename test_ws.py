import asyncio
import websockets
import json
import sys

async def query_questions():
    uri = "ws://127.0.0.1:7000/ws"
    questions = [
        "What are the six Ms of management?",
        "What are the characteristics of management?",
        "What is scientific management?",
        "What are Fayol’s principles of management?",
        "What are the steps in the planning process?",
        "What is management?",
        "What is planning?"
    ]
    
    try:
        async with websockets.connect(uri) as websocket:
            for q in questions:
                print(f"Q: {q}")
                await websocket.send(json.dumps({"question": q}))
                full_answer = ""
                while True:
                    try:
                        message = await websocket.recv()
                        if isinstance(message, bytes):
                            continue
                        data = json.loads(message)
                        if "answer" in data:
                            full_answer += data["answer"]
                        if data.get("aiResponseDone"):
                            break
                    except Exception:
                        break
                print(f"A: {full_answer.strip()}")
                print("---")
                sys.stdout.flush()
    except Exception as e:
        print(f"Connection Error: {e}")

if __name__ == "__main__":
    asyncio.run(query_questions())
