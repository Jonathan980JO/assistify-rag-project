import requests
session = requests.Session()
response = session.post("http://127.0.0.1:7001/login", data={"username": "admin", "password": "admin123"})
csrf = session.cookies.get("csrf_token")
headers = {"x-csrf-token": csrf} if csrf else {}

print("Checking Philosophy book query...")
r = session.get("http://127.0.0.1:7000/rag/retrieve-debug", params={"query": "philosophy means love of wisdom", "top_k": 3}, headers=headers)
print(r.status_code)
res = r.json()
print("Count:", res.get("count"))
if res.get("count", 0) > 0:
    entries = res.get("entries") or res.get("results") or []
    for e in entries:
        print(f"Dist: {e.get('distance')} | Text: {e.get('text_preview')}")
