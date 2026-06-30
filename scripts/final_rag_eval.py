import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

NOT_FOUND = "Not found in the document."

ROOT = Path(__file__).resolve().parents[1]
BACKEND_FILE = ROOT / "backend" / "assistify_rag_server.py"
LOGIN_FILE = ROOT / "Login_system" / "login_server.py"
REPORT_JSON = ROOT / "tests" / "final_rag_report.json"
REPORT_TXT = ROOT / "tests" / "final_rag_report.txt"

LOGIN_BASE = os.getenv("ASSISTIFY_LOGIN_BASE", "http://127.0.0.1:7001").rstrip("/")
RAG_BASE = os.getenv("ASSISTIFY_RAG_BASE", "http://127.0.0.1:7000").rstrip("/")
WS_URL = os.getenv("ASSISTIFY_WS_URL", "ws://127.0.0.1:7000/ws")
ADMIN_USERNAME = os.getenv("ASSISTIFY_ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ASSISTIFY_ADMIN_PASSWORD", "admin123")
TIMEOUT = int(os.getenv("ASSISTIFY_HTTP_TIMEOUT", "45"))


def _candidate_credentials() -> List[Tuple[str, str]]:
    candidates: List[Tuple[str, str]] = []

    env_combo = os.getenv("ASSISTIFY_ADMIN_CREDENTIALS", "").strip()
    if env_combo and ":" in env_combo:
        u, p = env_combo.split(":", 1)
        candidates.append((u.strip(), p.strip()))

    candidates.extend([
        (ADMIN_USERNAME, ADMIN_PASSWORD),
        (ADMIN_USERNAME, f"{ADMIN_USERNAME}123"),
        ("admin", "admin123"),
        ("admin", "admin"),
        ("employee", "employee123"),
        ("employee", "employee"),
    ])

    dedup: List[Tuple[str, str]] = []
    seen = set()
    for u, p in candidates:
        key = (u, p)
        if key in seen:
            continue
        seen.add(key)
        dedup.append(key)
    return dedup


DEFINITION_ENTITY_QUESTIONS = [
    "What is scientific management?",
    "Define management.",
    "What is planning?",
    "What is decision-making?",
    "What is administrative management?",
    "What is bureaucracy?",
    "Who is Frederick Taylor?",
    "Who is Henry Fayol?",
    "Who is Max Weber?",
    "Who is considered the father of scientific management?",
    "Who introduced administrative theory?",
]

LIST_STRUCTURE_QUESTIONS = [
    "Steps in planning process",
    "Advantages of scientific management",
    "Disadvantages of scientific management",
    "Types of management approaches",
    "Phases of management process",
    "Levels of management",
    "Functions of management",
    "What are the disadvantages of bureaucracy?",
    "What are the advantages of administrative management?",
    "What happens in planning?",
    "Explain planning process",
]

OVERVIEW_COMPARE_QUESTIONS = [
    "What topics are covered in Chapter 2?",
    "What is discussed in Chapter 1?",
    "What are the main sections in this document?",
    "What does this document talk about?",
    "What is the difference between scientific management and administrative management?",
]

OUT_OF_SCOPE_QUESTIONS = [
    "What is machine learning?",
    "What is blockchain?",
    "Who is Elon Musk?",
    "Explain artificial intelligence",
    "What is cybersecurity?",
]


@dataclass
class RouteChoice:
    kind: str  # http | websocket
    path: str
    base: str
    evidence: List[str]


def _extract_post_routes(file_path: Path) -> List[str]:
    if not file_path.exists():
        return []
    text = file_path.read_text(encoding="utf-8", errors="ignore")
    routes = re.findall(r'@app\.post\("([^"]+)"\)', text)
    return sorted(set(routes))


def _discover_answer_route_candidates() -> Dict[str, List[str]]:
    backend_routes = _extract_post_routes(BACKEND_FILE)
    login_routes = _extract_post_routes(LOGIN_FILE)

    backend_candidates = [
        r for r in backend_routes
        if re.search(r"/(query|ask|answer|chat)", r, flags=re.IGNORECASE)
    ]
    login_candidates = [
        r for r in login_routes
        if re.search(r"/(query|ask|answer|chat)", r, flags=re.IGNORECASE)
    ]

    return {
        "backend_routes": backend_routes,
        "login_routes": login_routes,
        "backend_candidates": backend_candidates,
        "login_candidates": login_candidates,
    }


def authenticate(session: requests.Session) -> Dict[str, Any]:
    flow: Dict[str, Any] = {
        "get_login": None,
        "attempts": [],
        "post_login": None,
        "cookies_after": {},
        "chosen_username": None,
    }

    get_r = session.get(f"{LOGIN_BASE}/login", timeout=TIMEOUT)
    flow["get_login"] = {"status": get_r.status_code, "url": get_r.url}

    for username, password in _candidate_credentials():
        post_r = session.post(
            f"{LOGIN_BASE}/login",
            data={"username": username, "password": password},
            allow_redirects=False,
            timeout=TIMEOUT,
        )
        cookies_now = requests.utils.dict_from_cookiejar(session.cookies)
        attempt = {
            "username": username,
            "status": post_r.status_code,
            "location": post_r.headers.get("location", ""),
            "has_session_cookie": "session" in cookies_now,
        }
        flow["attempts"].append(attempt)

        if post_r.status_code in (302, 303) and "session" in cookies_now:
            flow["post_login"] = {
                "status": post_r.status_code,
                "location": post_r.headers.get("location", ""),
            }
            flow["cookies_after"] = cookies_now
            flow["chosen_username"] = username
            return flow

    raise RuntimeError(f"Login did not set session cookie. Attempts={flow['attempts']}")


def _safe_json(resp: requests.Response) -> Dict[str, Any]:
    try:
        return resp.json()
    except Exception:
        return {"raw": resp.text[:500]}


def _probe_http_answer_route(session: requests.Session, base: str, route: str) -> Tuple[bool, Dict[str, Any]]:
    probe_payload = {"text": "What is management?"}
    t0 = time.perf_counter()
    try:
        r = session.post(f"{base}{route}", json=probe_payload, timeout=TIMEOUT)
        latency_ms = int((time.perf_counter() - t0) * 1000)
        body = _safe_json(r)
        ok_shape = isinstance(body, dict) and any(k in body for k in ("answer", "fullText", "response"))
        return (r.status_code == 200 and ok_shape), {
            "base": base,
            "route": route,
            "status": r.status_code,
            "latency_ms": latency_ms,
            "body_preview": str(body)[:500],
        }
    except Exception as exc:
        return False, {
            "base": base,
            "route": route,
            "status": "error",
            "error": str(exc),
        }


def discover_live_answer_channel(session: requests.Session) -> RouteChoice:
    discovery = _discover_answer_route_candidates()
    evidence: List[str] = []

    evidence.append(f"backend_post_routes={discovery['backend_routes']}")
    evidence.append(f"login_post_routes={discovery['login_routes']}")

    probes = []
    for route in discovery["login_candidates"]:
        ok, info = _probe_http_answer_route(session, LOGIN_BASE, route)
        probes.append(info)
        if ok:
            evidence.append(f"http_probe_success={info}")
            return RouteChoice(kind="http", path=route, base=LOGIN_BASE, evidence=evidence + [f"probes={probes}"])

    for route in discovery["backend_candidates"]:
        ok, info = _probe_http_answer_route(session, RAG_BASE, route)
        probes.append(info)
        if ok:
            evidence.append(f"http_probe_success={info}")
            return RouteChoice(kind="http", path=route, base=RAG_BASE, evidence=evidence + [f"probes={probes}"])

    evidence.append(f"http_probe_failed_all={probes}")
    return RouteChoice(kind="websocket", path="/ws", base=WS_URL, evidence=evidence)


def ask_http(session: requests.Session, route: RouteChoice, question: str) -> Dict[str, Any]:
    t0 = time.perf_counter()
    r = session.post(f"{route.base}{route.path}", json={"text": question}, timeout=TIMEOUT)
    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    body = _safe_json(r)
    answer = ""
    if isinstance(body, dict):
        answer = str(body.get("answer") or body.get("fullText") or body.get("response") or "").strip()
    return {
        "status": r.status_code,
        "latency_ms": elapsed_ms,
        "answer": answer,
        "raw": body,
    }


def ask_ws(session: requests.Session, question: str) -> Dict[str, Any]:
    try:
        import asyncio
        import websockets
    except Exception as exc:
        return {
            "status": "error",
            "latency_ms": -1,
            "answer": "",
            "raw": {"error": f"websockets not available: {exc}"},
        }

    async def _run() -> Dict[str, Any]:
        cookie_header = "; ".join([f"{c.name}={c.value}" for c in session.cookies])
        start = time.perf_counter()
        answer = ""
        status = 200
        raw: Dict[str, Any] = {}
        try:
            async with websockets.connect(WS_URL, additional_headers={"Cookie": cookie_header}, max_size=2**22) as ws:
                await ws.send(json.dumps({"text": question, "language": "en"}))
                while True:
                    msg = await asyncio.wait_for(ws.recv(), timeout=120)
                    if isinstance(msg, (bytes, bytearray)):
                        continue
                    data = json.loads(msg)
                    raw = data
                    if data.get("type") == "aiResponseDone":
                        answer = str(data.get("fullText") or "").strip()
                        break
        except Exception as e:
            status = 500
            raw = {"error": str(e)}
        return {
            "status": status,
            "latency_ms": int((time.perf_counter() - start) * 1000),
            "answer": answer,
            "raw": raw,
        }

    return asyncio.run(_run())


def _extract_entity_tokens(question: str) -> List[str]:
    q = (question or "").strip().lower().rstrip("?.")
    q = re.sub(r"^(who is considered the father of)\s+", "", q)
    q = re.sub(r"^(what is|define|who is|who was|who introduced)\s+", "", q)
    stop = {
        "the", "and", "management", "process", "document", "considered", "father", "introduced",
        "what", "who", "define", "is", "was", "of", "in", "to", "theory",
    }
    toks = [t for t in re.findall(r"[a-z0-9]{3,}", q) if t not in stop]
    return toks[:6]


def classify(question: str, answer: str, category: str) -> Tuple[str, str, List[str]]:
    a = (answer or "").strip()
    low = a.lower()
    qlow = (question or "").strip().lower()
    flags: List[str] = []

    if not a:
        return "FAIL", "empty answer", flags

    if category == "out_of_scope":
        if a == NOT_FOUND:
            return "PASS", "correct strict out-of-scope response", flags
        if "not found in the document" in low:
            return "PARTIAL", "near-correct out-of-scope wording", flags
        if re.search(r"\b(machine learning|blockchain|artificial intelligence|cybersecurity|elon musk)\b", low):
            flags.append("generic_hallucination")
            return "FAIL", "hallucinated world knowledge for out-of-scope", flags
        return "FAIL", "out-of-scope did not return strict not-found", flags

    if category in {"definition_entity", "in_scope_definition_entity"}:
        entity_tokens = _extract_entity_tokens(question)
        token_hits = sum(1 for t in entity_tokens if re.search(rf"\b{re.escape(t)}\b", low)) if entity_tokens else 0
        has_def_cue = bool(re.search(r"\b(is|was|refers to|defined as|known as|born|considered|introduced)\b", low))
        looks_like_list = bool(re.search(r"(?:^|\n)\s*(?:[-•*]|\d+[.)])\s+", a)) or (a.count("\n") >= 3)
        has_criticism = bool(re.search(r"\b(criticism|criticisms?|advantages?|disadvantages?)\b", low))
        is_person_lookup_q = qlow.startswith("who ")
        asks_father_or_intro = ("father of" in qlow) or qlow.startswith("who introduced")
        name_like_answer = bool(re.search(r"\b[A-Z][a-z]{2,}\s+[A-Z][a-z]{2,}\b", a)) or bool(re.search(r"\b[A-Z]\.\s*[A-Z][a-z]{2,}\b", a))

        if has_criticism:
            flags.append("criticism_as_definition")
        if looks_like_list:
            flags.append("list_as_definition")

        if asks_father_or_intro and not name_like_answer:
            flags.append("missing_person_name")
            return "FAIL", "person-entity question answered without a clear person name", flags

        required_hits = max(1, min(2, len(entity_tokens))) if entity_tokens else 0
        token_ok = (required_hits == 0) or (token_hits >= required_hits)

        if is_person_lookup_q and not name_like_answer and token_ok and has_def_cue:
            return "PARTIAL", "person question has weak person grounding", flags

        if token_ok and has_def_cue and not has_criticism and not looks_like_list:
            return "PASS", "clean definition/biography sentence", flags
        if token_ok and has_def_cue:
            return "PARTIAL", "definition signal present but quality contamination detected", flags
        return "FAIL", "missing grounded definitional sentence", flags

    if category in {"list_structure", "in_scope_list_structure", "in_scope_overview_compare"}:
        bullet_lines = len(re.findall(r"(?:^|\n)\s*(?:[-•*]|\d+[.)])\s+", a))
        comma_list = len(re.findall(r"\w+\s*,\s*\w+\s*,\s*\w+", a))
        multi_line = a.count("\n") >= 2
        wrong_section = False

        ql = question.lower()
        if "advantage" in ql and re.search(r"\bdisadvantages?\b", low):
            wrong_section = True
            flags.append("wrong_section_contamination")
        if "disadvantage" in ql and re.search(r"\badvantages?\b", low):
            wrong_section = True
            flags.append("wrong_section_contamination")

        if category == "in_scope_overview_compare":
            has_structure_cues = bool(
                re.search(r"\b(chapter|unit|section|topics|main|overview|summary|difference|whereas|while)\b", low)
            )
            if (multi_line or bullet_lines >= 1 or comma_list >= 1 or has_structure_cues) and not wrong_section:
                return "PASS", "structured overview/chapter/compare answer", flags
            if multi_line or has_structure_cues:
                return "PARTIAL", "partially structured overview/compare answer", flags
            return "FAIL", "overview/chapter/compare answer not clearly structured", flags

        if (bullet_lines >= 2 or comma_list >= 1 or multi_line) and not wrong_section:
            return "PASS", "structured list/sectional answer", flags
        if bullet_lines >= 1 or multi_line:
            return "PARTIAL", "partially structured but weak or mixed", flags
        return "FAIL", "list/structure answer not clearly structured", flags

    return "FAIL", "unknown category", flags


def run_eval() -> Dict[str, Any]:
    session = requests.Session()

    auth_flow = authenticate(session)
    route_choice = discover_live_answer_channel(session)

    questions: List[Tuple[str, str]] = []
    questions += [("in_scope_definition_entity", q) for q in DEFINITION_ENTITY_QUESTIONS]
    questions += [("in_scope_list_structure", q) for q in LIST_STRUCTURE_QUESTIONS]
    questions += [("in_scope_overview_compare", q) for q in OVERVIEW_COMPARE_QUESTIONS]
    questions += [("out_of_scope", q) for q in OUT_OF_SCOPE_QUESTIONS]

    results: List[Dict[str, Any]] = []

    for category, q in questions:
        if route_choice.kind == "http":
            asked = ask_http(session, route_choice, q)
        else:
            asked = ask_ws(session, q)

        answer = asked.get("answer", "")
        status, reason, flags = classify(q, answer, category)
        results.append(
            {
                "category": category,
                "question": q,
                "answer": answer,
                "status": status,
                "reason": reason,
                "quality_flags": flags,
                "latency_ms": asked.get("latency_ms"),
                "http_status": asked.get("status"),
            }
        )

    counts = {"PASS": 0, "PARTIAL": 0, "FAIL": 0}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1

    in_scope_categories = {
        "in_scope_definition_entity",
        "in_scope_list_structure",
        "in_scope_overview_compare",
    }

    in_scope_rows = [r for r in results if r["category"] in in_scope_categories]
    out_scope_rows = [r for r in results if r["category"] == "out_of_scope"]

    in_scope_pass = sum(1 for r in in_scope_rows if r["status"] == "PASS")
    in_scope_fail = sum(1 for r in in_scope_rows if r["status"] in {"FAIL", "PARTIAL"})
    in_scope_total = len(in_scope_rows)
    in_scope_accuracy = (in_scope_pass / in_scope_total) if in_scope_total else 0.0

    out_scope_pass = sum(1 for r in out_scope_rows if r["status"] == "PASS")
    out_scope_fail = sum(1 for r in out_scope_rows if r["status"] in {"FAIL", "PARTIAL"})
    out_scope_total = len(out_scope_rows)
    out_scope_accuracy = (out_scope_pass / out_scope_total) if out_scope_total else 0.0

    weighted_score = 0.8 * in_scope_accuracy + 0.2 * out_scope_accuracy

    report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "login_base": LOGIN_BASE,
        "rag_base": RAG_BASE,
        "auth": auth_flow,
        "route_choice": {
            "kind": route_choice.kind,
            "base": route_choice.base,
            "path": route_choice.path,
            "evidence": route_choice.evidence,
        },
        "raw_total_summary": {
            "total": len(results),
            "pass": counts["PASS"],
            "partial": counts["PARTIAL"],
            "fail": counts["FAIL"],
        },
        "rag_quality_summary": {
            "in_scope_total": in_scope_total,
            "in_scope_pass": in_scope_pass,
            "in_scope_fail": in_scope_fail,
            "in_scope_accuracy": round(in_scope_accuracy, 4),
            "out_of_scope_total": out_scope_total,
            "out_of_scope_pass": out_scope_pass,
            "out_of_scope_fail": out_scope_fail,
            "out_of_scope_accuracy": round(out_scope_accuracy, 4),
            "weighted_score": round(weighted_score, 4),
        },
        "results": results,
    }

    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        f"Assistify Final RAG Evaluation - {report['timestamp']}",
        f"Route used: {route_choice.kind.upper()} {route_choice.base}{route_choice.path if route_choice.kind == 'http' else ''}",
        f"Raw total summary: PASS={counts['PASS']} PARTIAL={counts['PARTIAL']} FAIL={counts['FAIL']} TOTAL={len(results)}",
        "",
        "RAG QUALITY SUMMARY",
        f"- Raw total: PASS={counts['PASS']} PARTIAL={counts['PARTIAL']} FAIL={counts['FAIL']} TOTAL={len(results)}",
        f"- In-scope accuracy: {in_scope_pass}/{in_scope_total} = {in_scope_accuracy:.2%}",
        f"- Out-of-scope refusal accuracy: {out_scope_pass}/{out_scope_total} = {out_scope_accuracy:.2%}",
        f"- Weighted overall score: {weighted_score:.2%}",
        "",
    ]
    for row in results:
        lines.append(f"[{row['status']}] {row['question']}")
        lines.append(f"  Answer: {row['answer'][:350]}")
        lines.append(f"  Reason: {row['reason']}")
        if row.get("quality_flags"):
            lines.append(f"  Flags: {', '.join(row['quality_flags'])}")
        lines.append("")

    REPORT_TXT.write_text("\n".join(lines), encoding="utf-8")
    return report


if __name__ == "__main__":
    final_report = run_eval()
    print(json.dumps(final_report["raw_total_summary"], ensure_ascii=False, indent=2))
    print(json.dumps(final_report["rag_quality_summary"], ensure_ascii=False, indent=2))
    print(f"Route used: {final_report['route_choice']['kind']} {final_report['route_choice']['base']}{final_report['route_choice']['path']}")
    print(f"Report JSON: {REPORT_JSON}")
    print(f"Report TXT: {REPORT_TXT}")
