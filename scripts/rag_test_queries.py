import os
import sys

import requests

LOGIN_HOST = os.environ.get("LOGIN_HOST", "http://127.0.0.1:7001")
RAG_HOST = os.environ.get("RAG_HOST", "http://127.0.0.1:7000")

# Aligned with backend/load_documents.py support KB (not PDF book content)
KB_QUERIES = [
    "How many days do I have to return a product?",
    "How do I reset my password?",
    "When is shipping free?",
    "What payment methods do you accept?",
    "What are your customer support hours?",
]

s = requests.Session()
r = s.post(
    f"{LOGIN_HOST}/login",
    data={"username": "admin", "password": "admin"},
    allow_redirects=False,
    timeout=20,
)
print("login", r.status_code)
if r.status_code not in (302, 303):
    print("login failed:", r.text[:500])
    sys.exit(1)

# Search full KB (do not restrict to a single uploaded PDF)
mode_resp = s.post(
    f"{RAG_HOST}/rag/doc-mode",
    json={"mode": "multi", "active_sources": []},
    timeout=20,
)
print("doc-mode", mode_resp.status_code, mode_resp.json() if mode_resp.ok else mode_resp.text[:200])

failed = 0
for q in KB_QUERIES:
    resp = s.post(f"{RAG_HOST}/query", json={"text": q}, timeout=120)
    print("---")
    print("Q:", q)
    print("status", resp.status_code)
    try:
        body = resp.json()
        print("A:", body)
        answer = ""
        if isinstance(body, dict):
            answer = str(body.get("response") or body.get("answer") or body.get("text") or "")
        if resp.status_code != 200:
            failed += 1
        elif "not found in the document" in answer.lower():
            failed += 1
            print("FAIL: empty KB match")
    except Exception:
        print(resp.text)
        failed += 1

sys.exit(1 if failed else 0)
