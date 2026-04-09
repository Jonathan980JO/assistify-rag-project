import requests
from backend.assistify_rag_server import LiveRAGManager
from config import OLLAMA_HOST, OLLAMA_PORT, OLLAMA_MODEL

rag = LiveRAGManager()
queries = [
    "لخص الوحدة الأولى في ثلاث نقاط",
    "لخص الوحدة الثالثة في ثلاث نقاط",
    "ما هو تعريف الإدارة؟",
]

url = f"http://{OLLAMA_HOST}:{OLLAMA_PORT}/api/chat"

for query in queries:
    print("\n" + "=" * 80)
    print("QUERY:", query)

    results = rag.search(query, top_k=10, return_dicts=True)
    print("RETRIEVED_CHUNKS:", len(results))
    print("RETRIEVED_UNITS:", sorted(set(str((item.get("metadata") or {}).get("unit", "")) for item in results)))

    context = "\n\n".join([f"Chunk {idx+1}: {item['text']}" for idx, item in enumerate(results[:8])])
    prompt = (
        "Using ONLY this context:\n\n"
        f"{context}\n\n"
        "Answer in Arabic if the user query is Arabic.\n"
        f"User query: {query}"
    )

    payload = {
        "model": OLLAMA_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
    }

    response = requests.post(url, json=payload, timeout=180)
    data = response.json()
    answer = data.get("message", {}).get("content", "(no answer)")
    print("FINAL_ANSWER:", answer[:2000])
