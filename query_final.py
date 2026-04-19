import asyncio
import websockets
import json
import sys

questions = [
    "What are the characteristics of management?",
    "What are the steps in the planning process?",
    "What is scientific management?",
    "What are the six Ms of management?",
    "What is quantum computing?"
]

async def query_server(question):
    uri = "ws://localhost:7000/ws"
    async with websockets.connect(uri) as websocket:
        await websocket.send(json.dumps({"text": question}))
        while True:
            try:
                message = await asyncio.wait_for(websocket.recv(), timeout=240)
                data = json.loads(message)
                if data.get("type") == "aiResponseDone":
                    return data.get("fullText")
            except asyncio.TimeoutError:
                return "Error: Timeout reached"
            except Exception as e:
                return f"Error: {str(e)}"

async def main():
    results = []
    for q in questions:
        print(f"=== Q: {q} ===")
        full_text = await query_server(q)
        print(full_text)
        print("=== END ===")
        results.append(f"=== Q: {q} ===\n{full_text}\n=== END ===")
    
    with open("scratch/mp_c5_after.txt", "w", encoding="utf-8") as f:
        f.write("\n\n".join(results))

if __name__ == "__main__":
    asyncio.run(main())
