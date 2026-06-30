#!/usr/bin/env python3
"""Read-only diagnostic harness for FDIC + Everyday Checking runtime paths.

Forces CPU so it does not contend with the live server's GPU. Uses the real
Chroma collection + the production retrieval/decision functions so the printed
route, chunks, scores, extraction and final answer match production behavior.

Usage:
    python scripts/diag_kb_queries.py
"""
from __future__ import annotations

import os

os.environ.setdefault("RAG_USE_GPU", "0")
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import backend.assistify_rag_server as srv


def _preview(text: str, limit: int = 240) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip())[:limit]


def diagnose(query: str) -> None:
    print("=" * 100)
    print(f"QUERY: {query}")
    print("-" * 100)

    family = srv._classify_query_family_v2(query)
    route = srv._resolve_grounded_answer_route(query)
    fact_type = srv._detect_fact_query_type(query)
    numeric = srv._is_numeric_fact_lookup_query(query)
    print(f"route_selected        = {route}")
    print(f"query_family_v2       = {family}")
    print(f"fact_query_type       = {fact_type}")
    print(f"is_numeric_fact_query = {numeric}")
    try:
        product_phrases = srv._table_fact_product_phrases(query)
        focus_tokens = srv._table_fact_focus_tokens(query)
        print(f"table_product_phrases = {product_phrases}")
        print(f"table_focus_tokens    = {focus_tokens}")
    except Exception as exc:
        print(f"table helpers error   = {exc}")

    docs = srv.live_rag.search(query, top_k=10, return_dicts=True, enable_rerank=True)
    docs = list(docs or [])
    print(f"\nretrieved_chunks      = {len(docs)} (top 10)")
    for i, d in enumerate(docs):
        meta = dict((d or {}).get("metadata") or {})
        dist = (d or {}).get("distance")
        rer = (d or {}).get("reranker_score")
        sim = (d or {}).get("similarity") or (d or {}).get("score")
        text = (d or {}).get("page_content") or (d or {}).get("text") or ""
        print(
            f"  [{i}] dist={dist} rerank={rer} sim={sim} "
            f"src={meta.get('source') or meta.get('filename')} ci={meta.get('chunk_index')}"
        )
        print(f"       {_preview(text, 200)}")

    try:
        table_ans = srv._extract_table_fact_answer(query, docs)
    except Exception as exc:
        table_ans = f"<error: {exc}>"
    print(f"\ntable_extraction      = {table_ans!r}")

    try:
        fact_ans = srv._extract_fact_route_answer(query, docs)
    except Exception as exc:
        fact_ans = f"<error: {exc}>"
    print(f"fact_route_answer     = {fact_ans!r}")

    decision = srv._shared_rag_final_answer_decision(query, docs, llm_text=None)
    print(f"\nanswer_type           = {decision.get('answer_type')}")
    print(f"source_mode           = {decision.get('source_mode')}")
    print(f"used_llm              = {decision.get('used_llm')}")
    print(f"FINAL_ANSWER          = {decision.get('answer')!r}")
    print()


def verify_all() -> None:
    """STEP 5 headless verification: greetings + Meridian + FDIC + Everyday."""
    import asyncio
    from backend.rag_query_prep import prepare_query_for_rag

    print("=" * 100)
    print("STEP 5 VERIFICATION")
    print("-" * 100)
    for g in ("hii", "hi", "hiii"):
        p = asyncio.run(prepare_query_for_rag(g))
        ok = bool(p.direct_response) and p.rag_query == ""
        print(f"  greeting {g!r:8} -> smalltalk={ok} response={str(p.direct_response)[:40]!r}")

    checks = {
        "What is the FDIC coverage limit?": "$250,000 per depositor, per ownership category",
        "What is the minimum balance requirement for Everyday Checking?": "$0 minimum balance",
    }
    for q, needle in checks.items():
        docs = list(srv.live_rag.search(q, top_k=10, return_dicts=True, enable_rerank=True) or [])
        decision = srv._shared_rag_final_answer_decision(q, docs, llm_text=None)
        ans = str(decision.get("answer") or "")
        ok = needle.lower() in ans.lower()
        print(f"  fact PASS={ok} q={q!r}")
        print(f"       answer={ans!r}")
    print()


def main() -> int:
    if "--verify" in sys.argv:
        verify_all()
        return 0
    queries = [
        "What is the FDIC coverage limit?",
        "What is the minimum balance requirement for Everyday Checking?",
    ]
    for q in queries:
        diagnose(q)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
