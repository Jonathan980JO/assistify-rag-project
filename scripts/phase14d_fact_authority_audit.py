from __future__ import annotations

"""Phase 14D-C   Fact Extraction Authority Audit harness.

Evidence-gathering tool (Step 1) for the deterministic fact layer in
``backend/retrieval/routing.py``. It is intentionally read-only against the
runtime: it logs in, calls ``/rag/retrieve-debug`` for ground-truth rerank
order, fires the real WebSocket query path, tails the RAG log for fact markers,
and then derives a generic, answer-key-free root-cause matrix (Step 2).

Login / retrieve-debug / WS / log-tail / tenant-auto-detect helpers are reused
verbatim from ``scripts/phase14d_relation_evidence.py``. Only the query sets,
fact-marker capture, and the root-cause-matrix derivation are new.

Genericity note: nothing in this file references a specific document, company,
person, filename, or known answer. "Contains correct answer" is derived purely
from query subject terms + attribution-verb sentence shape in the top-ranked
retrieved chunks. The override/harm signals are derived from rerank order.
"""

import argparse
import asyncio
import inspect
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
import websockets

LOGIN_HOST = "http://127.0.0.1:7001"
RAG_HOST = "http://127.0.0.1:7000"
WS_URL = "ws://127.0.0.1:7000/ws"

# ---------------------------------------------------------------------------
# Query sets (Step 1 + Step 5). No answer keys   only the questions.
# ---------------------------------------------------------------------------
RELATION_QUERIES: list[dict[str, str]] = [
    {"id": "relation_found_behaviorism", "group": "relation", "query": "Who founded behaviorism?"},
    {"id": "relation_found_gestalt", "group": "relation", "query": "Who founded Gestalt psychology?"},
    {"id": "relation_found_structuralism", "group": "relation", "query": "Who founded structuralism?"},
    {"id": "relation_created_psychoanalysis", "group": "relation", "query": "Who created psychoanalysis?"},
    {"id": "relation_developed_analytical", "group": "relation", "query": "Who developed analytical psychology?"},
    {"id": "relation_who_jung", "group": "relation", "query": "Who is Jung?"},
    {"id": "relation_who_freud", "group": "relation", "query": "Who is Freud?"},
]

DEMO_QUERIES: list[dict[str, str]] = [
    {"id": "demo_what_is_psychology", "group": "demo", "query": "What is psychology?"},
    {"id": "demo_define_behaviorism", "group": "demo", "query": "Define behaviorism"},
    {"id": "demo_define_structuralism", "group": "demo", "query": "Define structuralism"},
    {"id": "demo_define_functionalism", "group": "demo", "query": "Define functionalism"},
    {"id": "demo_long_term_memory", "group": "demo", "query": "What is long-term memory?"},
    {"id": "demo_document_about", "group": "demo", "query": "What is this document about?"},
    {"id": "demo_who_elon_musk", "group": "demo", "query": "Who is Elon Musk?"},
]

# Step 5   out-of-document regression set. The harness asserts grounded
# not-found responses for these (they are not expected to be in any uploaded doc).
NOT_IN_DOCUMENT_QUERIES: list[dict[str, str]] = [
    {"id": "nid_kubernetes", "group": "not_in_document", "query": "What is Kubernetes?"},
    {"id": "nid_elon_musk", "group": "not_in_document", "query": "Who is Elon Musk?"},
    {"id": "nid_quantum_computing", "group": "not_in_document", "query": "What is quantum computing?"},
    {"id": "nid_bitcoin", "group": "not_in_document", "query": "What is Bitcoin?"},
    {"id": "nid_docker", "group": "not_in_document", "query": "What is Docker?"},
]

QUERY_SETS: dict[str, list[dict[str, str]]] = {
    "relation": RELATION_QUERIES,
    "demo": DEMO_QUERIES,
    "notfound": NOT_IN_DOCUMENT_QUERIES,
    "all": RELATION_QUERIES + DEMO_QUERIES + NOT_IN_DOCUMENT_QUERIES,
}

MARKER_PATTERNS = (
    "[QUERY FAMILY]",
    "[ANSWER ROUTE]",
    "[ANSWER BLOCKED]",
    "[FACT TOPK]",
    "[FACT RETRY]",
    "[FACT RESCUE QUERY]",
    "[FACT RELATION FILTER]",
    "[FACT MULTI-CHUNK]",
    "[FACT MULTI-CHUNK FALLBACK]",
    "[FACT ANCHOR SCORE]",
    "[FACT CHUNK SELECTION]",
    "[FACT CONTEXT]",
    "[FACT EXTRACTION]",
    "[FACT OCR CLEANUP]",
    "[FACT PERSON VALIDATOR]",
    "[FACT CANDIDATE]",
    "[FACT DECISION]",
    "[FACT ACCEPTED]",
    "[FACT ANSWER GUARD]",
    "[FACT FALLBACK]",
    "[FACT METRIC]",
    "[FACT ROUTE]",
    "[FACT RANK]",
    "[OCR FILTER]",
    "[FINAL CANDIDATE REJECTED]",
    "[FINAL ANSWER SOURCE]",
    "[FINAL DECISION DEBUG]",
    "RAG_NO_MATCH",
    "not_found",
    "fact_",
)

NOT_FOUND_PATTERNS = (
    "not found in the document",
    "couldn't find",
    "could not find",
    "no relevant information",
    "not enough information",
    "not in the uploaded materials",
    "not in the uploaded help materials",
    "don't have information",
    "do not have information",
    "isn't covered",
    "is not covered",
)

ATTRIBUTION_VERBS = (
    "founded", "established", "proposed", "developed", "introduced", "created",
    "coined", "originated", "started", "formed", "discovered", "considered",
)

STOPWORDS = {
    "what", "which", "who", "whom", "whose", "when", "where", "why", "how",
    "is", "are", "was", "were", "did", "do", "does", "the", "a", "an", "of",
    "in", "on", "at", "to", "for", "from", "and", "or", "by", "it", "its", "be",
    "this", "that", "document", "about", "define", "year", "date",
}


@dataclass
class WsResult:
    answer: str
    payload: dict[str, Any]
    chunks: list[str]
    messages: list[dict[str, Any]]
    latency_ms: int
    error: str | None = None


# ---------------------------------------------------------------------------
# Verbatim helpers from scripts/phase14d_relation_evidence.py
# ---------------------------------------------------------------------------
def _session_cookie_header(session: requests.Session) -> str:
    return "; ".join(f"{c.name}={c.value}" for c in session.cookies)


def _websocket_header_kwargs(cookie_header: str) -> dict[str, Any]:
    if not cookie_header:
        return {}
    header_rows = [("Cookie", cookie_header)]
    try:
        params = inspect.signature(websockets.connect).parameters
    except Exception:
        params = {}
    if "additional_headers" in params:
        return {"additional_headers": header_rows}
    return {"extra_headers": header_rows}


def _login(login_host: str, username: str, password: str) -> requests.Session:
    session = requests.Session()
    response = session.post(
        f"{login_host}/login",
        data={"username": username, "password": password},
        allow_redirects=False,
        timeout=30,
    )
    if response.status_code not in (302, 303):
        raise RuntimeError(f"login failed status={response.status_code}: {response.text[:300]}")
    return session


def _get_json(session: requests.Session, url: str, *, timeout: int = 30) -> dict[str, Any]:
    response = session.get(url, timeout=timeout)
    response.raise_for_status()
    payload = response.json()
    return payload if isinstance(payload, dict) else {"value": payload}


def _retrieve_debug(
    session: requests.Session,
    rag_host: str,
    query: str,
    top_k: int,
    tenant_id: int | None,
) -> dict[str, Any]:
    params: dict[str, Any] = {"query": query, "top_k": top_k}
    if tenant_id is not None:
        params["tenant_id"] = int(tenant_id)
    response = session.get(f"{rag_host}/rag/retrieve-debug", params=params, timeout=120)
    response.raise_for_status()
    payload = response.json()
    return payload if isinstance(payload, dict) else {"value": payload}


def _read_log_tail(log_path: Path, start_offset: int) -> tuple[str, int]:
    if not log_path.exists():
        return "", start_offset
    with log_path.open("r", encoding="utf-8", errors="replace") as handle:
        handle.seek(start_offset)
        text = handle.read()
        return text, handle.tell()


def _log_offset(log_path: Path) -> int:
    if not log_path.exists():
        return 0
    return log_path.stat().st_size


def _marker_lines(text: str, query: str, trace_id: str) -> list[str]:
    lines: list[str] = []
    query_l = query.lower()
    trace_l = trace_id.lower()
    for line in text.splitlines():
        low = line.lower()
        marker_hit = any(marker.lower() in low for marker in MARKER_PATTERNS)
        query_hit = query_l in low or trace_l in low
        if marker_hit or query_hit:
            lines.append(line)
    return lines


def _entries_from_retrieve_debug(payload: dict[str, Any]) -> list[dict[str, Any]]:
    entries = payload.get("results") or payload.get("entries") or payload.get("rows") or []
    return entries if isinstance(entries, list) else []


def _text_from_entry(entry: dict[str, Any]) -> str:
    if not isinstance(entry, dict):
        return ""
    return str(
        entry.get("text")
        or entry.get("page_content")
        or entry.get("content")
        or entry.get("chunk")
        or entry.get("document")
        or entry.get("text_preview")
        or entry.get("preview")
        or ""
    )


def _metadata_from_entry(entry: dict[str, Any]) -> dict[str, Any]:
    metadata = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
    direct_metadata = {
        key: entry.get(key)
        for key in ("source", "file_name", "filename", "page", "chunk_index", "chapter", "section", "title", "unit", "heading")
        if entry.get(key) is not None
    }
    return {**direct_metadata, **metadata}


def _compact_entry(entry: dict[str, Any], idx: int) -> dict[str, Any]:
    text = _text_from_entry(entry)
    metadata = _metadata_from_entry(entry)
    return {
        "rank": idx + 1,
        "score": entry.get("score"),
        "rerank_score": entry.get("rerank_score") or entry.get("cross_encoder_score"),
        "chunk_index": metadata.get("chunk_index") or entry.get("chunk_index"),
        "source": metadata.get("source") or metadata.get("file_name") or metadata.get("filename") or entry.get("source"),
        "page": metadata.get("page") or entry.get("page"),
        "metadata": metadata,
        "text": re.sub(r"\s+", " ", text).strip(),
    }


def _generic_tenant_probe_score(
    session: requests.Session,
    rag_host: str,
    tenant_id: int,
    top_k: int,
    questions: list[dict[str, str]],
) -> tuple[int, dict[str, Any]]:
    score = 0
    probe_payload: dict[str, Any] = {}
    for question in questions:
        query = question["query"]
        try:
            payload = _retrieve_debug(session, rag_host, query, min(top_k, 10), tenant_id)
        except Exception as exc:
            probe_payload[query] = {"error": repr(exc)}
            continue
        entries = [
            _compact_entry(entry, idx)
            for idx, entry in enumerate(_entries_from_retrieve_debug(payload))
            if isinstance(entry, dict)
        ]
        non_empty = [entry for entry in entries if entry.get("text")]
        score += len(non_empty)
        probe_payload[query] = {
            "count": len(entries),
            "non_empty_count": len(non_empty),
            "top_sources": [entry.get("source") for entry in entries[:3]],
            "top_previews": [entry.get("text", "")[:180] for entry in entries[:3]],
        }
    return score, probe_payload


def _resolve_tenant_id(
    session: requests.Session,
    rag_host: str,
    kb_status: dict[str, Any],
    requested_tenant_id: int | None,
    tenant_candidates: list[int],
    top_k: int,
    questions: list[dict[str, str]],
) -> tuple[int | None, dict[str, Any]]:
    if requested_tenant_id is not None:
        return int(requested_tenant_id), {"mode": "explicit", "tenant_id": int(requested_tenant_id)}

    status_tenant = kb_status.get("tenant_id")
    if status_tenant is not None:
        return int(status_tenant), {"mode": "kb_status_preferred", "tenant_id": int(status_tenant)}

    scored: list[dict[str, Any]] = []
    for tenant_id in tenant_candidates:
        score, probe = _generic_tenant_probe_score(session, rag_host, tenant_id, top_k, questions)
        scored.append({"tenant_id": tenant_id, "score": score, "probe": probe})

    chosen = max(scored, key=lambda item: int(item.get("score") or 0), default=None)
    if chosen and int(chosen.get("score") or 0) > 0:
        return int(chosen["tenant_id"]), {"mode": "generic_non_empty_retrieval_probe", "chosen": chosen, "candidates": scored}
    return None, {"mode": "no_tenant_detected", "candidates": scored}


def _timing_summary(payload: dict[str, Any], latency_ms: int) -> dict[str, Any]:
    timing = payload.get("timing") if isinstance(payload, dict) else {}
    timing = timing if isinstance(timing, dict) else {}
    return {
        "retrieval_ms": timing.get("retrieval_ms"),
        "rerank_ms": timing.get("rerank_ms"),
        "answer_generation_ms": timing.get("answer_generation_ms"),
        "total_ms": timing.get("total_ms") or latency_ms,
        "query_family_v2": timing.get("query_family_v2") or timing.get("phase14_query_family_v2"),
        "answer_type": timing.get("answer_type") or timing.get("phase14_answer_type") or timing.get("branch"),
        "used_llm": timing.get("used_llm"),
        "selected_context_count": len(timing.get("phase14_selected_context") or []),
    }


async def _run_ws_query(
    *,
    ws_url: str,
    cookie_header: str,
    query: str,
    trace_id: str,
    tenant_id: int | None,
    timeout_s: float,
) -> WsResult:
    started = time.perf_counter()
    chunks: list[str] = []
    messages: list[dict[str, Any]] = []
    done_payload: dict[str, Any] = {}
    connect_kwargs = _websocket_header_kwargs(cookie_header)

    try:
        async with websockets.connect(ws_url, **connect_kwargs) as websocket:
            payload: dict[str, Any] = {
                "text": query,
                "language": "en",
                "tts_enabled": False,
                "phase14_trace": True,
                "client_trace_id": trace_id,
            }
            if tenant_id is not None:
                payload["tenant_id"] = int(tenant_id)
            await websocket.send(json.dumps(payload))
            while True:
                raw = await asyncio.wait_for(websocket.recv(), timeout=timeout_s)
                if isinstance(raw, bytes):
                    continue
                try:
                    message = json.loads(raw)
                except json.JSONDecodeError:
                    message = {"type": "raw", "text": raw}
                if not isinstance(message, dict):
                    continue
                messages.append(message)
                if message.get("type") == "aiResponseChunk":
                    chunks.append(str(message.get("text") or ""))
                if message.get("type") == "aiResponseDone":
                    done_payload = message
                    break
                if message.get("type") == "error" or message.get("error"):
                    done_payload = message
                    break
    except Exception as exc:
        elapsed = int(round((time.perf_counter() - started) * 1000))
        return WsResult(answer="", payload=done_payload, chunks=chunks, messages=messages, latency_ms=elapsed, error=repr(exc))

    elapsed = int(round((time.perf_counter() - started) * 1000))
    answer = str(done_payload.get("fullText") or "".join(chunks))
    return WsResult(answer=answer, payload=done_payload, chunks=chunks, messages=messages, latency_ms=elapsed)


def _is_not_found(answer: str) -> bool:
    low = str(answer or "").lower()
    return any(pattern in low for pattern in NOT_FOUND_PATTERNS)


# ---------------------------------------------------------------------------
# Fact-marker capture (new)
# ---------------------------------------------------------------------------
def _lines_with(lines: list[str], needle: str) -> list[str]:
    return [ln for ln in lines if needle in ln]


_ANSWER_ROUTE_FACT_RE = re.compile(r"\[ANSWER ROUTE\]\s+mode=fact\s+(.*)")
_DETERMINISTIC_RE = re.compile(r"deterministic=(true|false)")
_ROUTE_ANSWER_RE = re.compile(r"answer=(.*)$")
_FACT_CANDIDATE_RE = re.compile(
    r"\[FACT CANDIDATE\]\s+rank=(?P<rank>\d+)\s+type=(?P<type>\S+)\s+chunk=(?P<chunk>\S+)\s+score=(?P<score>[\d.]+)\s+candidate=(?P<candidate>.*?)\s+sentence=(?P<sentence>.*)$"
)
_FACT_DECISION_RE = re.compile(r"\[FACT DECISION\]\s+type=(?P<type>\S+)\s+final=(?P<final>.*?)\s+score=", re.IGNORECASE)
_FACT_ACCEPTED_RE = re.compile(r"\[FACT ACCEPTED\]\s+value=(?P<value>.*)$")


def _parse_answer_route_fact(lines: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {"deterministic": None, "answer": None, "raw": []}
    for ln in _lines_with(lines, "[ANSWER ROUTE]"):
        m = _ANSWER_ROUTE_FACT_RE.search(ln)
        if not m:
            continue
        out["raw"].append(ln.strip())
        det = _DETERMINISTIC_RE.search(ln)
        if det:
            out["deterministic"] = det.group(1) == "true"
        ans = _ROUTE_ANSWER_RE.search(ln)
        if ans:
            out["answer"] = ans.group(1).strip()
    return out


def _parse_fact_candidates(lines: list[str]) -> list[dict[str, Any]]:
    cands: list[dict[str, Any]] = []
    for ln in _lines_with(lines, "[FACT CANDIDATE]"):
        m = _FACT_CANDIDATE_RE.search(ln)
        if not m:
            continue
        cands.append(
            {
                "rank": int(m.group("rank")),
                "type": m.group("type"),
                "chunk": m.group("chunk"),
                "score": float(m.group("score")),
                "candidate": m.group("candidate").strip(),
                "sentence": m.group("sentence").strip(),
            }
        )
    return cands


def _parse_fact_decision(lines: list[str]) -> str | None:
    for ln in _lines_with(lines, "[FACT DECISION]"):
        m = _FACT_DECISION_RE.search(ln)
        if m:
            return m.group("final").strip()
    return None


def _parse_fact_accepted(lines: list[str]) -> str | None:
    for ln in _lines_with(lines, "[FACT ACCEPTED]"):
        m = _FACT_ACCEPTED_RE.search(ln)
        if m:
            return m.group("value").strip()
    return None


# ---------------------------------------------------------------------------
# Generic, answer-key-free evidence analysis (Step 2 inputs)
# ---------------------------------------------------------------------------
def _subject_terms(query: str) -> list[str]:
    toks = re.findall(r"[a-z0-9]+", str(query or "").lower())
    verbs = set(ATTRIBUTION_VERBS) | {"found", "founder", "create", "develop", "propose", "establish", "introduce"}
    return [t for t in toks if len(t) > 2 and t not in STOPWORDS and t not in verbs]


def _is_who_query(query: str) -> bool:
    return bool(re.match(r"^\s*who\b", str(query or "").strip().lower()))


def _is_relation_attribution_query(query: str) -> bool:
    q = str(query or "").lower()
    return _is_who_query(query) and bool(re.search(r"\b(found|founded|founder|created|develop|developed|proposed|established|introduced|coined|discovered)\b", q))


_PERSON_TOKEN = r"(?:[A-Z][a-z]+|[A-Z]\.)"
_PERSON_RE = rf"{_PERSON_TOKEN}(?:\s+{_PERSON_TOKEN}){{0,3}}"
_ACTIVE_ATTR_RE = re.compile(
    rf"\b({_PERSON_RE})\s+(?:has\s+)?(?:{'|'.join(ATTRIBUTION_VERBS)})\b"
)
_PASSIVE_ATTR_RE = re.compile(
    rf"\b(?:{'|'.join(ATTRIBUTION_VERBS)})\s+by\s+({_PERSON_RE})\b", re.IGNORECASE
)
_FATHER_RE = re.compile(rf"\b({_PERSON_RE})\s+(?:is\s+)?(?:considered\s+)?the\s+father\s+of\b", re.IGNORECASE)

_NON_NAME_TOKENS = {
    "The", "This", "That", "These", "Those", "Psychology", "Gestalt", "Table", "Figure",
    "Chapter", "Unit", "Theory", "Model", "Approach", "School", "Schools", "Germany",
    "England", "France", "Greek", "Greece", "Leipzig", "Introduction", "Lesson",
}


def _attribution_names(text: str) -> list[str]:
    """Generic person-name candidates appearing in attribution sentences.

    No name list   purely capitalization shape + attribution-verb context.
    """
    names: list[str] = []
    for rx in (_ACTIVE_ATTR_RE, _PASSIVE_ATTR_RE, _FATHER_RE):
        for m in rx.finditer(text or ""):
            cand = re.sub(r"\s+", " ", m.group(1) or "").strip(" .,:;")
            parts = cand.split()
            if not parts:
                continue
            if any(p in _NON_NAME_TOKENS for p in parts):
                continue
            if len(parts) == 1 and len(parts[0]) < 4:
                continue
            names.append(cand)
    # dedup preserving order
    seen: set[str] = set()
    out: list[str] = []
    for n in names:
        k = n.lower()
        if k not in seen:
            seen.add(k)
            out.append(n)
    return out


def _name_key(name: str) -> str:
    """Last alphabetic token, lowercased   robust comparison key for a person."""
    toks = re.findall(r"[A-Za-z]+", str(name or ""))
    toks = [t for t in toks if len(t) > 1]
    return toks[-1].lower() if toks else str(name or "").strip().lower()


def _text_has_subject(text: str, subject_terms: list[str]) -> bool:
    low = str(text or "").lower()
    return any(re.search(rf"\b{re.escape(t)}\b", low) for t in subject_terms)


def _root_cause_signals(query: str, det: dict[str, Any], entries: list[dict[str, Any]]) -> dict[str, Any]:
    """Derive the Step 2 matrix signals generically from rerank order.

    entries: compact retrieve-debug entries in rerank order (rank 1 = top).
    det: parsed [ANSWER ROUTE] mode=fact result (deterministic flag + answer).
    """
    subj = _subject_terms(query)
    top_band = entries[:3]

    # Per-chunk attribution names + subject presence (rerank order).
    chunk_evidence: list[dict[str, Any]] = []
    for e in entries:
        txt = e.get("text") or ""
        chunk_evidence.append(
            {
                "rank": e.get("rank"),
                "has_subject": _text_has_subject(txt, subj),
                "attribution_names": _attribution_names(txt),
            }
        )

    # "Retrieval Contains Correct Answer?"   generic: a top-band chunk has the
    # query subject term AND an attribution-shaped person sentence (relation),
    # or for plain identity ("who is X") simply the subject term present.
    if _is_relation_attribution_query(query):
        retrieval_contains = any(
            ce["has_subject"] and ce["attribution_names"] for ce in chunk_evidence[:3]
        )
    else:
        retrieval_contains = any(ce["has_subject"] for ce in chunk_evidence[:3])

    deterministic_ran = bool(det.get("deterministic") is True and det.get("answer"))
    det_answer = str(det.get("answer") or "").strip()
    det_key = _name_key(det_answer) if det_answer else ""

    # Top-band valid attribution names (only chunks that also mention subject).
    top_attr_names: list[str] = []
    for ce in chunk_evidence[:2]:
        if ce["has_subject"]:
            top_attr_names.extend(ce["attribution_names"])
    top_attr_keys = {_name_key(n) for n in top_attr_names}

    # Rank where the deterministic answer first appears in an attribution sentence.
    det_origin_rank: int | None = None
    if det_key:
        for ce in chunk_evidence:
            if any(_name_key(n) == det_key for n in ce["attribution_names"]):
                det_origin_rank = ce["rank"]
                break

    overrode_better = False
    if deterministic_ran and det_key and top_attr_keys and det_key not in top_attr_keys:
        # A conflicting valid attribution name exists in the top band, but the
        # deterministic answer was sourced from a strictly lower rank (or not
        # present in the top band at all).
        if det_origin_rank is None or det_origin_rank > 2:
            overrode_better = True

    improved = bool(
        deterministic_ran
        and det_key
        and det_origin_rank is not None
        and det_origin_rank <= 2
        and not overrode_better
    )

    harmed = bool(
        deterministic_ran
        and (
            overrode_better
            or (retrieval_contains and _is_relation_attribution_query(query) and det_key and det_key not in top_attr_keys)
        )
    )

    return {
        "subject_terms": subj,
        "retrieval_contains_correct": retrieval_contains,
        "deterministic_ran": deterministic_ran,
        "det_answer": det_answer,
        "det_origin_rank": det_origin_rank,
        "top_band_attribution_names": top_attr_names,
        "improved": improved,
        "harmed": harmed,
        "overrode_better_evidence": overrode_better,
        "chunk_evidence": chunk_evidence[:8],
    }


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------
def _bool_cell(value: Any) -> str:
    if value is True:
        return "YES"
    if value is False:
        return "NO"
    return "?"


def _report_markdown(results: list[dict[str, Any]], meta: dict[str, Any]) -> str:
    lines: list[str] = [
        "# Phase 14D-C   Fact Extraction Authority Audit",
        "",
        f"Generated: `{meta.get('generated_at')}`",
        f"Tenant: `{meta.get('tenant_id')}` (detection: `{meta.get('tenant_detection_mode')}`)",
        f"Log path: `{meta.get('log_path')}` (markers captured: `{meta.get('log_capture_ok')}`)",
        "",
        "## Step 2   Root-Cause Matrix (relation / who queries)",
        "",
        "Signals are derived generically from rerank order + attribution-verb sentence",
        "shape. No answer keys are used. `Contains Correct Answer` = a top-band chunk",
        "carries the query subject term AND an attribution-shaped person sentence.",
        "`Overrode Better Evidence` = deterministic answer was sourced below the top band",
        "while a conflicting valid attribution name sits in the top band.",
        "",
        "| Query | Contains Correct Answer? | Deterministic Ran? | Improved? | Harmed? | Overrode Better Evidence? | Det Answer | Det Origin Rank |",
        "| --- | :---: | :---: | :---: | :---: | :---: | --- | :---: |",
    ]
    for r in results:
        if r.get("group") != "relation":
            continue
        sig = r.get("root_cause") or {}
        lines.append(
            "| `{q}` | {cc} | {dr} | {imp} | {harm} | {ov} | `{ans}` | {orank} |".format(
                q=r["query"],
                cc=_bool_cell(sig.get("retrieval_contains_correct")),
                dr=_bool_cell(sig.get("deterministic_ran")),
                imp=_bool_cell(sig.get("improved")),
                harm=_bool_cell(sig.get("harmed")),
                ov=_bool_cell(sig.get("overrode_better_evidence")),
                ans=(sig.get("det_answer") or "(none)"),
                orank=(sig.get("det_origin_rank") if sig.get("det_origin_rank") is not None else "-"),
            )
        )

    # Tally
    rel = [r for r in results if r.get("group") == "relation"]
    improved = sum(1 for r in rel if (r.get("root_cause") or {}).get("improved"))
    harmed = sum(1 for r in rel if (r.get("root_cause") or {}).get("harmed"))
    overrode = sum(1 for r in rel if (r.get("root_cause") or {}).get("overrode_better_evidence"))
    det_ran = sum(1 for r in rel if (r.get("root_cause") or {}).get("deterministic_ran"))
    lines.extend(
        [
            "",
            "### Tally",
            "",
            f"- Relation queries: `{len(rel)}`",
            f"- Deterministic extractor ran: `{det_ran}`",
            f"- Improved: `{improved}`",
            f"- Harmed: `{harmed}`",
            f"- Overrode better evidence: `{overrode}`",
            "",
            f"**Authority recommendation:** {'Case A (harms >= improves)   restrict/disable deterministic authority for relation/who and route via guard' if harmed >= improved else 'Case B (helps some)   keep deterministic under strict rank-aware acceptance'}",
            "",
        ]
    )

    # Out-of-document regression summary
    nid = [r for r in results if r.get("group") == "not_in_document"]
    if nid:
        lines.extend(["## Out-of-Document Regression", "", "| Query | Grounded Not-Found? | Answer (preview) |", "| --- | :---: | --- |"])
        for r in nid:
            lines.append(
                f"| `{r['query']}` | {_bool_cell(r.get('is_not_found'))} | {(r.get('answer') or '').strip()[:140] or '(empty)'} |"
            )
        lines.append("")

    # Per-query detail
    lines.append("## Per-Query Evidence")
    for r in results:
        ts = r.get("timing_summary", {})
        det = r.get("answer_route_fact", {})
        lines.extend(
            [
                "",
                f"### {r['id']}",
                "",
                f"Group: `{r['group']}`  |  Query: `{r['query']}`",
                f"Trace: `{r['trace_id']}`  |  Tenant: `{r.get('tenant_id')}`",
                f"Query family: `{ts.get('query_family_v2')}`  |  answer_type: `{ts.get('answer_type')}`  |  used_llm: `{ts.get('used_llm')}`",
                f"Latency: `{ts.get('total_ms')} ms`  |  Not found: `{r.get('is_not_found')}`",
                f"Route deterministic flag (log): `{det.get('deterministic')}`  |  route answer (log): `{det.get('answer')}`",
                "",
                "Answer:",
                "",
                (r.get("answer") or "").strip() or "(empty)",
                "",
                "Fact candidate ranking (from [FACT CANDIDATE]):",
                "",
            ]
        )
        cands = r.get("fact_candidates") or []
        if not cands:
            lines.append("(none captured)")
        for c in cands[:8]:
            lines.append(
                f"- rank `{c['rank']}` type `{c['type']}` chunk `{c['chunk']}` score `{c['score']:.3f}` -> `{c['candidate']}`  | {c['sentence'][:160]}"
            )

        lines.extend(["", "Top reranked chunks (ground-truth order):", ""])
        for e in (r.get("retrieved_chunks") or [])[:5]:
            lines.append(
                f"- rank `{e.get('rank')}` score `{e.get('score')}` rerank `{e.get('rerank_score')}` chunk `{e.get('chunk_index')}` source `{e.get('source')}`"
            )
            lines.append(f"  - {(e.get('text') or '')[:400]}")

        rc = r.get("root_cause")
        if rc:
            lines.extend(
                [
                    "",
                    "Root-cause signals:",
                    "",
                    f"- subject_terms: `{rc.get('subject_terms')}`",
                    f"- retrieval_contains_correct: `{rc.get('retrieval_contains_correct')}`",
                    f"- top_band_attribution_names: `{rc.get('top_band_attribution_names')}`",
                    f"- det_origin_rank: `{rc.get('det_origin_rank')}`",
                ]
            )

        lines.extend(["", "Fact log markers:", ""])
        markers = (
            _lines_with(r.get("log_markers") or [], "[ANSWER ROUTE]")
            + _lines_with(r.get("log_markers") or [], "[FACT DECISION]")
            + _lines_with(r.get("log_markers") or [], "[FACT ACCEPTED]")
            + _lines_with(r.get("log_markers") or [], "[FACT CONTEXT]")
            + _lines_with(r.get("log_markers") or [], "[FACT FALLBACK]")
        )
        if not markers:
            lines.append("(none captured)")
        for m in markers[:40]:
            lines.append(f"- `{m.strip()}`")

    return "\n".join(lines).rstrip() + "\n"


async def run_audit(args: argparse.Namespace) -> int:
    login_host = args.login_host.rstrip("/")
    rag_host = args.rag_host.rstrip("/")
    log_path = Path(args.log_path)
    output_dir = Path(args.output_dir)

    questions = QUERY_SETS.get(args.query_set, QUERY_SETS["all"])

    session = _login(login_host, args.username, args.password)
    cookie_header = _session_cookie_header(session)
    kb_status = _get_json(session, f"{rag_host}/kb_status", timeout=60)
    tenant_candidates = [int(x) for x in str(args.tenant_candidates).split(",") if str(x).strip()]
    tenant_id, tenant_detection = _resolve_tenant_id(
        session, rag_host, kb_status, args.tenant_id, tenant_candidates, args.top_k, questions
    )

    log_capture_ok = log_path.exists()

    results: list[dict[str, Any]] = []
    log_cursor = _log_offset(log_path)
    for question in questions:
        trace_id = f"phase14dc-{question['id']}-{int(time.time() * 1000)}"
        retrieval = _retrieve_debug(session, rag_host, question["query"], args.top_k, tenant_id)
        retrieved_chunks = [
            _compact_entry(entry, idx)
            for idx, entry in enumerate(_entries_from_retrieve_debug(retrieval))
            if isinstance(entry, dict)
        ]
        ws = await _run_ws_query(
            ws_url=args.ws_url,
            cookie_header=cookie_header,
            query=question["query"],
            trace_id=trace_id,
            tenant_id=tenant_id,
            timeout_s=args.timeout,
        )
        # Give the log a moment to flush the trailing markers for this query.
        await asyncio.sleep(args.log_settle)
        log_text, log_cursor = _read_log_tail(log_path, log_cursor)
        marker_lines = _marker_lines(log_text, question["query"], trace_id)

        answer_route_fact = _parse_answer_route_fact(marker_lines)
        fact_candidates = _parse_fact_candidates(marker_lines)
        result: dict[str, Any] = {
            **question,
            "trace_id": trace_id,
            "tenant_id": tenant_id,
            "retrieved_chunks": retrieved_chunks,
            "ws_payload": ws.payload,
            "ws_error": ws.error,
            "answer": ws.answer,
            "is_not_found": _is_not_found(ws.answer) or bool(ws.error),
            "timing_summary": _timing_summary(ws.payload, ws.latency_ms),
            "log_markers": marker_lines,
            "answer_route_fact": answer_route_fact,
            "fact_candidates": fact_candidates,
            "fact_decision": _parse_fact_decision(marker_lines),
            "fact_accepted": _parse_fact_accepted(marker_lines),
        }
        if question["group"] == "relation":
            result["root_cause"] = _root_cause_signals(question["query"], answer_route_fact, retrieved_chunks)
        results.append(result)

    meta = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "tenant_id": tenant_id,
        "tenant_detection_mode": tenant_detection.get("mode"),
        "log_path": str(log_path),
        "log_capture_ok": log_capture_ok,
        "query_set": args.query_set,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"phase14d_fact_authority_audit{args.suffix}.json"
    md_path = output_dir / f"phase14d_fact_authority_audit{args.suffix}.md"
    json_path.write_text(json.dumps({"meta": meta, "results": results}, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(_report_markdown(results, meta), encoding="utf-8")

    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")
    if not log_capture_ok:
        print(f"WARNING: log path {log_path} not found   fact markers not captured. Restart stack with --service-logs.")
    for r in results:
        ts = r.get("timing_summary", {})
        det = r.get("answer_route_fact", {})
        status = "NOTFOUND" if r.get("is_not_found") else "ANSWER"
        print(
            f"{status:9s} {r['id']:32s} det={det.get('deterministic')} "
            f"family={ts.get('query_family_v2')} total_ms={ts.get('total_ms')}"
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Phase 14D-C fact extraction authority audit.")
    parser.add_argument("--login-host", default=LOGIN_HOST)
    parser.add_argument("--rag-host", default=RAG_HOST)
    parser.add_argument("--ws-url", default=WS_URL)
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", default="admin")
    parser.add_argument("--tenant-id", type=int, default=None)
    parser.add_argument("--tenant-candidates", default="1,2,3,4,5")
    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument("--timeout", type=float, default=240.0)
    parser.add_argument("--log-settle", type=float, default=0.6)
    parser.add_argument("--query-set", choices=sorted(QUERY_SETS.keys()), default="all")
    parser.add_argument("--output-dir", default="logs")
    parser.add_argument("--log-path", default="logs/rag.log")
    parser.add_argument("--suffix", default="", help="Suffix for output filenames, e.g. _before / _after")
    return parser


def main() -> int:
    return asyncio.run(run_audit(build_parser().parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
