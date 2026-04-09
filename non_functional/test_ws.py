import asyncio
import websockets
import json
import requests
import time
import os

async def main():
    print("Logging in...")
    s = requests.Session()
    r = s.post('http://127.0.0.1:7001/login', data={'username':'admin', 'password':'admin123'})
    if r.status_code != 200:
        print("Login failed")
        return
    cookie = r.cookies.get_dict().get("session") or s.cookies.get("session")
    headers = {"Cookie": f"session={cookie}"} if cookie else {}

    def upload_pdf(filepath):
        print(f"Uploading {filepath}...")
        with open(filepath, 'rb') as f:
            files = {'file': (os.path.basename(filepath), f, 'application/pdf')}
            csrf = s.cookies.get("csrf_token")
            h = {"x-csrf-token": csrf} if csrf else {}
            res = s.post("http://127.0.0.1:7000/upload_rag", files=files, headers=h)
            print(f"Status: {res.status_code}")
            
    async def chat(query):
        print(f"\nQuery: {query}")
        try:
            async with websockets.connect("ws://127.0.0.1:7000/ws", extra_headers=headers) as websocket:
                await websocket.send(json.dumps({"text": query}))
                full_reply = ""
                while True:
                    try:
                        msg = await asyncio.wait_for(websocket.recv(), timeout=10.0)
                        data = json.loads(msg)
                        if data.get("type") == "final" or data.get("type") == "end_of_turn":
                            break
                        if data.get("type") == "text":
                            text_chunk = data.get("text", "")
                            full_reply += text_chunk
                    except asyncio.TimeoutError:
                        break
                    except websockets.exceptions.ConnectionClosed:
                        break
                with open("results_ws.txt", "a", encoding="utf-8") as out:
                    out.write(f"\nQuery: {query}\nAnswer: {full_reply.strip() or 'No answer received.'}\n")
                print(f"Answer: {full_reply.strip() or 'No answer received.'}")
        except Exception as e:
            print(f"WS error: {e}")

    # clear file
    open("results_ws.txt", "w", encoding="utf-8").write("")
    print("--- Testing Philosophy ---")
    p_pdf = "C:/Users/MK/Desktop/Notes/PDF/Introduction_to_Philosophy-WEB_cszrKYp-compressed.pdf"
    upload_pdf(p_pdf)
    print("Waiting 10s...")
    time.sleep(10)
    
    queries_p = [
        "What is this document about?",
        "List all chapters in the book",
        "What is Chapter 6 about?",
        "What are the sections in Chapter 7?",
        "What does this document say about machine learning?"
    ]
    for q in queries_p:
        await chat(q)

    print("\n--- Testing Management ---")
    m_pdf = "C:/Users/MK/Desktop/Notes/PDF/Principles_of_Management.pdf"
    upload_pdf(m_pdf)
    print("Waiting 10s...")
    time.sleep(10)
    
    queries_m = [
        "What is this document about?",
        "List all units in the book",
        "What are the six Ms of management?",
        "What is discussed in Unit 4?",
        "What does this document say about machine learning?"
    ]
    for q in queries_m:
        await chat(q)

if __name__ == "__main__":
    asyncio.run(main())
