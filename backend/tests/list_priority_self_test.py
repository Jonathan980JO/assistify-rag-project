import io
import json
import re
from contextlib import redirect_stdout, redirect_stderr

from backend import assistify_rag_server as ars

QUERIES = [
    "List the six goals of psychology",
    "What are the components of the ABC model",
    "What are the steps of the scientific method",
    "Describe Piaget’s stages",
    "What needs must be met before self-actualization",
]


def _is_valid_structured_answer(answer: str) -> bool:
    text = str(answer or "").strip()
    if not text or text == ars.RAG_NO_MATCH_RESPONSE:
        return False
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return False
    bullet_like = [ln for ln in lines if re.match(r"^\s*(?:[-•*]|\d+[.)])\s+", ln)]
    if len(bullet_like) >= 2:
        return True
    if len(lines) >= 2:
        return True
    return False


def run_self_test() -> dict:
    results = []
    pass_count = 0

    for q in QUERIES:
        sink = io.StringIO()
        with redirect_stdout(sink), redirect_stderr(sink):
            raw_docs = ars._search_with_query_expansion(
                q,
                top_k=8,
                distance_threshold=ars._distance_threshold_for_query(q),
                return_dicts=True,
                enable_rerank=True,
            ) or []
            docs = ars._prepare_rag_doc_dicts_shared(raw_docs, q)
            if docs:
                docs = ars._rerank_docs_for_query_intent(q, docs)
            decision = ars._shared_rag_final_answer_decision(q, docs, llm_text=None)
            context_chunks = [
                str((d or {}).get("page_content") or (d or {}).get("text") or "")
                for d in docs
            ]
            extracted_items = ars._extract_structured_list_from_context(context_chunks, query_text=q) or []

        answer = decision.get("answer")
        ok = _is_valid_structured_answer(answer)
        if ok:
            pass_count += 1

        results.append(
            {
                "query": q,
                "retrieved_chunks": [
                    re.sub(r"\s+", " ", str((d or {}).get("page_content") or (d or {}).get("text") or ""))[:240]
                    for d in docs[:8]
                ],
                "extracted_items": extracted_items,
                "final_decision": {
                    "used_llm": bool(decision.get("used_llm")),
                    "answer_type": decision.get("answer_type"),
                    "answer": answer,
                },
                "valid_structured": ok,
            }
        )

    total = len(QUERIES)
    success_rate = (pass_count / total) if total else 0.0
    return {
        "total": total,
        "passed": pass_count,
        "success_rate": round(success_rate, 3),
        "results": results,
    }


if __name__ == "__main__":
    report = run_self_test()
    print(json.dumps(report, ensure_ascii=False, indent=2))
