"""Test the full RAG pipeline for the goals query"""
import sys
sys.path.insert(0, r'G:\Grad_Project\assistify-rag-project-main')

import asyncio
import websockets
import json
import logging

# Enable verbose logging
logging.basicConfig(level=logging.DEBUG, format='%(levelname)s: %(message)s')

async def test_query_with_logs(query_text):
    uri = "ws://127.0.0.1:7000/ws"
    async with websockets.connect(uri) as websocket:
        # Send the query
        await websocket.send(json.dumps({"text": query_text}))
        
        # Collect responses
        full_text = ""
        try:
            while True:
                response = await asyncio.wait_for(websocket.recv(), timeout=30.0)
                data = json.loads(response)
                
                if data.get("type") == "aiResponseChunk":
                    full_text += data.get("text", "")
                elif data.get("type") == "aiResponseDone":
                    full_text = data.get("fullText", full_text)
                    break
        except asyncio.TimeoutError:
            print("Timeout waiting for response")
        except websockets.exceptions.ConnectionClosed:
            pass
        
    return full_text

if __name__ == "__main__":
    query = "List the goals of psychology"
    print(f"\n{'='*60}")
    print(f"Testing: {query}")
    print(f"{'='*60}\n")
    
    full_text = asyncio.run(test_query_with_logs(query))
    
    print(f"\n{'='*60}")
    print("FINAL RESULT:")
    print(f"{'='*60}")
    print(full_text)
    print(f"\n{'='*60}")
