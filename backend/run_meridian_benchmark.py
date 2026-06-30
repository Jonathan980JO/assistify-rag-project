"""Run Meridian KB benchmark with session-isolated connection_ids."""
from __future__ import annotations
import asyncio, json, sys, uuid
from pathlib import Path
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
from backend.config_head import CS_NO_MATCH_RESPONSE_EN
from backend.retrieval.routing import _classify_query_family_v2
MERIDIAN_QUESTIONS = [
    "If I am traveling and need to replace a lost debit card, what are my options and associated costs?",
    "What specific information is required to open a business account at Meridian?",
    "Can I reach out to customer support to ask for my account password if I forget it?",
    "How does Meridian handle potential fraud on my account?",
    "If I have a $10,000 balance in my Money Market account, am I eligible for the same fee structure as an Everyday Checking account?",
    'How does the "Optional Coverage" feature for checking accounts work?',
    "When will I receive my tax forms for interest earned on my savings account?",
    "Are my investment accounts protected by the FDIC?",
    "What are the basic requirements to open a personal account?",
    "I need to send $15,000 to another bank today. What are my options and how much will it cost?",
    "Why isn't the money from my mobile check deposit available immediately?",
    "What happens if I make a purchase that exceeds the available balance in my Everyday Checking account?",
    "How long does Meridian take to resolve a disputed card transaction?",
    "Will my credit score drop if I check my rate for a Personal Loan?",
    "Is there a penalty if I decide to pay off my Small Business Loan early?",
]
FRAGMENT_CHECKS = {
    "Why isn't the money from my mobile check deposit available immediately?": lambda a: len(a.strip()) <= 5 or a.strip() == "1",
    "If I have a $10,000 balance in my Money Market account, am I eligible for the same fee structure as an Everyday Checking account?": lambda a: a.strip() in {"$0", "$0."},
    "Will my credit score drop if I check my rate for a Personal Loan?": lambda a: "Fixed rate" in a and len(a) < 80,
    "Is there a penalty if I decide to pay off my Small Business Loan early?": lambda a: "personal loan" in a.lower() and "business" not in a.lower(),
    "What happens if I make a purchase that exceeds the available balance in my Everyday Checking account?": lambda a: "overdraft" in a.lower() and "declin" not in a.lower() and "coverage" not in a.lower(),
    "How does Meridian handle potential fraud on my account?": lambda a: "cash back" in a.lower() or "rewards credit card" in a.lower(),
}
REGRESSION_CHECKS = {
    'How does the "Optional Coverage" feature for checking accounts work?': lambda a: "overdraw" in a.lower(),
    "Can I reach out to customer support to ask for my account password if I forget it?": lambda a: "forgot password" in a.lower(),
    "If I am traveling and need to replace a lost debit card, what are my options and associated costs?": lambda a: "replace" in a.lower() and ("free" in a.lower() or "$25" in a or "25" in a),
    "What specific information is required to open a business account at Meridian?": lambda a: "formation" in a.lower() or "not" in a.lower() or "beneficial" in a.lower(),
    "Are my investment accounts protected by the FDIC?": lambda a: "not fdic" in a.lower().replace("-", " ") or "are not fdic" in a.lower(),
}
def _is_not_found(answer):
    return CS_NO_MATCH_RESPONSE_EN[:40] in str(answer or "")
async def _run_benchmark():
    import backend.assistify_rag_server as ars
    user = {"username": "benchmark_user", "role": "admin"}
    report = []
    for query in MERIDIAN_QUESTIONS:
        conn_id = f"bench_{uuid.uuid4().hex}"
        ars.conversation_history.pop(conn_id, None)
        answer, docs = await ars.call_llm_with_rag(text=query, user=user, connection_id=conn_id)
        ans_str = str(answer or "")
        report.append({"query": query, "family_v2": _classify_query_family_v2(query), "answer": ans_str[:300], "not_found": _is_not_found(ans_str), "doc_count": len(docs or [])})
    print(json.dumps(report, indent=2))
    fragment_failures = sum(1 for q, check in FRAGMENT_CHECKS.items() if any(r["query"] == q and check(r["answer"]) for r in report))
    regression_failures = sum(1 for q, check in REGRESSION_CHECKS.items() if any(r["query"] == q and not check(r["answer"]) for r in report))
    print(f"\nFragment failures: {fragment_failures}/{len(FRAGMENT_CHECKS)}")
    print(f"Regression failures: {regression_failures}/{len(REGRESSION_CHECKS)}")
    return 1 if fragment_failures > 1 or regression_failures > 0 else 0
if __name__ == "__main__":
    raise SystemExit(asyncio.run(_run_benchmark()))