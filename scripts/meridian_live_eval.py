#!/usr/bin/env python3
"""Phase 8 live regression for the Meridian KB (default tenant = 1).

Runs the 17 required questions through the REAL pipeline (call_llm_with_rag),
capturing for each: route, retrieved-doc sources, validation result, final
answer, and pass/fail vs. the expected answer.

must_contain uses OR-within-group / AND-across-group semantics so paraphrases
still pass; must_not_contain is the strict anti-contamination / anti-leak gate.

Usage:
    python scripts/meridian_live_eval.py
"""
from __future__ import annotations

import os
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
os.environ.setdefault("CHROMA_TELEMETRY_IMPL", "none")
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("RAG_USE_GPU", "0")

import asyncio
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.ERROR, format="%(levelname)s %(message)s")

DEMO_LEAK = ["sign up", "purchase history", "shipping", "returns policy",
             "return policy", "warranty", "tracking number"]

# (question, [must_contain groups], [must_not_contain])
QUERIES = [
    ("What is Meridian Financial Services?",
     [["digital-first", "bank"]], DEMO_LEAK + ["psychology"]),
    ("What is Meridian Invest?",
     [["commission-free", "stocks", "etfs", "invest"]], DEMO_LEAK),
    ("What is Everyday Checking?",
     [["overdraft", "checking"]], DEMO_LEAK + ["stocks", "brokerage"]),
    ("What is the FDIC coverage limit?",
     [["250,000"], ["depositor", "ownership"]], DEMO_LEAK),
    ("What is the ACH transfer limit?",
     [["25,000"]], DEMO_LEAK),
    ("What is the outgoing wire fee?",
     [["15"], ["wire"]], DEMO_LEAK),
    ("What is the minimum balance requirement for Everyday Checking?",
     [["$0", " 0 ", "no minimum", "zero"]], DEMO_LEAK + ["1,000"]),
    ("What is the minimum balance requirement for Money Market?",
     [["1,000"]], DEMO_LEAK),
    ("What is the minimum balance requirement for High-Yield Savings?",
     [["$0", " 0 ", "no minimum", "zero"]], DEMO_LEAK + ["1,000"]),
    ("How do I open an account?",
     [["app"], ["identity", "ssn", "itin", "social security"]], DEMO_LEAK),
    ("How do I dispute a transaction?",
     [["dispute"], ["lock", "open"]], DEMO_LEAK),
    ("How do I replace my card?",
     [["replace"], ["25", "free", "app"]], DEMO_LEAK),
    ("Do you charge overdraft fees?",
     [["no"], ["overdraft"]], DEMO_LEAK),
    ("What happens if I report fraud?",
     [["fraud", "provisional", "refund", "investigat"]], DEMO_LEAK),
    ("I lost my card. What should I do?",
     [["lock", "freeze", "replace"]], DEMO_LEAK),
    ("My account was hacked. What should I do?",
     [["support", "verify", "identity", "lock", "secure", "password", "2fa", "authentication", "change"]], DEMO_LEAK),
    ("I need money urgently. Which transfer method is fastest?",
     [["instant", "wire", "minutes"]], DEMO_LEAK),
]


def _groups_ok(answer_l: str, groups: list[list[str]]) -> list[str]:
    fails = []
    for grp in groups:
        if not any(tok.lower() in answer_l for tok in grp):
            fails.append("MISSING any of " + repr(grp))
    return fails


def _leak_check(answer_l: str, banned: list[str]) -> list[str]:
    return [f"LEAKED '{t}'" for t in banned if t.lower() in answer_l]


async def main() -> int:
    import backend.assistify_rag_server as srv

    # Ensure active-source registry is populated from the (clean) collection.
    try:
        srv._rebuild_active_sources_from_collection()
    except Exception as e:
        print("warn: rebuild active sources:", e)
    try:
        active = sorted(srv._get_active_sources())
    except Exception:
        active = []
    print(f"active_sources = {active}")
    print("=" * 78)

    user = {"username": "eval_admin", "role": "admin", "tenant_id": 1}
    passed = 0
    results = []

    for i, (q, must_groups, must_not) in enumerate(QUERIES, 1):
        try:
            route = srv.classify_query_route(q)
        except Exception:
            route = "?"
        try:
            answer, docs = await srv.call_llm_with_rag(q, f"eval_conn_{i}", user)
        except Exception as e:
            import traceback
            traceback.print_exc()
            answer, docs = f"<EXCEPTION: {e}>", []

        answer_l = str(answer or "").lower()
        # validation (safety) result
        try:
            vr = srv.validate_response(str(answer or ""), q, docs or [])
            valid = f"is_valid={vr.is_valid} sev={vr.severity}"
        except Exception as e:
            valid = f"validate_err={e}"

        # doc sources
        srcs = []
        for d in (docs or [])[:5]:
            if isinstance(d, dict):
                md = d.get("metadata") or {}
                srcs.append(md.get("section") or md.get("title") or md.get("source_name") or "?")
        fails = _groups_ok(answer_l, must_groups) + _leak_check(answer_l, must_not)
        ok = not fails and not answer_l.startswith("<exception")
        passed += 1 if ok else 0
        results.append((q, ok, fails))

        print(f"\n[{i:2d}] {'PASS' if ok else 'FAIL'}  route={route}  docs={len(docs or [])}  {valid}")
        print(f"     Q: {q}")
        print(f"     A: {str(answer or '').strip()[:400]}")
        if srcs:
            print(f"     sections: {srcs}")
        for f in fails:
            print(f"     -> {f}")

    print("\n" + "=" * 78)
    print(f"LIVE PASSED: {passed}/{len(QUERIES)}")
    if passed < len(QUERIES):
        print("FAILED:")
        for q, ok, fails in results:
            if not ok:
                print(f"  - {q} :: {fails}")
    return 0 if passed == len(QUERIES) else 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
