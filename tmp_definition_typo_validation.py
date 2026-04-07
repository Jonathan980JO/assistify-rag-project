import requests, time, json
s = requests.Session()
_ = s.post("http://127.0.0.1:7001/login", data={"username": "admin", "password": "admin123"}, timeout=30)
csrf = s.cookies.get("csrf_token")
headers = {"x-csrf-token": csrf} if csrf else {}
queries = ["what is mangment in general", "what is management in general"]
results = []
for q in queries:
    t0 = time.perf_counter()
    r = s.post("http://127.0.0.1:7000/query", json={"text": q}, headers=headers, timeout=180)
    latency_ms = (time.perf_counter() - t0) * 1000.0
    if r.ok:
        answer = (r.json() or {}).get("answer", "")
    else:
        answer = f"HTTP {r.status_code}: {r.text[:240]}"
    results.append({"query": q, "latency_ms": round(latency_ms, 2), "answer": answer})
print(json.dumps(results, ensure_ascii=False, indent=2))
