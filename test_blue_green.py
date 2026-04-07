import requests
import time
import os
import json
import sys
import codecs
sys.stdout = codecs.getwriter("utf-8")(sys.stdout.detach())

LOGIN_URL = "http://127.0.0.1:7001/login"
UPLOAD_URL = "http://127.0.0.1:7000/upload_rag"
DELETE_URL = "http://127.0.0.1:7000/rag/delete"
# The debug endpoint
QUERY_URL = "http://127.0.0.1:7000/rag/retrieve-debug"
if not os.path.exists("C:/Users/MK/Desktop/Notes/PDF/Principles_of_Management.pdf"):
    print("Files not found")

session = requests.Session()
# 1. Login
response = session.post(LOGIN_URL, data={"username": "admin", "password": "admin123"})
if response.status_code != 200:
    print(f"Login failed: {response.status_code} {response.text}")
else:
    print("Login successful.")

def get_headers():
    csrf = session.cookies.get("csrf_token")
    return {"x-csrf-token": csrf} if csrf else {}

def upload_pdf(filepath):
    print(f"Uploading {filepath}...")
    with open(filepath, 'rb') as f:
        files = {'file': (os.path.basename(filepath), f, 'application/pdf')}
        r = session.post(UPLOAD_URL, files=files, headers=get_headers())
        print(f"Status: {r.status_code}")
        try:
            print(r.json())
        except:
            print(r.text)

def query_rag(q):
    print(f"Querying: {q}")
    r = session.get(QUERY_URL, params={"query": q, "top_k": 3}, headers=get_headers())
    if r.status_code == 200:
         res = r.json()
         docs = res.get("documents", [])
         print(f"  -> Found {len(docs)} documents.")
         if docs:
            print(f"  -> Top match snippet: {docs[0]['text'][:200]}...")
         else:
            print("  -> NO MATCHES.")
    else:
         print(f"Query failed: {r.status_code} {r.text}")

print("--- Testing Philosophy ---")
p_pdf = "C:/Users/MK/Desktop/Notes/PDF/Introduction_to_Philosophy-WEB_cszrKYp-compressed.pdf"
upload_pdf(p_pdf)
print("Waiting 10s for RAG server to fully index and sync...")
time.sleep(10)

queries_p = [
    "What is this document about?",
    "List all chapters in the book",
    "What is Chapter 6 about?",
    "What are the sections in Chapter 7?",
    "What does this document say about machine learning?"
]
for q in queries_p:
    query_rag(q)

print("\n--- Testing Management ---")
m_pdf = "C:/Users/MK/Desktop/Notes/PDF/Principles_of_Management.pdf"
upload_pdf(m_pdf)
print("Waiting 10s for RAG server to fully index and sync...")
time.sleep(10)

queries_m = [
    "What is this document about?",
    "List all units in the book",
    "What are the six Ms of management?",
    "What is discussed in Unit 4?",
    "What does this document say about machine learning?"
]
for q in queries_m:
    query_rag(q)
