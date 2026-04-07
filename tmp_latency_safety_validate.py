import asyncio
import json
import time

import backend.assistify_rag_server as srv

QUERIES = [
    "Who is Frederick Taylor?",
    "What is administrative management?",
    "What is bureaucracy?",
    "Steps in planning process",
    "hi",
]


async def run_one(query: str, connection_id: str):
    started = time.perf_counter()
    answer, docs = await srv.call_llm_with_rag(query, connection_id, {"username": "perf", "role": "admin"})
    total_ms = (time.perf_counter() - started) * 1000.0
    stages = dict(srv._LAST_LATENCY_BREAKDOWN.get(connection_id, {}))
    if not stages:
        stages = {
            "retrieval_ms": 0.0,
            "extraction_ms": 0.0,
            "validation_ms": 0.0,
            "llm_ms": 0.0,
            "total_ms": total_ms,
            "cache_hit": False,
        }
    stage_pairs = [
        ("retrieval_ms", float(stages.get("retrieval_ms", 0.0) or 0.0)),
        ("extraction_ms", float(stages.get("extraction_ms", 0.0) or 0.0)),
        ("validation_ms", float(stages.get("validation_ms", 0.0) or 0.0)),
        ("llm_ms", float(stages.get("llm_ms", 0.0) or 0.0)),
    ]
    slowest_stage, slowest_ms = max(stage_pairs, key=lambda x: x[1])
    return {
        "query": query,
        "total_latency_ms": round(float(stages.get("total_ms", total_ms)), 1),
        "slowest_stage": slowest_stage,
        "slowest_stage_ms": round(slowest_ms, 1),
        "breakdown": {k: round(float(v or 0.0), 1) for k, v in stages.items()},
        "docs": len(docs or []),
        "answer": (answer or "")[:220],
    }


async def main():
    # warm state priming
    await srv.call_llm_with_rag("warmup", "perf_warmup_0", {"username": "perf", "role": "admin"})

    out = []
    for idx, q in enumerate(QUERIES, start=1):
        out.append(await run_one(q, f"perf_q_{idx}"))

    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
