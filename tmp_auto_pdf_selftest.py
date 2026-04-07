import asyncio
import json
import os
import random
import re
import shutil
import string
import time
import uuid
from pathlib import Path

import requests
import websockets
from PyPDF2 import PdfReader

BASE_RAG = "http://127.0.0.1:7000"
BASE_LOGIN = "http://127.0.0.1:7001"
WS_URL = "ws://127.0.0.1:7000/ws"
PDF_DIR = Path(r"C:\Users\MK\Desktop\Notes\PDF")
ASSETS_DIR = Path(__file__).resolve().parent / "backend" / "assets"
REPORT_PATH = Path(__file__).resolve().parent / "auto_selftest_report.json"

NOT_FOUND = "Not found in the document."


def login_admin(session: requests.Session) -> None:
    last_err = None
    for _ in range(30):
        try:
            r = session.post(
                f"{BASE_LOGIN}/login",
                data={"username": "admin", "password": "admin"},
                allow_redirects=False,
                timeout=20,
            )
            if r.status_code in (200, 302, 303):
                return
            last_err = RuntimeError(f"Login failed: {r.status_code} {r.text[:200]}")
        except Exception as exc:
            last_err = exc
        time.sleep(1.0)
    raise RuntimeError(f"Login failed after retries: {last_err}")


def random_csrf() -> str:
    return "tok_" + "".join(random.choices(string.ascii_letters + string.digits, k=24))


def post_with_retry(session: requests.Session, url: str, **kwargs) -> requests.Response:
    last_err = None
    for _ in range(30):
        try:
            r = session.post(url, **kwargs)
            return r
        except Exception as exc:
            last_err = exc
            time.sleep(1.0)
    raise RuntimeError(f"POST retry failed for {url}: {last_err}")


def get_with_retry(session: requests.Session, url: str, **kwargs) -> requests.Response:
    last_err = None
    for _ in range(30):
        try:
            r = session.get(url, **kwargs)
            return r
        except Exception as exc:
            last_err = exc
            time.sleep(1.0)
    raise RuntimeError(f"GET retry failed for {url}: {last_err}")


def set_doc_mode(session: requests.Session, mode: str, active_sources=None) -> dict:
    payload = {"mode": mode}
    if active_sources is not None:
        payload["active_sources"] = active_sources
    r = post_with_retry(session, f"{BASE_RAG}/rag/doc-mode", json=payload, timeout=30)
    r.raise_for_status()
    return r.json()


def upload_pdf(session: requests.Session, pdf_path: Path) -> dict:
    csrf = random_csrf()
    session.cookies.set("csrf_token", csrf)
    with pdf_path.open("rb") as f:
        files = {"file": (pdf_path.name, f, "application/pdf")}
        r = post_with_retry(
            session,
            f"{BASE_RAG}/upload_rag",
            files=files,
            headers={"x-csrf-token": csrf},
            timeout=600,
        )
    r.raise_for_status()
    return r.json()


def extract_pdf_text(pdf_path: Path, max_pages: int = 18) -> str:
    reader = PdfReader(str(pdf_path))
    pages = []
    for i, page in enumerate(reader.pages[:max_pages], start=1):
        t = (page.extract_text() or "").strip()
        if t:
            pages.append(t)
    return "\n\n".join(pages)


def derive_smoke_questions(pdf_path: Path, text: str) -> list[dict]:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    title_line = ""
    for ln in lines[:25]:
        if 4 <= len(ln.split()) <= 10 and len(ln) <= 90 and not re.search(r"\d{4}|copyright|openstax|university", ln, flags=re.I):
            title_line = ln
            break

    base = re.sub(r"[_\-]+", " ", pdf_path.stem)
    base = re.sub(r"\s+", " ", base).strip()
    doc_title = title_line or base

    def _clean_topic_line(raw: str) -> str:
        cleaned = re.sub(r"^\s*(chapter|unit|section)\s+\d+[\.:\-]*\s*", "", raw, flags=re.I)
        cleaned = re.sub(r"^\s*\d+[\.)\-:]*\s*", "", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" -:;,.\t")
        return cleaned

    chapter_lines = []
    for ln in lines[:260]:
        if re.search(r"^(chapter|unit|section)\s+\d+", ln, flags=re.I):
            chapter_lines.append(ln)
        elif re.search(r"^\d+\.\s+[A-Z]", ln):
            chapter_lines.append(ln)
        if len(chapter_lines) >= 8:
            break

    clean_topics = []
    for ln in chapter_lines:
        cleaned = _clean_topic_line(ln)
        if not cleaned:
            continue
        if len(cleaned) < 4 or len(cleaned.split()) > 10:
            continue
        if re.search(r"\b(isbn|copyright|title|internet--security|computer security)\b", cleaned, flags=re.I):
            continue
        if sum(1 for ch in cleaned if ch in "()[]{}|/") > 1:
            continue
        clean_topics.append(cleaned)

    definition_term = None
    definition_sentence = None
    for m in re.finditer(r"\b([A-Z][A-Za-z][A-Za-z\- ]{1,40})\s+is\s+(?:the|a|an)\b", text):
        candidate = re.sub(r"\s+", " ", m.group(1)).strip()
        if candidate.lower() in {"this", "that", "it", "there", "chapter", "section"}:
            continue
        if 2 <= len(candidate.split()) <= 5:
            definition_term = candidate
            sentence_start = max(0, m.start() - 20)
            sentence_end = min(len(text), m.end() + 180)
            definition_sentence = text[sentence_start:sentence_end].replace("\n", " ").strip()
            break

    if not definition_term:
        tokens = [t for t in re.findall(r"[A-Za-z]{5,}", doc_title) if t.lower() not in {"introduction", "complete", "compressed"}]
        definition_term = " ".join(tokens[:2]) if tokens else "the main concept"

    entity_candidates = []
    person_entities = []
    name_blacklist = {
        "handbook", "discovering", "web", "application", "chapter", "section", "contents",
        "core", "defense", "mechanisms", "internet", "security", "title"
    }
    for m in re.finditer(r"\b([A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,}){0,2})\b", text):
        cand = re.sub(r"\s+", " ", m.group(1)).strip()
        if cand.lower() in {"table of contents", "chapter", "section", "introduction", "openstax", "rice university"}:
            continue
        if len(cand) >= 4:
            entity_candidates.append(cand)
        if re.match(r"^[A-Z][a-z]{2,}\s+[A-Z][a-z]{2,}$", cand):
            a, b = cand.split()
            if a.lower() not in name_blacklist and b.lower() not in name_blacklist:
                person_entities.append(cand)
    entity = entity_candidates[0] if entity_candidates else definition_term

    if clean_topics:
        list_topic = "chapter or section titles"
        list_question = f"List only the first four {list_topic} shown in {doc_title}, one item per line."
        topic_target = clean_topics[0]
        factual_question = f"What is {topic_target} according to {doc_title}?"
    elif chapter_lines:
        topic_target = _clean_topic_line(chapter_lines[0]) or chapter_lines[0]
        list_question = f"List only the first four chapter or section titles shown in {doc_title}, one item per line."
        factual_question = f"What does {topic_target} refer to in {doc_title}?"
    else:
        list_patterns = [
            r"\b(main\s+branches?)\b",
            r"\b(types?)\b",
            r"\b(goals?)\b",
            r"\b(principles?)\b",
            r"\b(themes?)\b",
        ]
        lower_text = text.lower()
        list_hint = "main topics"
        for pat in list_patterns:
            mm = re.search(pat, lower_text)
            if mm:
                list_hint = mm.group(1)
                break
        list_question = f"List only the {list_hint} mentioned in {doc_title}, one item per line."
        factual_question = f"What is {entity} according to {doc_title}?"

    definition_question = f"What is {definition_term} as defined in {doc_title}?"

    questions = [
        {"type": "definition", "question": definition_question, "evidence_hint": (definition_sentence or "")[:220]},
        {"type": "list", "question": list_question, "evidence_hint": (chapter_lines[0] if chapter_lines else "")[:220]},
        {"type": "factual", "question": factual_question, "evidence_hint": entity},
        {"type": "out_of_scope", "question": "What is the capital of France?", "evidence_hint": ""},
    ]
    return questions


def cookie_header(session: requests.Session) -> str:
    return "; ".join([f"{c.name}={c.value}" for c in session.cookies])


async def ask_ws(session: requests.Session, question: str) -> dict:
    headers = {"Cookie": cookie_header(session)}
    t0 = time.perf_counter()
    first_chunk_ms = None
    done = None
    try:
        async with websockets.connect(WS_URL, additional_headers=headers, max_size=2**22) as ws:
            await ws.send(json.dumps({"text": question, "language": "en"}))
            while True:
                msg = await asyncio.wait_for(ws.recv(), timeout=180)
                if isinstance(msg, (bytes, bytearray)):
                    continue
                data = json.loads(msg)
                if data.get("type") == "aiResponseChunk" and first_chunk_ms is None:
                    first_chunk_ms = (time.perf_counter() - t0) * 1000
                if data.get("type") == "aiResponseDone":
                    done = data
                    break
    except Exception:
        done = done or {"fullText": NOT_FOUND, "sources": 0}
    total_ms = (time.perf_counter() - t0) * 1000
    return {
        "answer": (done or {}).get("fullText", ""),
        "first_token_ms": round(first_chunk_ms or -1, 1),
        "total_ms": round(total_ms, 1),
        "sources_count": (done or {}).get("sources", 0),
    }


def retrieve_debug(session: requests.Session, question: str, top_k: int = 3) -> dict:
    r = get_with_retry(session, f"{BASE_RAG}/rag/retrieve-debug", params={"query": question, "top_k": top_k}, timeout=40)
    r.raise_for_status()
    return r.json()


def evaluate_case(case: dict, expected_source_fragment: str, active_sources: set[str]) -> tuple[bool, list[str]]:
    fails = []
    ans = (case.get("answer") or "").strip()
    qtype = case["type"]
    retrieved = case.get("retrieval", {}).get("results", [])

    for row in retrieved:
        src = str(row.get("source") or row.get("filename") or "").lower()
        if active_sources and not any(a in src for a in active_sources):
            fails.append(f"wrong_document_source:{src}")

    if qtype == "out_of_scope":
        if ans != NOT_FOUND:
            fails.append("out_of_scope_not_exact_not_found")
    else:
        if expected_source_fragment.lower() not in " ".join(
            [str((r.get("source") or r.get("filename") or "")).lower() for r in retrieved]
        ):
            fails.append("retrieval_not_from_expected_pdf")

    if qtype == "list":
        has_list_shape = ("\n-" in ans) or ("\n1." in ans) or (ans.count("\n") >= 2)
        if not has_list_shape and ans != NOT_FOUND:
            fails.append("list_format_invalid")

    if qtype == "factual":
        q_entities = [e.lower() for e in re.findall(r"\b[A-Z][a-z]{2,}\b", case.get("question", ""))]
        retrieval_text = "\n".join((r.get("text_preview") or "") for r in retrieved).lower()
        entity_evidence = any(ent in retrieval_text for ent in q_entities) if q_entities else False
        lexical_terms = [t.lower() for t in re.findall(r"[A-Za-z]{4,}", case.get("question", ""))]
        lexical_hits = sum(1 for t in lexical_terms if t in retrieval_text)
        definitional_evidence = bool(re.search(r"\b(is|are|refers to|defined as|means)\b", retrieval_text))
        has_strong_evidence = (entity_evidence and definitional_evidence) or lexical_hits >= 3
        top_sim = 0.0
        for row in retrieved:
            try:
                top_sim = max(top_sim, float(row.get("similarity") or 0.0))
            except Exception:
                pass
        if ans == NOT_FOUND and len(retrieved) >= 5 and has_strong_evidence and top_sim >= 0.82:
            fails.append("factual_false_not_found")

    if case.get("first_token_ms", 0) > 8000 and not case.get("cold_start", False):
        fails.append("first_token_too_slow")

    return (len(fails) == 0), fails


async def run_pdf_batch(session: requests.Session, pdf_path: Path, mode: str, cold_start: bool = False) -> dict:
    upload_meta = upload_pdf(session, pdf_path)
    indexed_name = upload_meta.get("filename", pdf_path.name)

    text = extract_pdf_text(pdf_path)
    questions = derive_smoke_questions(pdf_path, text)

    batch = {
        "pdf": str(pdf_path),
        "indexed_filename": indexed_name,
        "mode": mode,
        "upload": upload_meta,
        "questions": [],
        "pass": True,
    }

    active_sources = {indexed_name.lower()}

    for idx, q in enumerate(questions):
        ws_res = await ask_ws(session, q["question"])
        ws_res["cold_start"] = cold_start and idx == 0
        ret = retrieve_debug(session, q["question"], top_k=3)
        case = {
            **q,
            **ws_res,
            "retrieval": ret,
        }
        ok, fails = evaluate_case(case, indexed_name.lower(), active_sources)
        case["pass"] = ok
        case["fail_reasons"] = fails
        batch["questions"].append(case)
        if not ok:
            batch["pass"] = False

    return batch


async def run_multi_batch(session: requests.Session, indexed_files: list[str]) -> dict:
    set_doc_mode(session, "multi", active_sources=indexed_files)
    batch = {
        "mode": "multi",
        "active_sources": indexed_files,
        "cases": [],
        "pass": True,
    }

    for src in indexed_files:
        q = f"What is discussed in {Path(src).stem.replace('_', ' ')}?"
        ws_res = await ask_ws(session, q)
        ret = retrieve_debug(session, q, top_k=4)
        case = {
            "question": q,
            **ws_res,
            "retrieval": ret,
        }
        retrieved_sources = {
            str(r.get("source") or r.get("filename") or "").lower()
            for r in ret.get("results", [])
        }
        allowed = {s.lower() for s in indexed_files}
        bad = [s for s in retrieved_sources if s and not any(a in s for a in allowed)]
        case["pass"] = len(bad) == 0
        case["fail_reasons"] = [f"wrong_document_source:{x}" for x in bad]
        batch["cases"].append(case)
        if not case["pass"]:
            batch["pass"] = False

    return batch


async def main() -> None:
    if not PDF_DIR.exists():
        raise RuntimeError(f"PDF folder not found: {PDF_DIR}")

    pdfs = sorted(PDF_DIR.glob("*.pdf"))[:3]
    if len(pdfs) < 3:
        raise RuntimeError("Need at least 3 PDFs for required validation")

    session = requests.Session()
    login_admin(session)

    report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "pdfs": [str(p) for p in pdfs],
        "single_mode_batches": [],
        "multi_mode_batch": None,
        "overall_pass": False,
        "single_first_pass": None,
    }

    set_doc_mode(session, "single", active_sources=[])

    indexed_files = []
    first_batch = await run_pdf_batch(session, pdfs[0], mode="single", cold_start=True)
    report["single_mode_batches"].append(first_batch)
    indexed_files.append(first_batch.get("indexed_filename", pdfs[0].name))
    report["single_first_pass"] = bool(first_batch.get("pass"))

    if report["single_first_pass"]:
        for pdf in pdfs[1:]:
            batch = await run_pdf_batch(session, pdf, mode="single", cold_start=False)
            report["single_mode_batches"].append(batch)
            indexed_files.append(batch.get("indexed_filename", pdf.name))
    else:
        report["multi_mode_batch"] = {"mode": "multi", "active_sources": indexed_files, "cases": [], "pass": False}
        report["overall_pass"] = False
        REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"report": str(REPORT_PATH), "overall_pass": report["overall_pass"]}, indent=2))
        return

    multi_batch = await run_multi_batch(session, indexed_files)
    report["multi_mode_batch"] = multi_batch

    report["overall_pass"] = (
        all(b.get("pass") for b in report["single_mode_batches"])
        and (report["multi_mode_batch"] or {}).get("pass", False)
    )

    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"report": str(REPORT_PATH), "overall_pass": report["overall_pass"]}, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
