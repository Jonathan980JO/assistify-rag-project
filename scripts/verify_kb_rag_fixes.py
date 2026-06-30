#!/usr/bin/env python3
"""Verification harness for KB/RAG final RCA fixes."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.config_head import RAG_NO_MATCH_RESPONSE
from backend.assistify_rag_server import (
    _classify_smalltalk_intent,
    _resolve_grounded_answer_route,
    _shared_rag_final_answer_decision,
    classify_query_route,
)
from backend.rag_query_prep import prepare_query_for_rag

MERIDIAN_DOCS = [
    {
        "page_content": (
            "Meridian Financial Services is a regional bank offering personal and business banking.\n\n"
            "[TABLE DATA]\n"
            "Everyday Checking | $500 minimum balance | No monthly fee\n"
            "Premium Checking | $2,500 minimum balance | Waived fees\n\n"
            "Products include Everyday Checking, Premium Checking, savings accounts, and business loans.\n"
            "FDIC insurance covers deposits up to $250,000 per depositor, per insured bank."
        ),
        "metadata": {},
    }
]

QUERIES = [
    "hi",
    "hii",
    "hiii",
    "What is Meridian Financial Services?",
    "What products does Meridian offer?",
    "What is the FDIC coverage limit?",
    "What is the minimum balance requirement for Everyday Checking?",
]


def main() -> int:
    print("=" * 80)
    failures = 0
    for q in QUERIES:
        prep = asyncio.run(prepare_query_for_rag(q))
        route = classify_query_route(q)
        intent = _classify_smalltalk_intent(q)
        answer_route = _resolve_grounded_answer_route(q)
        if prep.direct_response:
            final = prep.direct_response
            validation = "skipped_smalltalk"
            retrieval = "skipped"
        else:
            decision = _shared_rag_final_answer_decision(q, MERIDIAN_DOCS, llm_text=None)
            final = decision.get("answer") or "(llm_required)"
            validation = decision.get("answer_type", "n/a")
            retrieval = f"{len(MERIDIAN_DOCS)} docs (fixture)"

        print(f"Q: {q}")
        print(f"  intent={intent} route={route} answer_route={answer_route}")
        print(f"  retrieval={retrieval} validation={validation}")
        print(f"  final={str(final)[:200]}")
        print()

        if q in {"hi", "hii", "hiii"}:
            if not prep.direct_response:
                failures += 1
        elif q == "What is the FDIC coverage limit?":
            if "250" not in str(final):
                failures += 1
        elif q == "What is the minimum balance requirement for Everyday Checking?":
            if "500" not in str(final) or "everyday" not in str(final).lower():
                failures += 1
        elif final == RAG_NO_MATCH_RESPONSE:
            failures += 1

    print("=" * 80)
    if failures:
        print(f"FAILED: {failures} query checks")
        return 1
    print("All verification checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
