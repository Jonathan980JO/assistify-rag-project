#!/usr/bin/env python3
"""
Phase 7 — 17-Query Meridian Regression Suite.

Run AFTER re-ingesting Meridian with the fixed OCR / chunking pipeline.

Usage:
    # With live LLM (requires backend running):
    python scripts/meridian_regression.py --mode live --tenant-id 4

    # Retrieval-only mode (no LLM, fast):
    python scripts/meridian_regression.py --mode retrieval --tenant-id 4
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import re
import sys
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
logger = logging.getLogger("meridian_regression")

# ---------------------------------------------------------------------------
# The 17-query suite from RCA Sprint #2
# ---------------------------------------------------------------------------
QUERIES = [
    {
        "query": "What is Meridian Financial Services?",
        "must_contain": ["meridian", "financial services"],
        "must_not_contain": ["psychology", "chapter", "six ms"],
    },
    {
        "query": "What is Meridian Invest?",
        "must_contain": ["invest", "meridian"],
        "must_not_contain": ["checking", "everyday checking", "minimum balance"],
    },
    {
        "query": "What is Everyday Checking?",
        "must_contain": ["everyday checking"],
        "must_not_contain": ["meridian invest", "stocks", "brokerage"],
    },
    {
        "query": "What is High-Yield Savings?",
        "must_contain": ["high-yield savings", "savings"],
        "must_not_contain": [],
    },
    {
        "query": "FDIC coverage limit?",
        "must_contain": ["250,000", "fdic"],
        "must_not_contain": [],
    },
    {
        "query": "ACH transfer limit?",
        "must_contain": ["25,000", "ach"],
        "must_not_contain": [],
    },
    {
        "query": "Outgoing wire fee?",
        "must_contain": ["15", "wire"],
        "must_not_contain": [],
    },
    {
        "query": "Minimum balance Everyday Checking?",
        "must_contain": ["everyday checking"],
        "must_not_contain": ["meridian invest"],
    },
    {
        "query": "Minimum balance Money Market?",
        "must_contain": ["money market"],
        "must_not_contain": [],
    },
    {
        "query": "Minimum balance High-Yield Savings?",
        "must_contain": ["$0", "high-yield savings"],
        "must_not_contain": [],
    },
    {
        "query": "How do I open an account?",
        "must_contain": ["account", "open"],
        "must_not_contain": ["sign up", "purchase history", "warranty", "shipping", "returns"],
    },
    {
        "query": "How do I dispute a transaction?",
        "must_contain": ["dispute", "transaction"],
        "must_not_contain": ["sign up", "purchase history", "warranty"],
    },
    {
        "query": "How do I replace my card?",
        "must_contain": ["card", "replace"],
        "must_not_contain": ["sign up", "warranty", "shipping"],
    },
    {
        "query": "What happens if I report fraud?",
        "must_contain": ["fraud"],
        "must_not_contain": ["sign up", "warranty"],
    },
    {
        "query": "I lost my card.",
        "must_contain": ["card"],
        "must_not_contain": ["sign up", "warranty"],
    },
    {
        "query": "My account was hacked.",
        "must_contain": [],
        "must_not_contain": ["sign up", "purchase history", "warranty", "shipping"],
    },
    {
        "query": "Fastest transfer method.",
        "must_contain": ["instant", "wire"],
        "must_not_contain": [],
    },
]

# ---------------------------------------------------------------------------
# Retrieval-only mode (no LLM)
# ---------------------------------------------------------------------------

def _check_retrieved_chunks(query: str, chunks: list[dict], must_contain: list[str], must_not_contain: list[str]) -> tuple[bool, list[str]]:
    combined = " ".join(
        str(c.get("text") or c.get("page_content") or "")
        for c in (chunks or [])
    ).lower()

    failures = []
    for term in must_contain:
        if term.lower() not in combined:
            failures.append(f"MISSING: '{term}'")
    for term in must_not_contain:
        if term.lower() in combined:
            failures.append(f"LEAKED: '{term}'")
    return len(failures) == 0, failures


def run_retrieval_suite(tenant_id: int) -> dict:
    from backend.knowledge_base import resolve_tenant_active_collection, search_documents

    col = resolve_tenant_active_collection(tenant_id)
    if not col or col.count() == 0:
        print(f"ERROR: No chunks in collection for tenant {tenant_id}")
        return {}

    print(f"\nCollection: {getattr(col, 'name', '?')}  chunks: {col.count()}")
    print("=" * 70)

    results = {}
    passed = 0
    failed = 0

    for item in QUERIES:
        q = item["query"]
        must_contain = item["must_contain"]
        must_not_contain = item["must_not_contain"]

        chunks = search_documents(q, top_k=5, tenant_id=tenant_id)
        if isinstance(chunks, list) and chunks and isinstance(chunks[0], str):
            chunk_dicts = [{"text": c} for c in chunks]
        else:
            chunk_dicts = list(chunks or [])

        ok, failures = _check_retrieved_chunks(q, chunk_dicts, must_contain, must_not_contain)
        status = "PASS" if ok else "FAIL"
        if ok:
            passed += 1
        else:
            failed += 1

        print(f"[{status}] {q}")
        for f in failures:
            print(f"       {f}")
        results[q] = {"status": status, "failures": failures}

    print("=" * 70)
    print(f"PASSED: {passed}/{len(QUERIES)}   FAILED: {failed}/{len(QUERIES)}")
    return results


# ---------------------------------------------------------------------------
# Live LLM mode
# ---------------------------------------------------------------------------

async def run_live_suite(tenant_id: int) -> dict:
    from backend.assistify_rag_server import call_llm_with_rag

    results = {}
    passed = 0
    failed = 0

    print(f"\nLive LLM regression — tenant_id={tenant_id}")
    print("=" * 70)

    user_stub = {"username": "regression_user", "role": "admin", "tenant_id": tenant_id}

    for item in QUERIES:
        q = item["query"]
        must_contain = item["must_contain"]
        must_not_contain = item["must_not_contain"]

        try:
            response, docs = await call_llm_with_rag(
                text=q,
                user=user_stub,
                connection_id="regression",
            )
            answer = str(response or "").lower()

            failures = []
            for term in must_contain:
                if term.lower() not in answer:
                    failures.append(f"MISSING: '{term}'")
            for term in must_not_contain:
                if term.lower() in answer:
                    failures.append(f"LEAKED: '{term}'")

            ok = len(failures) == 0
        except Exception as e:
            ok = False
            failures = [f"EXCEPTION: {e}"]

        status = "PASS" if ok else "FAIL"
        if ok:
            passed += 1
        else:
            failed += 1

        print(f"[{status}] {q}")
        for f in failures:
            print(f"       {f}")
        results[q] = {"status": status, "failures": failures}

    print("=" * 70)
    print(f"PASSED: {passed}/{len(QUERIES)}   FAILED: {failed}/{len(QUERIES)}")
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="17-Query Meridian Regression Suite")
    parser.add_argument("--tenant-id", type=int, default=4)
    parser.add_argument("--mode", choices=["retrieval", "live"], default="retrieval")
    args = parser.parse_args()

    if args.mode == "live":
        asyncio.run(run_live_suite(args.tenant_id))
    else:
        run_retrieval_suite(args.tenant_id)


if __name__ == "__main__":
    main()
