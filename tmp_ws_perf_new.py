import httpx
import time
import asyncio
import json
import websockets

queries = [
    "What is psychology?",
    "Who founded the first psychological laboratory and when?",
    "Give only psychology goals",
    "What is the capital of France?",
]

async def test_websocket():
    url = "ws://localhost:7000/ws"
    
    # We need to simulate the login to get connection, but maybe we can just hit the text query endpoint via HTTP?
    # RAG Server: POST /query

    base_url = "http://localhost:7000/query"

    # From ACTUAL_SYSTEM_IMPLEMENTATION.md:
    # Query endpoint needs user login, wait.
    # Actually, RAG server on 7000 might not have auth for /query if we bypass proxy, or maybe it does have Depends(require_login())
    # Wait, the RAG server is 7000, Login server is 7001.
    pass

async def test_http(client, token, csrf, text):
    headers = {
        "x-csrf-token": csrf,
        "Cookie": f"session={token}; csrf_token={csrf}"
    }
    data = {"text": text}
    
    start = time.perf_counter()
    r = await client.post("http://localhost:7001/query", data=data, headers=headers)
    end = time.perf_counter()
    res = r.json() if r.status_code == 200 else r.text
    return end - start, res

if __name__ == "__main__":
    print("Testing...")
