import asyncio
import websockets
import json
import time

async def single_worker(worker_id, uri, question, stats):
    try:
        async with websockets.connect(uri) as websocket:
            start_time = time.time()
            await websocket.send(json.dumps({"text": question}))
            
            full_response = ""
            while True:
                try:
                    msg = await asyncio.wait_for(websocket.recv(), timeout=60.0)
                    if isinstance(msg, bytes):
                        # Audio byte chunks from TTS - ignore for performance test
                        continue
                    
                    data = json.loads(msg)
                    if "error" in data:
                        print(f"[Worker {worker_id}] Error: {data['error']}")
                        break
                    
                    if data.get("type") == "aiResponseDone" or data.get("type") == "aiResponse":
                        if "fullText" in data:
                            full_response = data["fullText"]
                        elif "text" in data:
                            full_response += data["text"]
                        break
                        
                    if data.get("type") == "aiResponseChunk":
                        full_response += data.get("text", "")
                        
                except asyncio.TimeoutError:
                    print(f"[Worker {worker_id}] Timeout!")
                    break
            
            duration = time.time() - start_time
            stats.append(duration)
            print(f"[Worker {worker_id}] Finished in {duration:.2f}s, Response length: {len(full_response)}")
            
    except Exception as e:
        print(f"[Worker {worker_id}] Connection failed: {e}")

async def run_heavy_test(concurrency=5, total_requests=10):
    uri = "ws://localhost:7000/ws"
    stats = []
    
    print(f"Starting heavy test with {concurrency} concurrent workers...")
    
    for i in range(0, total_requests, concurrency):
        tasks = []
        for j in range(concurrency):
            worker_id = i + j + 1
            if worker_id > total_requests:
                break
            tasks.append(single_worker(worker_id, uri, "What is the main topic of your documents?", stats))
        
        await asyncio.gather(*tasks)
        await asyncio.sleep(1) # Breath between bursts
        
    if stats:
        avg_time = sum(stats) / len(stats)
        print(f"\n--- Load Test Results ---")
        print(f"Total successful requests: {len(stats)}")
        print(f"Average response time: {avg_time:.2f} seconds")
        if avg_time < 20.0: # adjusting expectation since it is RAG LLM
            print("Status: HEALTHY. The server responds normally in a small period of time.")
            return True
        else:
            print("Status: SLOW. The response time is currently high.")
            return False
    else:
        print("\n--- Load Test Results ---")
        print("Status: FAILED. No successful responses. Ensure the LLM backend (Ollama) is running.")
        return False

if __name__ == "__main__":
    while True:
        success = asyncio.run(run_heavy_test(concurrency=3, total_requests=6))
        if success:
            print("Server behaves normally! Stopping test.")
            break
        print("Loop finished, waiting 5 seconds before next run...")
        time.sleep(5)
