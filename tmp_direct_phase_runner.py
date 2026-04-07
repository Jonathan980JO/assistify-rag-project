import argparse
import asyncio
import json
import time
from datetime import datetime

from backend.assistify_rag_server import call_llm_with_rag

PHASE_1 = [
    "what is operant conditioning",
    "explain operant conditioning",
    "how does operant conditioning work",
    "what is structuralism",
    "explain structuralism",
    "what is reinforcement",
    "how does reinforcement work",
]

PHASE_2 = [
    "give an explanation of operant conditioning",
    "explain structuralism fully",
    "how does operant conditioning work in detail",
    "what is the goal of structuralism",
    "what is blockchain",
    "what is artificial intelligence",
]

PHASE_3 = [
    "what is conditioning",
    "explain conditioning",
    "types of conditioning",
    "what is classical conditioning",
    "what is operant conditioning",
    "difference between classical and operant conditioning",
]

PHASE_4 = [
    "what is reinforcement",
    "how does reinforcement work",
    "what is punishment",
    "explain punishment in psychology",
    "what is operant conditioning",
]

GLOBAL_PROTECTION = [
    "what is operant conditioning",
    "define operant conditioning",
    "explain operant conditioning",
    "how does operant conditioning work",
    "what is the idea behind operant conditioning",
    "what is structuralism",
    "define structuralism",
    "explain structuralism in psychology",
    "what does structuralism focus on",
    "what is punishment",
    "explain punishment in psychology",
    "what is classical conditioning",
    "difference between classical and operant conditioning",
    "compare classical and operant conditioning",
    "what is blockchain",
    "what is artificial intelligence",
]

SETS = {
    "phase1": PHASE_1,
    "phase2": PHASE_2,
    "phase3": PHASE_3,
    "phase4": PHASE_4,
    "global": GLOBAL_PROTECTION,
}


async def ask(query: str, idx: int) -> dict:
    started = time.perf_counter()
    error = None
    answer = ""
    docs_count = 0
    try:
        user = {"username": "phase_tester", "role": "tester"}
        answer, docs = await call_llm_with_rag(query, f"phase_eval_conn_{idx}", user)
        docs_count = len(docs) if docs else 0
    except Exception as exc:
        error = str(exc)

    elapsed_ms = round((time.perf_counter() - started) * 1000.0, 2)
    answer_clean = str(answer or "").strip()
    return {
        "query": query,
        "answer": answer_clean,
        "elapsed_ms": elapsed_ms,
        "docs_count": docs_count,
        "error": error,
        "not_found": answer_clean.lower() == "not found in the document.",
    }


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--set", choices=sorted(SETS.keys()), required=True)
    parser.add_argument("--tag", required=True)
    args = parser.parse_args()

    queries = SETS[args.set]
    out = {
        "ts": datetime.now().isoformat(),
        "set": args.set,
        "tag": args.tag,
        "results": [],
    }

    for i, q in enumerate(queries, start=1):
        r = await ask(q, i)
        out["results"].append(r)
        print(f"Q: {q}\nA: {r['answer']}\nNF: {r['not_found']} ERR: {r['error']} DOCS: {r['docs_count']}\n---")

    out_path = f"phase_eval_direct_{args.set}_{args.tag}_{int(time.time())}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(out_path)


if __name__ == "__main__":
    asyncio.run(main())
