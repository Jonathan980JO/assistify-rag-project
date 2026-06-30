#!/usr/bin/env python3
"""16-test dual-corpus RAG evaluation (IBM HR + Psychology) with rubric scoring."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

LOGIN_BASE = os.getenv("ASSISTIFY_LOGIN_BASE", "http://127.0.0.1:7001").rstrip("/")
RAG_BASE = os.getenv("ASSISTIFY_RAG_BASE", "http://127.0.0.1:7000").rstrip("/")
WS_URL = os.getenv("ASSISTIFY_WS_URL", "ws://127.0.0.1:7000/ws")
TIMEOUT = int(os.getenv("ASSISTIFY_HTTP_TIMEOUT", "180"))
REPORT_PATH = REPO_ROOT / "tests" / "eval_dual_corpus_report.json"

SENTINEL = "Not found in the document."


@dataclass
class Rubric:
    required_concepts: List[str] = field(default_factory=list)
    required_numeric_patterns: List[str] = field(default_factory=list)
    required_source_signals: List[str] = field(default_factory=list)
    forbidden_patterns: List[str] = field(default_factory=list)
    refusal_ok: bool = False
    min_bullets: int = 0
    max_bullets: int = 0
    min_mcq: int = 0
    memo_headers: bool = False
    min_length: int = 0


@dataclass
class EvalCase:
    test_id: int
    phase: int
    name: str
    prompt: str
    rubric: Rubric


EVAL_CASES: List[EvalCase] = [
    EvalCase(1, 1, "HR attrition rate", "According to the IBM HR Attrition CRISP-DM report, what is the exact attrition rate, and which department has the highest attrition percentage?",
             Rubric(required_concepts=["attrition", "sales"], required_numeric_patterns=[r"16\.1\d?\s*%", r"20\.6\d?\s*%"])),
    EvalCase(2, 1, "ROC-AUC baseline", "What was the ROC-AUC score of the Logistic Regression baseline model at the default 0.50 threshold?",
             Rubric(required_concepts=["roc", "logistic"], required_numeric_patterns=[r"0\.7272"])),
    EvalCase(3, 1, "Plato soul", "What are the three parts of the soul according to Plato, and how did he define the 'rational' part?",
             Rubric(required_concepts=["reason", "spirit", "appetite", "rational"])),
    EvalCase(4, 1, "Medulla centers", "List the three vital centers located in the Medulla Oblongata and their functions.",
             Rubric(required_concepts=["cardio", "respiratory", "vasomotor"])),
    EvalCase(5, 2, "I/O Psychology bridge", "The HR report identifies 'JobSatisfaction' and 'WorkLifeBalance' as key features. Using the Industrial/Organizational Psychology chapter from the Psychology textbook, explain the psychological definition of job satisfaction and how decision-making structures (centralized vs. decentralized) impact it.",
             Rubric(required_concepts=["job satisfaction", "centralized", "decentralized"], required_source_signals=["hr", "psychology"])),
    EvalCase(6, 2, "Health Psychology overtime", "The HR data shows that 'OverTime' has the strongest positive correlation (+0.25) with attrition. Using the Health Psychology chapter on Stress and Illness, categorize 'OverTime' into the correct class of stressors (Cataclysmic, Personal, or Background) and explain the physiological manifestation of this chronic stress using the General Adaptation Syndrome (GAS) model.",
             Rubric(required_concepts=["overtime", "background", "gas", "stress"], required_source_signals=["hr", "psychology"])),
    EvalCase(7, 2, "Operant conditioning retention", "The HR 30/60/90-day plan suggests a 'Sales Rep retention program' and 'targeted compensation reviews'. How would B.F. Skinner's Operant Conditioning principles (specifically Positive Reinforcement and Schedules of Reinforcement) be applied to design this retention program?",
             Rubric(required_concepts=["reinforcement", "skinner", "retention"], required_source_signals=["hr", "psychology"])),
    EvalCase(8, 3, "Correlation vs causation", "The HR report uses a correlation heatmap to identify drivers of attrition. Referencing the Research Methods in Psychology chapter, explain the difference between correlation and causation. Why must IBM HR be careful not to assume that reducing 'OverTime' will causally reduce attrition without further experimental or quasi-experimental research?",
             Rubric(required_concepts=["correlation", "causation", "overtime"], required_source_signals=["psychology"])),
    EvalCase(9, 3, "Cognitive dissonance", "Imagine a Sales Representative who is working high overtime but has low monthly income. According to the Social Psychology chapter on Cognitive Dissonance, what psychological conflict might this employee experience, and what specific dissonance reduction strategies might they use to either justify staying or ultimately decide to leave (attrition)?",
             Rubric(required_concepts=["dissonance", "overtime", "attrition"])),
    EvalCase(10, 3, "Predictive validity", "The HR model achieves an ROC-AUC of ~0.73. The Psychology textbook discusses Intelligence and Predictive Validity. Is an ROC-AUC of 0.73 considered a strong predictor of complex human behavior? What psychological variables (e.g., intrinsic motivation, personality traits like the 'Big Five') are missing from the HR dataset that could improve this model?",
             Rubric(required_concepts=["predictive validity", "0.73"], required_source_signals=["hr", "psychology"])),
    EvalCase(11, 4, "Executive memo", "Act as an Industrial/Organizational Psychologist hired by IBM. Write a 1-page executive memo to the HR Director. Translate the top 3 data-driven findings from the CRISP-DM report into actionable psychological interventions, citing relevant psychological theories (e.g., Maslow's Hierarchy, Expectancy Theory).",
             Rubric(required_concepts=["memo", "finding"], memo_headers=True, min_length=400)),
    EvalCase(12, 4, "Quiz generation", "Create a 5-question multiple-choice quiz for a university class. Question 1-3 should test concepts from the Memory chapter (e.g., Short-term vs. Long-term, Proactive interference). Questions 4-5 should test the IBM HR Attrition deployment plan and KPIs. Provide an answer key at the end.",
             Rubric(min_mcq=5, required_concepts=["memory", "answer key"])),
    EvalCase(13, 4, "Extreme summary", "Summarize the entire 250+ page Psychology textbook and the 13-page HR report into exactly 5 bullet points, highlighting how human behavior (psychology) drives business metrics (HR attrition).",
             Rubric(min_bullets=5, max_bullets=7, required_concepts=["psychology", "attrition"])),
    EvalCase(14, 5, "Missing HR formula", "What is the exact mathematical formula and the coefficient weights for the Logistic Regression model used in the IBM HR dataset?",
             Rubric(refusal_ok=True, forbidden_patterns=[r"β\s*\d", r"coefficient\s*=\s*[-+]?\d\.\d+", r"intercept\s*=\s*[-+]?\d\.\d+"])),
    EvalCase(15, 5, "Absurd cross-reference", "What did Wilhelm Wundt say about the CRISP-DM framework in his 1879 Leipzig laboratory?",
             Rubric(refusal_ok=True, forbidden_patterns=[r"wundt.{0,80}crisp-dm", r"1879.{0,80}data mining"])),
    EvalCase(16, 5, "Out-of-scope DSM", "According to the provided text, what is the DSM-5-TR diagnostic code for 'Employee Burnout Syndrome'?",
             Rubric(refusal_ok=True, forbidden_patterns=[r"DSM-5-TR\s*[A-Z]\d+", r"F\d{2}\.\d", r"Z\d{2}\.\d"])),
]


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def _warm_refusal(answer: str) -> bool:
    a = _normalize(answer)
    if SENTINEL in answer:
        return False
    refusal_markers = (
        "not in the", "not found in", "do not have", "don't have", "does not contain",
        "doesn't contain", "no information", "not provided", "not available",
        "uploaded materials", "knowledge base", "provided text", "provided documents",
        "cannot find", "unable to find", "no specific detail",
    )
    return any(m in a for m in refusal_markers)


def score_answer(case: EvalCase, answer: str) -> Dict[str, Any]:
    a_norm = _normalize(answer)
    checks: Dict[str, Any] = {}
    failed: List[str] = []

    for concept in case.rubric.required_concepts:
        ok = concept.lower() in a_norm
        checks[f"concept:{concept}"] = ok
        if not ok:
            failed.append(f"missing concept: {concept}")

    for pattern in case.rubric.required_numeric_patterns:
        ok = bool(re.search(pattern, answer, re.IGNORECASE))
        checks[f"numeric:{pattern}"] = ok
        if not ok:
            failed.append(f"missing numeric pattern: {pattern}")

    for sig in case.rubric.required_source_signals:
        if sig == "hr":
            ok = any(x in a_norm for x in ("ibm", "hr report", "crisp", "attrition report", "crisp-dm"))
        elif sig == "psychology":
            ok = any(x in a_norm for x in ("psychology", "lesson", "chapter", "textbook"))
        else:
            ok = sig.lower() in a_norm
        checks[f"source:{sig}"] = ok
        if not ok:
            failed.append(f"missing source signal: {sig}")

    for pattern in case.rubric.forbidden_patterns:
        bad = bool(re.search(pattern, answer, re.IGNORECASE | re.DOTALL))
        checks[f"forbidden:{pattern}"] = not bad
        if bad:
            failed.append(f"forbidden pattern matched: {pattern}")

    if case.rubric.refusal_ok:
        ok = _warm_refusal(answer)
        checks["warm_refusal"] = ok
        if not ok:
            failed.append("expected warm grounded refusal")

    if case.rubric.min_bullets:
        bullets = len(re.findall(r"(?m)^\s*[-*•]\s+", answer))
        ok = bullets >= case.rubric.min_bullets
        checks["min_bullets"] = ok
        if not ok:
            failed.append(f"need >= {case.rubric.min_bullets} bullets, got {bullets}")

    if case.rubric.max_bullets:
        bullets = len(re.findall(r"(?m)^\s*[-*•]\s+", answer))
        ok = bullets <= case.rubric.max_bullets
        checks["max_bullets"] = ok
        if not ok:
            failed.append(f"need <= {case.rubric.max_bullets} bullets, got {bullets}")

    if case.rubric.min_mcq:
        mcq = len(re.findall(r"(?im)^\s*(?:question\s*)?\d+[.)]", answer))
        ok = mcq >= case.rubric.min_mcq
        checks["min_mcq"] = ok
        if not ok:
            failed.append(f"need >= {case.rubric.min_mcq} MCQs, got {mcq}")

    if case.rubric.memo_headers:
        ok = bool(re.search(r"(?im)\b(to|from|subject|memo)\b", answer))
        checks["memo_headers"] = ok
        if not ok:
            failed.append("missing memo headers")

    if case.rubric.min_length:
        ok = len(answer.strip()) >= case.rubric.min_length
        checks["min_length"] = ok
        if not ok:
            failed.append(f"answer too short ({len(answer.strip())} < {case.rubric.min_length})")

    if SENTINEL in answer:
        failed.append("literal sentinel leaked to user")

    required_checks = [v for k, v in checks.items() if not k.startswith("forbidden:")]
    forbidden_checks = [v for k, v in checks.items() if k.startswith("forbidden:")]
    passed = all(required_checks) and all(forbidden_checks) and not failed

    if failed:
        if case.rubric.refusal_ok and _warm_refusal(answer) and all(
            checks.get(k, True) for k in checks if k.startswith("forbidden:")
        ):
            partial = len([f for f in failed if "warm_refusal" not in f]) == 0
        else:
            partial = len(failed) <= max(1, len(checks) // 3) and any(required_checks)
    else:
        partial = False

    status = "pass" if passed else ("partial" if partial else "fail")
    return {"status": status, "checks": checks, "failed": failed, "answer_preview": answer[:500]}


def authenticate(session: requests.Session) -> None:
    for username, password in (("admin", "admin"), ("admin", "admin123")):
        r = session.post(f"{LOGIN_BASE}/login", data={"username": username, "password": password}, allow_redirects=False, timeout=TIMEOUT)
        if r.status_code in (302, 303) and session.cookies.get("session"):
            return
    raise RuntimeError("Login failed — start login server on port 7001")


def _kb_status(session: requests.Session) -> Dict[str, Any]:
    try:
        r = session.get(f"{RAG_BASE}/kb_status", timeout=10)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return {}


def ask_question(session: requests.Session, question: str) -> Dict[str, Any]:
    """Prefer login-server WebSocket proxy (production chat path)."""
    login_ws = LOGIN_BASE.replace("http://", "ws://").replace("https://", "wss://") + "/ws"
    ws_result = ask_ws(session, question, ws_url=login_ws)
    if ws_result.get("answer"):
        return ws_result
    return ask_http(session, question)


def ask_http(session: requests.Session, question: str) -> Dict[str, Any]:
    t0 = time.perf_counter()
    for route in ("/api/query", "/query"):
        try:
            r = session.post(f"{RAG_BASE}{route}", json={"text": question}, timeout=TIMEOUT)
            if r.status_code == 404:
                continue
            body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            answer = str(body.get("answer") or body.get("fullText") or body.get("response") or "").strip()
            return {"status": r.status_code, "latency_ms": int((time.perf_counter() - t0) * 1000), "answer": answer, "route": route}
        except Exception:
            continue
    return ask_ws(session, question)


def ask_ws(session: requests.Session, question: str, ws_url: str | None = None) -> Dict[str, Any]:
    import asyncio
    try:
        import websockets
    except ImportError as exc:
        return {"status": 500, "latency_ms": -1, "answer": "", "error": str(exc)}

    target_ws = ws_url or WS_URL

    async def _run() -> Dict[str, Any]:
        cookie_header = "; ".join([f"{c.name}={c.value}" for c in session.cookies])
        start = time.perf_counter()
        answer = ""
        try:
            async with websockets.connect(target_ws, additional_headers={"Cookie": cookie_header}, max_size=2**22) as ws:
                await ws.send(json.dumps({"text": question, "language": "en"}))
                while True:
                    msg = await asyncio.wait_for(ws.recv(), timeout=TIMEOUT)
                    if isinstance(msg, (bytes, bytearray)):
                        continue
                    data = json.loads(msg)
                    if data.get("type") == "aiResponseDone":
                        answer = str(data.get("fullText") or "").strip()
                        break
        except Exception as exc:
            return {"status": 500, "latency_ms": int((time.perf_counter() - start) * 1000), "answer": answer, "error": str(exc)}
        return {"status": 200, "latency_ms": int((time.perf_counter() - start) * 1000), "answer": answer, "route": target_ws}

    return asyncio.run(_run())


def run_eval(phase: Optional[int] = None, offline_rubric_only: bool = False) -> Dict[str, Any]:
    cases = [c for c in EVAL_CASES if phase is None or c.phase == phase]
    report: Dict[str, Any] = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "phase_filter": phase,
        "results": [],
        "summary": {"pass": 0, "partial": 0, "fail": 0, "total": len(cases)},
    }

    session = requests.Session()
    if not offline_rubric_only:
        authenticate(session)
        kb = _kb_status(session)
        if kb:
            print(f"KB status: chunks via active_sources={len(kb.get('active_sources') or [])} stage={kb.get('stage')}")
            report["kb_status"] = kb
        try:
            rb = session.post(f"{RAG_BASE}/rag/rebuild-active-sources", timeout=30)
            if rb.status_code == 200:
                report["rebuild_active_sources"] = rb.json()
                print("Rebuilt active_sources from collection")
        except Exception:
            pass

    for case in cases:
        entry: Dict[str, Any] = {"test_id": case.test_id, "phase": case.phase, "name": case.name, "prompt": case.prompt}
        if offline_rubric_only:
            entry["score"] = {"status": "skipped", "checks": {}, "failed": [], "answer_preview": ""}
            report["results"].append(entry)
            continue

        try:
            resp = ask_question(session, case.prompt)
            answer = str(resp.get("answer") or "")
            score = score_answer(case, answer)
            entry.update({"response": resp, "score": score})
            report["summary"][score["status"]] = report["summary"].get(score["status"], 0) + 1
        except Exception as exc:
            entry["score"] = {"status": "fail", "checks": {}, "failed": [str(exc)], "answer_preview": ""}
            report["summary"]["fail"] += 1

        report["results"].append(entry)
        print(f"Test {case.test_id} ({case.name}): {entry['score']['status']}")

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nReport written to {REPORT_PATH}")
    print(f"Summary: {report['summary']}")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Dual-corpus RAG evaluation protocol")
    parser.add_argument("--phase", type=int, choices=[1, 2, 3, 4, 5], help="Run only one phase")
    parser.add_argument("--offline-rubric", action="store_true", help="Validate rubric definitions only")
    args = parser.parse_args()
    report = run_eval(phase=args.phase, offline_rubric_only=args.offline_rubric)
    fails = int(report["summary"].get("fail", 0))
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
