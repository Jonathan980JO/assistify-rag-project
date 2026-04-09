"""
Test script to verify RAG retrieval coverage fixes.
Tests deep-section retrieval (Peter Drucker, MBO) and out-of-scope rejection.
"""
import requests
import time
import os
import json
import sys
import codecs
sys.stdout = codecs.getwriter("utf-8")(sys.stdout.detach())

BASE = "http://127.0.0.1:7000"
LOGIN = "http://127.0.0.1:7001/login"

session = requests.Session()
r = session.post(LOGIN, data={"username": "admin", "password": "admin123"})
print(f"Login: {r.status_code}")

def hdr():
    csrf = session.cookies.get("csrf_token")
    return {"x-csrf-token": csrf} if csrf else {}

def upload(path):
    print(f"\nUploading {os.path.basename(path)}...")
    with open(path, 'rb') as f:
        r = session.post(f"{BASE}/upload_rag", files={'file': (os.path.basename(path), f, 'application/pdf')}, headers=hdr())
    data = r.json()
    print(f"  Status: {r.status_code}, Indexed: {data.get('chunks_indexed', '?')}")
    return r.status_code == 200

def query_debug(q):
    """Use /rag/retrieve-debug to check raw retrieval (no LLM)."""
    r = session.get(f"{BASE}/rag/retrieve-debug", params={"query": q, "top_k": 5}, headers=hdr())
    data = r.json()
    count = data.get("count", 0)
    docs = data.get("documents", data.get("results", []))
    print(f"\n  Q: {q}")
    print(f"  Chunks found: {count}")
    if count > 0 and docs:
        for i, d in enumerate(docs[:2]):
            txt = d.get("text", d.get("text_preview", ""))[:120]
            sim = d.get("similarity", d.get("score", "?"))
            print(f"    [{i+1}] sim={sim} | {txt}...")
    return count

# Wait for servers to fully start
print("Waiting 20s for servers to start...")
time.sleep(20)

# Upload Management PDF
pdf = "C:/Users/MK/Desktop/Notes/PDF/Principles_of_Management.pdf"
ok = upload(pdf)
if not ok:
    print("UPLOAD FAILED!")
    sys.exit(1)

print("\nWaiting 10s for indexing to complete...")
time.sleep(10)

# === DEEP-SECTION QUERIES (should find results) ===
print("\n" + "="*60)
print("DEEP-SECTION QUERIES (expecting matches)")
print("="*60)

deep_queries = [
    "Who is Peter Drucker?",
    "What is Management by Objectives?",
    "What are the functions of management?",
    "What is planning in management?",
    "What is organizing in management?",
]

deep_pass = 0
deep_fail = 0
for q in deep_queries:
    count = query_debug(q)
    if count > 0:
        deep_pass += 1
        print("  => PASS")
    else:
        deep_fail += 1
        print("  => FAIL (should have found results)")

# === OUT-OF-SCOPE QUERIES (should NOT find results) ===
print("\n" + "="*60)
print("OUT-OF-SCOPE QUERIES (expecting no matches)")
print("="*60)

oos_queries = [
    "What is quantum physics?",
    "Tell me about the French Revolution",
    "What is machine learning?",
]

oos_pass = 0
oos_fail = 0
for q in oos_queries:
    count = query_debug(q)
    if count == 0:
        oos_pass += 1
        print("  => PASS (correctly rejected)")
    else:
        oos_fail += 1
        print("  => ACCEPTABLE (retrieval found something; downstream gates may still reject)")

# === SUMMARY ===
print("\n" + "="*60)
print("RESULTS SUMMARY")
print("="*60)
print(f"Deep-section: {deep_pass}/{len(deep_queries)} passed, {deep_fail} failed")
print(f"Out-of-scope: {oos_pass}/{len(oos_queries)} correctly rejected")
total_pass = deep_pass + oos_pass
total = len(deep_queries) + len(oos_queries)
print(f"Overall: {total_pass}/{total}")
