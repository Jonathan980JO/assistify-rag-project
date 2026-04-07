import asyncio
import time
import json
from backend.assistify_rag_server import call_llm_with_rag

QUERIES = [
    "what is meant by classical approach",
    "what is scientific management",
    "what is bureaucracy",
    "what is administrative theory",
    "tell me about management principles",
]


async def main():
    results = []
    user = {"username": "tester", "role": "tester"}
    for i, q in enumerate(QUERIES, start=1):
        print("\n=== QUERY %s ===" % i)
        print(q)
        try:
            answer, docs = await call_llm_with_rag(q, f"run_queries_conn_{i}", user)
            print("--- ANSWER ---")
            print(answer)
            results.append({"query": q, "answer": answer, "docs_count": len(docs) if docs else 0})
        except Exception as e:
            print("ERROR while running query:", e)
            results.append({"query": q, "error": str(e)})
        # small delay to avoid any rate/resource thrashing
        await asyncio.sleep(0.5)

    # Dump a JSON summary
    ts = int(time.time())
    out_path = f"run_queries_results_{ts}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print("\nWROTE:", out_path)


if __name__ == '__main__':
    asyncio.run(main())
