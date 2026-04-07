import asyncio
import json
import time

from backend.assistify_rag_server import call_llm_with_rag

QUERIES = [
    "Steps in planning process",
    "Who is Frederick Taylor?",
    "hi",
]


async def run_pass(name: str):
    user = {"username": "perf_test", "role": "admin"}
    rows = []
    for index, query in enumerate(QUERIES, start=1):
        started = time.perf_counter()
        answer, docs = await call_llm_with_rag(query, f"{name}_{index}", user)
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        rows.append(
            {
                "query": query,
                "latency_ms": round(elapsed_ms, 1),
                "docs": len(docs or []),
                "answer_preview": (answer or "")[:160],
            }
        )
    return rows


async def main() -> None:
    user = {"username": "perf_test", "role": "admin"}

    await call_llm_with_rag("warmup", "perf_warmup", user)
    measured = await run_pass("perf")
    print(json.dumps(measured, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
