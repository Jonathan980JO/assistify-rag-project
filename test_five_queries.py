import asyncio
import time
from backend.assistify_rag_server import live_rag, call_llm_streaming, startup_event, shutdown_event

class MockWebsocket:
    async def send_json(self, data):
        if data.get("type") == "aiResponseDone":
            self.final_data = data
            print("\nFINAL:", data["fullText"])
            print("LATENCY:", data.get("latency", {}))
        elif data.get("type") == "aiResponseChunk":
            # Just print the chunk length or something to know it's chunking
            pass

async def main():
    queries = [
        "What is philosophy?",
        "List ONLY the main branches of philosophy mentioned in the document.",
        "Who was Thales and what is he known for?",
        "What is the capital of Germany?",
        "Explain philosophy in one simple sentence."
    ]
    await startup_event()
    for q in queries:
        print("\n" + "="*50)
        print("QUERY:", q)
        ws = MockWebsocket()
        user = {"username": "test", "role": "admin"}
        try:
            await call_llm_streaming(ws, q, f"conn_{time.time()}", user)
        except Exception as e:
            print("ERROR", e)
    
    await shutdown_event()

if __name__ == "__main__":
    asyncio.run(main())
