#!/usr/bin/env python3
"""Evaluate Farco tenant (id=3) car knowledge base against the 18-question golden set."""
from __future__ import annotations

import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

FARCO_TENANT_ID = int(os.getenv("FARCO_TENANT_ID", "3"))
REPORT_JSON = ROOT / "tests" / "farco_car_kb_eval_report.json"
REPORT_TXT = ROOT / "tests" / "farco_car_kb_eval_report.txt"

NOT_FOUND_MARKERS = (
    "not found in the document",
    "don't have that specific detail",
    "not in our help materials",
    "isn't covered",
    "is not covered",
    "cannot find",
    "can't find",
    "no specific",
    "false premise",
)


@dataclass
class EvalCase:
    id: str
    tier: str
    question: str
    expect_any: list[str] = field(default_factory=list)
    expect_all: list[str] = field(default_factory=list)
    trap: bool = False
    notes: str = ""


CASES: list[EvalCase] = [
    EvalCase("Q1", "A", "What are the four phases of the four-stroke engine cycle?",
             expect_any=["intake", "compression", "power", "exhaust", "combustion"]),
    EvalCase("Q2", "A", "What ignites the fuel-air mixture in a diesel engine?",
             expect_any=["compression", "no spark", "inject", "spontaneous", "14:1", "23:1"]),
    EvalCase("Q3", "A", 'What does the "5W" in "5W-30" engine oil mean?',
             expect_any=["winter", "cold", "low temperature", "flows"]),
    EvalCase("Q4", "A", "What is the recommended brake fluid replacement interval?",
             expect_any=["2-3 year", "2 to 3 year", "every 2", "hygroscopic", "moisture"]),
    EvalCase("Q5", "A", 'What does the number "45" mean in the tire size 225/45R17?',
             expect_any=["aspect ratio", "sidewall", "percentage", "225"]),
    EvalCase("Q6", "A", "How long does a typical 12-volt car battery last?",
             expect_any=["3-5 year", "3 to 5 year", "three", "five year"]),
    EvalCase("Q7", "B", "Why do turbocharged engines often require premium fuel?",
             expect_any=["knock", "octane", "compression", "premium"]),
    EvalCase("Q8", "B", "A driver hears grinding when braking — what does this likely indicate, and how urgent is it?",
             expect_any=["pad", "rotor", "metal", "prompt", "urgent", "worn"]),
    EvalCase("Q9", "B", "What's the difference between AWD and 4WD as described in the document?",
             expect_any=["awd", "4wd", "all-wheel", "four-wheel", "off-road", "traction"]),
    EvalCase("Q10", "B", "Why shouldn't you keep driving if the oil pressure warning light comes on?",
             expect_any=["lubricat", "damage", "stop", "low oil", "pressure"]),
    EvalCase("Q11", "C", "Compare the typical refuel/charge time and running cost of a battery electric vehicle versus a hydrogen fuel cell vehicle.",
             expect_any=["bev", "electric", "fcev", "hydrogen", "minute", "cost", "charg"]),
    EvalCase("Q12", "C", "If a car has a timing belt instead of a timing chain, why does its maintenance interval matter so much?",
             expect_any=["timing belt", "60,000", "100,000", "engine damage", "camshaft", "crankshaft"]),
    EvalCase("Q13", "C", "Explain why diesel engines tend to get better fuel economy than gasoline engines, referencing both the combustion process and the fuel itself.",
             expect_any=["compression", "denser", "energy", "thermal", "gasoline"]),
    EvalCase("Q14", "C", "A driver wants a vehicle with no multi-speed transmission at all — which powertrain type would that be, and why doesn't it need one?",
             expect_any=["electric", "bev", "single-speed", "torque", "motor"]),
    EvalCase("Q15", "C", "What two systems both rely on a belt driven by the engine, and what does each one do?",
             expect_any=["water pump", "alternator", "coolant", "electrical"]),
    EvalCase("Q16", "D", "According to the document, what is the recommended tire pressure for a standard sedan?",
             trap=True, notes="Should refuse specific PSI; mention door jamb sticker"),
    EvalCase("Q17", "D", "Does the document mention solid-state batteries for electric vehicles?",
             trap=True, notes="Should say not covered"),
    EvalCase("Q18", "D", "What is the maintenance interval for spark plugs in an electric vehicle, according to the document?",
             trap=True, notes="Trap: EVs have no spark plugs"),
]


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def _hits(text: str, phrases: list[str]) -> list[str]:
    low = _norm(text)
    return [p for p in phrases if p.lower() in low]


def _is_not_found_answer(text: str) -> bool:
    low = _norm(text)
    return any(m in low for m in NOT_FOUND_MARKERS)


def _score_case(case: EvalCase, answer: str, retrieval_text: str) -> dict[str, Any]:
    answer = str(answer or "")
    retrieval_text = str(retrieval_text or "")
    combined = f"{answer}\n{retrieval_text}"

    if case.trap:
        passed = _is_not_found_answer(answer) or (
            case.id == "Q16" and any(x in _norm(answer) for x in ("door", "sticker", "manufacturer", "jamb", "varies"))
        ) or (
            case.id == "Q17" and any(x in _norm(answer) for x in ("not mention", "does not mention", "not cover", "no mention", "isn't", "is not"))
        ) or (
            case.id == "Q18" and any(x in _norm(answer) for x in ("no spark", "electric vehicle", "ev", "not applicable", "does not have", "don't have", "no internal combustion"))
        )
        return {
            "passed": passed,
            "mode": "trap",
            "answer_preview": answer[:400],
            "not_found": _is_not_found_answer(answer),
        }

    any_hits = _hits(combined, case.expect_any) if case.expect_any else []
    all_hits = _hits(combined, case.expect_all) if case.expect_all else []
    missing_any = not any_hits if case.expect_any else False
    missing_all = [p for p in case.expect_all if p.lower() not in _norm(combined)]
    passed = (not missing_any) and (not missing_all)
    answer_hits = _hits(answer, case.expect_any) if case.expect_any else []
    answer_pass = (not case.expect_any or bool(answer_hits)) and not _is_not_found_answer(answer)
    retrieval_hits = _hits(retrieval_text, case.expect_any) if case.expect_any else []
    return {
        "passed": passed and answer_pass,
        "answer_pass": answer_pass,
        "retrieval_pass": bool(retrieval_hits) if case.expect_any else True,
        "mode": "positive",
        "any_hits": any_hits,
        "answer_hits": answer_hits,
        "retrieval_hits": retrieval_hits,
        "missing_all": missing_all,
        "answer_preview": answer[:400],
        "not_found": _is_not_found_answer(answer),
    }


def run_eval() -> dict[str, Any]:
    from backend.assistify_rag_server import (
        RAG_NO_MATCH_RESPONSE,
        RAG_STRICT_DISTANCE_THRESHOLD,
        _TenantScope,
        _distance_threshold_for_query,
        _search_fast_minimal,
        _validate_query_ui_equivalent,
        get_tenant_rag,
    )

    results: list[dict[str, Any]] = []
    t0 = time.time()

    with _TenantScope(FARCO_TENANT_ID):
        rag = get_tenant_rag(FARCO_TENANT_ID)
        collection_count = None
        try:
            if rag.vs is None:
                from backend.pdf_ingestion_rag import VectorStore
                rag.vs = VectorStore(
                    persist_directory=str(ROOT / "backend" / "chroma_db"),
                    collection_name=f"t{FARCO_TENANT_ID}_support_docs_v3_latest",
                )
            collection_count = rag.vs.collection.count()
        except Exception as exc:
            collection_count = f"error: {exc}"

        for case in CASES:
            print(f"\n=== {case.id} [{case.tier}] {case.question[:70]}...")
            row: dict[str, Any] = {
                "id": case.id,
                "tier": case.tier,
                "question": case.question,
                "trap": case.trap,
                "notes": case.notes,
            }
            try:
                diag = _validate_query_ui_equivalent(case.question)
                ui = diag.get("ui_equivalent_result") or {}
                answer = str(ui.get("answer") or "")
                retrieval_count = int(diag.get("retrieval_count") or 0)

                docs = _search_fast_minimal(case.question, top_k=8) or []
                retrieval_snippets = []
                top_distance = None
                for i, d in enumerate(docs[:5]):
                    txt = str(d.get("text") or d.get("page_content") or "")
                    dist = d.get("distance")
                    if i == 0 and dist is not None:
                        top_distance = float(dist)
                    retrieval_snippets.append(txt[:300])
                retrieval_blob = "\n".join(retrieval_snippets)

                score = _score_case(case, answer, retrieval_blob)
                row.update({
                    "retrieval_count": retrieval_count,
                    "search_count": len(docs),
                    "top_distance": top_distance,
                    "distance_threshold": _distance_threshold_for_query(case.question),
                    "answer": answer,
                    "answer_type": ui.get("answer_type"),
                    "score": score,
                    "context_summary": diag.get("context_summary", "")[:500],
                    "top_retrieval_preview": retrieval_snippets[0] if retrieval_snippets else "",
                })
                status = "PASS" if score["passed"] else "FAIL"
                print(f"  {status} | retrieval={retrieval_count} search={len(docs)} dist={top_distance}")
                print(f"  A: {answer[:220]}")
                if not score["passed"]:
                    if case.trap:
                        print(f"  expected trap/refusal, got: {answer[:180]}")
                    else:
                        print(f"  hits={score.get('any_hits')} not_found={score.get('not_found')}")
            except Exception as exc:
                row["error"] = str(exc)
                row["score"] = {"passed": False, "mode": "error"}
                print(f"  ERROR: {exc}")

            results.append(row)

    passed = sum(1 for r in results if (r.get("score") or {}).get("passed"))
    answer_passed = sum(1 for r in results if (r.get("score") or {}).get("answer_pass"))
    retrieval_passed = sum(1 for r in results if (r.get("score") or {}).get("retrieval_pass"))
    report = {
        "tenant_id": FARCO_TENANT_ID,
        "tenant_name": "Farco",
        "collection_count": collection_count,
        "rag_strict_distance_threshold": RAG_STRICT_DISTANCE_THRESHOLD,
        "not_found_sentinel": RAG_NO_MATCH_RESPONSE,
        "passed": passed,
        "answer_passed": answer_passed,
        "retrieval_passed": retrieval_passed,
        "total": len(CASES),
        "pass_rate": round(passed / max(1, len(CASES)), 3),
        "answer_pass_rate": round(answer_passed / max(1, len(CASES)), 3),
        "retrieval_pass_rate": round(retrieval_passed / max(1, len(CASES)), 3),
        "elapsed_s": round(time.time() - t0, 2),
        "results": results,
    }
    return report


def _write_reports(report: dict[str, Any]) -> None:
    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        f"Farco Car KB Eval — tenant {report['tenant_id']} ({report.get('tenant_name')})",
        f"Collection chunks: {report.get('collection_count')}",
        f"Pass: {report['passed']}/{report['total']} full ({report['pass_rate']:.0%})",
        f"Answer pass: {report.get('answer_passed', 0)}/{report['total']}",
        f"Retrieval pass: {report.get('retrieval_passed', 0)}/{report['total']}",
        f"Threshold: {report.get('rag_strict_distance_threshold')}",
        "",
    ]
    for r in report.get("results", []):
        ok = (r.get("score") or {}).get("passed")
        mark = "PASS" if ok else "FAIL"
        lines.append(f"[{mark}] {r['id']} ({r['tier']}) {r['question'][:72]}")
        if r.get("answer"):
            lines.append(f"  A: {str(r['answer'])[:240]}")
        if not ok:
            lines.append(f"  retrieval={r.get('retrieval_count')} dist={r.get('top_distance')}")
            if r.get("top_retrieval_preview"):
                lines.append(f"  top_chunk: {r['top_retrieval_preview'][:200]}")
        lines.append("")
    REPORT_TXT.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    report = run_eval()
    _write_reports(report)
    print(f"\n{'='*60}")
    print(
        f"SUMMARY: {report['passed']}/{report['total']} full pass | "
        f"answer {report['answer_passed']}/{report['total']} | "
        f"retrieval {report['retrieval_passed']}/{report['total']}"
    )
    print(f"Reports: {REPORT_JSON}")
    print(f"         {REPORT_TXT}")
    return 0 if report["passed"] == report["total"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
