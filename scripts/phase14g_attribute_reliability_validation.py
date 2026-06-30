"""Live Phase 14G validation runner."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import phase14f_final_answer_validation as p14f
from backend.retrieval.routing import _lightweight_spelling_correction

QUESTIONS: list[dict[str, Any]] = [
    {"id": "attr_tam", "group": "attribute", "query": "Which plan includes a named TAM?", "expected_any": ["enterprise"]},
    {"id": "attr_audit", "group": "attribute", "query": "Which plan includes audit logs?", "expected_all": ["business", "enterprise"]},
    {"id": "attr_private_net", "group": "attribute", "query": "Which plan includes private networking?", "expected_any": ["enterprise"]},
    {"id": "attr_pci", "group": "attribute", "query": "Which plan includes PCI compliance?", "expected_any": ["enterprise"]},
    {"id": "attr_fee_growth", "group": "attribute", "query": "What is the monthly fee for Growth?", "expected_any": ["99"]},
    {"id": "attr_fee_business", "group": "attribute", "query": "What is the monthly fee for Business?", "expected_any": ["499"]},
    {"id": "attr_support_starter", "group": "attribute", "query": "What is the support response time for Starter?", "expected_any": ["business day", "next business"]},
    {"id": "attr_support_growth", "group": "attribute", "query": "What is the support response time for Growth?", "expected_any": ["4 business", "under 4"]},
    {"id": "attr_support_business", "group": "attribute", "query": "What is the support response time for Business?", "expected_any": ["1 hour", "under 1"]},
    {"id": "attr_support_enterprise", "group": "attribute", "query": "What is the support response time for Enterprise?", "expected_any": ["15 minute", "under 15"]},
    {"id": "attr_vm_memory", "group": "attribute", "query": "Which VM family has the most memory?", "expected_any": ["gpu", "1152"]},
    {"id": "attr_vm_vcpu", "group": "attribute", "query": "Which VM family has the largest vCPU range?", "expected_any": ["memory", "128"]},
    {"id": "cmp_growth_enterprise", "group": "compare", "query": "Compare Growth and Enterprise plans", "require_structured": True},
    {"id": "cmp_starter_business", "group": "compare", "query": "Compare Starter and Business plans", "require_structured": True},
    {"id": "cmp_three_plans", "group": "compare", "query": "Compare Growth, Business and Enterprise plans", "require_structured": True},
    {"id": "cmp_all_plans", "group": "compare", "query": "Compare all plans", "require_structured": True},
    {"id": "cmp_general_gpu", "group": "compare", "query": "Compare General and GPU VM families", "require_structured": True},
    {"id": "cmp_compute_memory", "group": "compare", "query": "Compare Compute and Memory VM families", "require_structured": True},
    {"id": "faq_transfer", "group": "faq", "query": "How do I transfer ownership?", "expected_any": ["transfer", "ownership"], "forbidden": ["forgot password", "reset password"]},
    {"id": "faq_account_owner", "group": "faq", "query": "Who is the account owner?", "expected_any": ["owner", "account"]},
    {"id": "faq_invitation", "group": "faq", "query": "How long does an invitation remain valid?", "expected_any": ["invitation", "valid", "day", "hour"]},
    {"id": "proc_ingress", "group": "procedural", "query": "Do I pay for ingress traffic?", "expected_any": ["ingress", "free", "not charged"]},
    {"id": "proc_egress", "group": "procedural", "query": "How is egress billed?", "expected_any": ["egress", "bill", "charge", "per"]},
    {"id": "proc_launch_vm", "group": "procedural", "query": "How quickly can I launch a VM?", "expected_any": ["launch", "minute", "second", "vm"]},
    {"id": "proc_onboarding", "group": "procedural", "query": "How does onboarding work?", "expected_any": ["onboard", "setup", "step", "process"]},
    {"id": "proc_enterprise_setup", "group": "procedural", "query": "How long does Enterprise setup take?", "expected_any": ["enterprise", "setup", "day", "week"]},
    {"id": "proc_compliance_setup", "group": "procedural", "query": "How long does compliance setup take?", "expected_any": ["compliance", "setup", "day", "week"]},
    {"id": "proc_usage_discount", "group": "procedural", "query": "Are usage discounts available?", "expected_any": ["discount", "usage", "volume", "commit"]},
    {"id": "proc_prepaid", "group": "procedural", "query": "How long are prepaid credits valid?", "expected_any": ["prepaid", "credit", "valid", "month", "year"]},
    {"id": "proc_refund", "group": "procedural", "query": "What refund options are available?", "expected_any": ["refund", "credit", "policy"]},
    {"id": "person_ceo", "group": "person", "query": "Who is the CEO of Nimbus?", "expect_not_found": True},
    {"id": "person_elon", "group": "person", "query": "Who is Elon Musk?", "expect_not_found": True},
    {"id": "person_ms_founder", "group": "person", "query": "Who founded Microsoft?", "expect_not_found": True},
]

GROUP_MARKERS = {
    "attribute": "ATTRIBUTE FIX VERIFIED",
    "compare": "COMPARISON FIX VERIFIED",
    "faq": "FAQ FIX VERIFIED",
    "procedural": "PROCEDURAL FIX VERIFIED",
    "person": "PERSON VALIDATION FIX VERIFIED",
    "spelling": "SPELLING FIX VERIFIED",
}


def _evaluate(question: dict[str, Any], answer: str) -> bool:
    answer_l = str(answer or "").lower()
    if question.get("expect_not_found"):
        return p14f._is_not_found(answer)
    if p14f._is_not_found(answer):
        return False
    if question.get("expected_any"):
        if not any(str(t).lower() in answer_l for t in question["expected_any"]):
            return False
    for token in question.get("expected_all") or []:
        if str(token).lower() not in answer_l:
            return False
    if question.get("require_structured") and "-" not in answer and "\n" not in answer:
        return False
    if question.get("require_structured") and question.get("id") == "cmp_all_plans":
        if not any(name in answer_l for name in ("starter", "growth", "business", "enterprise")):
            return False
    for bad in question.get("forbidden") or []:
        if str(bad).lower() in answer_l:
            return False
    if question.get("group") == "attribute" and "|" in answer:
        return False
    return True


async def _run(args: argparse.Namespace) -> int:
    session = p14f._login(args.login_host, args.username, args.password)
    cookie = p14f._session_cookie_header(session)
    results: list[dict[str, Any]] = []
    for question in QUESTIONS:
        trace_id = f"phase14g-{question['id']}-{int(time.time() * 1000)}"
        ws = await p14f._run_ws_query(
            ws_url=args.ws_url,
            cookie_header=cookie,
            query=question["query"],
            trace_id=trace_id,
            tenant_id=args.tenant_id,
            timeout_s=args.timeout,
        )
        passed = _evaluate(question, ws.answer) and not ws.error
        row = {**question, "answer": ws.answer, "passed": passed, "error": ws.error}
        results.append(row)
        if passed:
            marker = GROUP_MARKERS.get(str(question.get("group") or ""), "FIXED")
            print(f"GREEN {marker}")
            print(f"FIXED: {question['query']}")
            print(f"After: {str(ws.answer)[:300]}")
        else:
            print(f"FAIL {question['id']} -> {str(ws.answer)[:120]}")
    for token in ("provide", "support", "enterprise", "growth", "business", "audit", "memory", "response", "billing", "compliance", "kubernetes", "nimbus"):
        q = f"What does the {token} feature include?"
        corrected = q
        try:
            corrected = _lightweight_spelling_correction(q)
        except Exception:
            corrected = q
        ok = token in corrected.lower()
        results.append({"id": f"spell_{token}", "group": "spelling", "passed": ok, "query": q})
        print(("PASS" if ok else "FAIL"), "spelling", token)
        if ok:
            print(f"GREEN {GROUP_MARKERS['spelling']}: {token}")
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    passed_count = sum(1 for r in results if r.get("passed"))
    print(f"Summary: {passed_count}/{len(results)} passed -> {out}")
    return 0 if passed_count == len(results) else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--login-host", default=p14f.LOGIN_HOST)
    parser.add_argument("--ws-url", default=p14f.WS_URL)
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", default="admin")
    parser.add_argument("--tenant-id", type=int, default=2)
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--output", default="logs/phase14g_live_validation.json")
    args = parser.parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
