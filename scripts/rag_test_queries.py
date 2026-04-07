import requests
from pathlib import Path

LOGIN_HOST = "http://127.0.0.1:7001"
RAG_HOST = "http://127.0.0.1:7000"

s = requests.Session()
# Login as admin
r = s.post(f"{LOGIN_HOST}/login", data={'username':'admin','password':'admin'}, allow_redirects=False, timeout=20)
print('login', r.status_code)

queries = [
    "What is this document about?",
    "List all units in the book",
    "What are the six Ms of management?",
    "What is discussed in Unit 4?",
    "What does this document say about machine learning?"
]

for q in queries:
    resp = s.post(f"{RAG_HOST}/query", json={'text': q}, timeout=60)
    print('---')
    print('Q:', q)
    print('status', resp.status_code)
    try:
        print('A:', resp.json())
    except Exception:
        print(resp.text)
