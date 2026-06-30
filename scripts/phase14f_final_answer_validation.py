"""Phase 14F - final answer reliability validation (attribute, table, compare, definitions)."""

from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
import websockets

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.retrieval.generation import _resolve_grounded_answer_route
from backend.retrieval.routing import (
    _classify_query_family_v2,
    _compare_all_class_tokens,
    _compare_entities_from_query,
    _extract_best_faq_answer,
    _is_attribute_lookup_query,
)

LOGIN_HOST = "http://127.0.0.1:7001"
RAG_HOST = "http://127.0.0.1:7000"
WS_URL = "ws://127.0.0.1:7000/ws"

FAQ_QUERIES: list[dict[str, Any]] = [
    {
        "id": "faq_password_reset",
        "group": "faq",
        "query": "How do I reset my password?",
        "forbidden_tokens": ["invite", "sso", "transfer ownership", "teammate"],
    },
    {
        "id": "faq_add_teammate",
        "group": "faq",
        "query": "How do I add a teammate?",
        "forbidden_tokens": ["forgot password", "sso", "transfer ownership"],
    },
    {
        "id": "faq_sso",
        "group": "faq",
        "query": "Can I use SSO?",
        "forbidden_tokens": ["forgot password", "invite", "transfer ownership"],
    },
    {
        "id": "faq_transfer_ownership",
        "group": "faq",
        "query": "How do I transfer ownership?",
        "forbidden_tokens": ["forgot password", "invite", "sso"],
    },
]

COMPARE_QUERIES: list[dict[str, Any]] = [
    {
        "id": "cmp_starter_growth",
        "group": "compare",
        "query": "Compare Starter and Growth plans",
        "expected_entities": ["starter", "growth"],
    },
    {
        "id": "cmp_growth_enterprise",
        "group": "compare",
        "query": "Compare Growth and Enterprise plans",
        "expected_entities": ["growth", "enterprise"],
    },
    {
        "id": "cmp_three_plans",
        "group": "compare",
        "query": "Compare Growth, Business, and Enterprise plans",
        "expected_entities": ["growth", "business", "enterprise"],
    },
    {
        "id": "cmp_vm_general_gpu",
        "group": "compare",
        "query": "Compare General and GPU VM families",
        "expected_entities": ["general", "gpu"],
    },
    {
        "id": "cmp_vm_general_memory",
        "group": "compare",
        "query": "Compare General and Memory-Optimized VM families",
        "expected_entities": ["general", "memory-optimized"],
    },
    {
        "id": "cmp_all_plans",
        "group": "compare",
        "query": "Compare all plans",
        "expected_entities": [],
        "compare_all": True,
    },
    {
        "id": "cmp_all_vm",
        "group": "compare",
        "query": "Compare all VM families",
        "expected_entities": [],
        "compare_all": True,
    },
]

ATTRIBUTE_QUERIES: list[dict[str, str]] = [
    {"id": "attr_tam", "group": "attribute", "query": "Which plan includes a named TAM?"},
    {"id": "attr_sso", "group": "attribute", "query": "Which plans support SSO?"},
    {"id": "attr_hipaa", "group": "attribute", "query": "Which plan includes HIPAA?"},
    {"id": "attr_audit", "group": "attribute", "query": "Which plan includes audit logs?"},
    {"id": "attr_support_growth", "group": "attribute", "query": "What is the support response time for Growth?"},
    {"id": "attr_support_business", "group": "attribute", "query": "What is the support response time for Business?"},
    {"id": "attr_support_enterprise", "group": "attribute", "query": "What is the support response time for Enterprise?"},
]

DEFINITION_QUERIES: list[dict[str, str]] = [
    {"id": "def_freud", "group": "definition", "query": "Who is Freud?"},
    {"id": "def_jung", "group": "definition", "query": "Who is Jung?"},
    {"id": "def_elon", "group": "definition", "query": "Who is Elon Musk?"},
    {"id": "def_k8s", "group": "definition", "query": "What is Kubernetes?"},
]

RELATION_QUERIES: list[dict[str, str]] = [
    {"id": "rel_structuralism", "group": "relation", "query": "Who founded structuralism?"},
    {"id": "rel_gestalt", "group": "relation", "query": "Who founded Gestalt psychology?"},
    {"id": "rel_psychoanalysis", "group": "relation", "query": "Who created psychoanalysis?"},
    {"id": "rel_analytical", "group": "relation", "query": "Who developed analytical psychology?"},
]

TABLE_QUERIES: list[dict[str, str]] = [
    {"id": "tbl_vm_db", "group": "vm", "query": "Which VM family is best for databases?"},
    {"id": "tbl_vm_memory", "group": "vm", "query": "Which VM family has the most memory?"},
    {"id": "tbl_vm_ml", "group": "vm", "query": "Which VM family is best for machine learning?"},
    {"id": "tbl_vm_render", "group": "vm", "query": "Which VM family is best for rendering?"},
    {"id": "tbl_hipaa", "group": "attribute", "query": "Which plan includes HIPAA support?"},
    {"id": "tbl_sso_plans", "group": "attribute", "query": "Which plans support SSO?"},
]

VALIDATION_QUESTIONS: list[dict[str, Any]] = (
    FAQ_QUERIES
    + ATTRIBUTE_QUERIES
    + TABLE_QUERIES
    + COMPARE_QUERIES
    + DEFINITION_QUERIES
    + RELATION_QUERIES
)

MARKER_PATTERNS = (
    "[FAQ PAIR SELECT]",
    "[COMPARE ENTITIES]",
    "[COMPARE TABLE EVIDENCE]",
    "[SUPPORT PROCEDURAL RESCUE]",
    "[RAG QUALITY FILTER]",
    "heading_dominated",
    "[FINAL ANSWER SOURCE]",
    "[ANSWER ROUTE]",
)

NOT_FOUND_PATTERNS = (
    "not found in the document",
    "couldn't find",
    "could not find",
    "no relevant information",
    "not enough information",
    "not in the uploaded materials",
    "not in the uploaded help materials",
)

STRUCTURAL_METADATA_KEYS = ("chapter", "section", "title", "unit", "heading")


@dataclass
class WsResult:
    answer: str
    payload: dict[str, Any]
    chunks: list[str]
    messages: list[dict[str, Any]]
    latency_ms: int
    error: str | None = None


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
        for key in (
            "source",
            "file_name",
            "filename",
            "page",
            "chunk_index",
            "chapter",
            "section",
            "title",
            "unit",
            "heading",
        )
        if entry.get(key) is not None
    }
    return {**direct_metadata, **metadata}


def _compact_entry(entry: dict[str, Any], idx: int) -> dict[str, Any]:
    text = _text_from_entry(entry)
    metadata = _metadata_from_entry(entry)
    structural_metadata = {
        key: re.sub(r"\s+", " ", str(metadata.get(key) or "")).strip()
        for key in STRUCTURAL_METADATA_KEYS
        if str(metadata.get(key) or "").strip()
    }
    return {
        "rank": idx + 1,
        "score": entry.get("score"),
        "rerank_score": entry.get("rerank_score") or entry.get("cross_encoder_score"),
        "chunk_index": metadata.get("chunk_index") or entry.get("chunk_index"),
        "source": metadata.get("source") or metadata.get("file_name") or metadata.get("filename") or entry.get("source"),
        "page": metadata.get("page") or entry.get("page"),
        "metadata": metadata,
        "structural_metadata": structural_metadata,
        "text": re.sub(r"\s+", " ", text).strip(),
    }


def _query_terms(query: str) -> list[str]:
    stop = {
        "what",
        "which",
        "does",
        "the",
        "this",
        "document",
        "covered",
        "cover",
        "covers",
        "list",
        "major",
        "main",
        "topics",
        "topic",
        "subjects",
        "subject",
        "chapters",
        "chapter",
        "concepts",
        "concept",
        "themes",
        "theme",
        "who",
        "founded",
        "created",
        "developed",
        "proposed",
        "discovered",
        "is",
        "was",
        "are",
        "a",
        "an",
        "of",
        "in",
    }
    return [tok for tok in re.findall(r"[a-z0-9]+", query.lower()) if len(tok) > 2 and tok not in stop]


def _evidence_hint(query: str, entries: list[dict[str, Any]]) -> dict[str, Any]:
    terms = _query_terms(query)
    if not terms:
        return {"query_term_presence": "unknown", "matched_ranks": []}
    matched = []
    for entry in entries:
        text = str(entry.get("text") or "").lower()
        metadata_text = " ".join(str(v) for v in (entry.get("structural_metadata") or {}).values()).lower()
        hits = [term for term in terms if term in text or term in metadata_text]
        if hits:
            matched.append({"rank": entry.get("rank"), "terms": hits, "preview": entry.get("text", "")[:240]})
    return {
        "query_term_presence": "needs_review" if matched else "no_term_hit",
        "matched_ranks": matched[:8],
    }


def _candidate_lines(lines: list[str]) -> list[str]:
    return [line for line in lines if "[FACT CANDIDATE]" in line]


def _decision_lines(lines: list[str]) -> list[str]:
    return [line for line in lines if "[FACT DECISION]" in line or "[FACT ACCEPTED]" in line]


def _topic_marker_lines(lines: list[str]) -> list[str]:
    return [line for line in lines if "[LIST" in line or "[SECTION" in line or "[STRUCTURE" in line or "[LEXICAL" in line]


def _marker_summary(lines: list[str]) -> list[str]:
    counts: dict[str, int] = {}
    for line in lines:
        for marker in MARKER_PATTERNS:
            if marker.lower() in line.lower():
                counts[marker] = counts.get(marker, 0) + 1
                break
    return [f"`{marker}` x{count}" for marker, count in sorted(counts.items())]


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
        non_empty = [entry for entry in entries if entry.get("text") or entry.get("structural_metadata")]
        score += len(non_empty)
        score += sum(1 for entry in non_empty if _evidence_hint(query, [entry]).get("matched_ranks"))
        probe_payload[query] = {
            "count": len(entries),
            "non_empty_count": len(non_empty),
            "top_sources": [entry.get("source") for entry in entries[:3]],
            "top_metadata": [entry.get("structural_metadata") for entry in entries[:3]],
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
        "phase14_retrieved_count": timing.get("phase14_retrieved_count"),
        "query_family_v2": timing.get("query_family_v2") or timing.get("phase14_query_family_v2"),
        "selected_context_count": len(timing.get("phase14_selected_context") or []),
        "selected_context": timing.get("phase14_selected_context") or [],
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


def _evaluate_result(question: dict[str, Any], answer: str, retrieved_chunks: list[dict[str, Any]], marker_lines: list[str]) -> dict[str, Any]:
    group = str(question.get("group") or "")
    answer_l = str(answer or "").lower()
    issues: list[str] = []
    passed = True

    if _is_not_found(answer):
        issues.append("not_found_answer")
        passed = False

    if group == "faq":
        query_tokens = [t for t in re.findall(r"[a-z0-9]{3,}", str(question.get("query") or "").lower()) if t not in {"how", "can", "the", "and", "for", "you", "your"}]
        if query_tokens and not any(token in answer_l for token in query_tokens):
            issues.append("faq_query_tokens_missing_in_answer")
            passed = False
        for token in question.get("forbidden_tokens") or []:
            if str(token).lower() in answer_l:
                issues.append(f"faq_contamination:{token}")
                passed = False

    if group == "compare":
        entities = _compare_entities_from_query(str(question.get("query") or ""))
        expected = [str(x).lower() for x in (question.get("expected_entities") or [])]
        if entities != expected:
            issues.append(f"entity_mismatch:got={entities}:expected={expected}")
            passed = False
        if any("," in entity for entity in entities):
            issues.append("merged_entity_string")
            passed = False
        marker_blob = "\n".join(marker_lines).lower()
        if expected and passed and not any("compare entities" in marker_blob for _ in [0]):
            issues.append("missing_compare_entities_log")
            passed = False

    if group == "table":
        dropped = [
            entry for entry in retrieved_chunks
            if str(entry.get("drop_reason") or entry.get("quality_reason") or "").lower() == "heading_dominated"
        ]
        if dropped:
            issues.append(f"heading_dominated_drops:{len(dropped)}")
            passed = False
        if not answer_l.strip():
            issues.append("empty_answer")
            passed = False

    return {"passed": passed, "issues": issues, "entities": _compare_entities_from_query(str(question.get("query") or ""))}


def run_offline_checks() -> tuple[int, list[dict[str, Any]]]:
    results: list[dict[str, Any]] = []
    faq_blob = (
        "Q: How do I reset my password? A: Go to login and click Forgot Password. "
        "Q: How do I add a teammate? A: Open Settings and click Invite Member."
    )
    faq_answer = _extract_best_faq_answer("How do I reset my password?", faq_blob) or ""
    results.append(
        {
            "id": "offline_faq_pair",
            "passed": "forgot password" in faq_answer.lower() and "invite" not in faq_answer.lower(),
            "issues": [],
        }
    )
    for question in COMPARE_QUERIES:
        entities = _compare_entities_from_query(question["query"])
        expected = question.get("expected_entities") or []
        if question.get("compare_all"):
            ok = bool(_compare_all_class_tokens(question["query"]))
        else:
            ok = entities == expected and not any("," in entity for entity in entities)
        results.append({"id": f"offline_{question['id']}", "passed": ok, "issues": [], "entities": entities})
    for question in ATTRIBUTE_QUERIES:
        query = question["query"]
        family = _classify_query_family_v2(query)
        route = _resolve_grounded_answer_route(query)
        ok = _is_attribute_lookup_query(query) and family == "attribute_lookup" and route == "attribute"
        results.append(
            {
                "id": f"offline_{question['id']}",
                "passed": ok,
                "issues": [] if ok else [f"family={family}", f"route={route}"],
                "family_v2": family,
                "answer_route": route,
            }
        )
    for question in DEFINITION_QUERIES:
        query = question["query"]
        family = _classify_query_family_v2(query)
        ok = family == "definition_entity"
        results.append({"id": f"offline_{question['id']}", "passed": ok, "family_v2": family, "issues": []})
    passed_count = sum(1 for item in results if item.get("passed"))
    return passed_count, results


def _is_not_found_answer(answer: str) -> bool:
    low = str(answer or "").lower()
    return any(pattern in low for pattern in NOT_FOUND_PATTERNS)


def _report_markdown(results: list[dict[str, Any]]) -> str:
    lines = [
        "# Phase 14F Final Answer Reliability Validation",
        "",
        "## Evidence Matrix",
        "",
        "| Group | Query | Query Family | Retrieval Hint | Answer Returned | Total ms | Marker Summary |",
        "| --- | --- | --- | --- | --- | ---: | --- |",
    ]
    for result in results:
        hint = result.get("evidence_hint", {}).get("query_term_presence", "unknown")
        answer_status = "NO" if result.get("is_not_found") else "YES"
        markers = "; ".join(result.get("marker_summary") or []) or "(none captured)"
        lines.append(
            f"| `{result['group']}` | `{result['query']}` | "
            f"`{result.get('timing_summary', {}).get('query_family_v2')}` | `{hint}` | "
            f"`{answer_status}` | `{result.get('timing_summary', {}).get('total_ms')}` | {markers} |"
        )

    for result in results:
        lines.extend(
            [
                "",
                f"## {result['id']}",
                "",
                f"Group: `{result['group']}`",
                f"Query: `{result['query']}`",
                f"Trace ID: `{result['trace_id']}`",
                f"Tenant: `{result.get('tenant_id')}`",
                f"Query family: `{result.get('timing_summary', {}).get('query_family_v2')}`",
                f"Latency: `{result.get('timing_summary', {}).get('total_ms')} ms`",
                f"Not found: `{result.get('is_not_found')}`",
                "",
                "Answer:",
                "",
                result.get("answer", "").strip() or "(empty)",
                "",
                "Candidate score ranking / fact decisions:",
                "",
            ]
        )
        candidates = result.get("fact_candidate_lines") or []
        decisions = result.get("fact_decision_lines") or []
        if not candidates and not decisions:
            lines.append("(none captured)")
        for marker in candidates[:20] + decisions[:20]:
            lines.append(f"- `{marker}`")

        lines.extend(["", "Top retrieved/reranked chunks:", ""])
        for entry in result.get("retrieved_chunks", [])[:8]:
            metadata = entry.get("structural_metadata") or {}
            metadata_text = ", ".join(f"{k}={v}" for k, v in metadata.items()) or "(none)"
            lines.extend(
                [
                    f"- rank `{entry.get('rank')}` score `{entry.get('score')}` rerank `{entry.get('rerank_score')}` "
                    f"chunk `{entry.get('chunk_index')}` page `{entry.get('page')}` source `{entry.get('source')}`",
                    f"  - metadata: {metadata_text}",
                    f"  - {entry.get('text', '')[:700]}",
                ]
            )

        lines.extend(["", "Topic/list markers:", ""])
        topic_markers = result.get("topic_marker_lines") or []
        if not topic_markers:
            lines.append("(none captured)")
        else:
            for marker in topic_markers[:80]:
                lines.append(f"- `{marker}`")

        lines.extend(["", "Relevant log markers:", ""])
        markers = result.get("log_markers") or []
        if not markers:
            lines.append("(none captured)")
        else:
            for marker in markers[:120]:
                lines.append(f"- `{marker}`")
    return "\n".join(lines).rstrip() + "\n"


async def run_validation(args: argparse.Namespace) -> int:
    login_host = args.login_host.rstrip("/")
    rag_host = args.rag_host.rstrip("/")
    log_path = Path(args.log_path)
    output_dir = Path(args.output_dir)

    session = _login(login_host, args.username, args.password)
    cookie_header = _session_cookie_header(session)
    kb_status = _get_json(session, f"{rag_host}/kb_status", timeout=60)
    tenant_candidates = [int(x) for x in str(args.tenant_candidates).split(",") if str(x).strip()]
    questions = VALIDATION_QUESTIONS
    tenant_id, tenant_detection = _resolve_tenant_id(
        session,
        rag_host,
        kb_status,
        args.tenant_id,
        tenant_candidates,
        args.top_k,
        questions,
    )

    results: list[dict[str, Any]] = []
    log_cursor = _log_offset(log_path)
    for question in questions:
        trace_id = f"phase14d-{question['id']}-{int(time.time() * 1000)}"
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
        log_text, log_cursor = _read_log_tail(log_path, log_cursor)
        marker_lines = _marker_lines(log_text, question["query"], trace_id)
        result = {
            **question,
            "trace_id": trace_id,
            "tenant_id": tenant_id,
            "tenant_detection": tenant_detection,
            "kb_status": kb_status,
            "retrieval_debug": retrieval,
            "retrieved_chunks": retrieved_chunks,
            "ws_payload": ws.payload,
            "ws_chunks": ws.chunks,
            "ws_messages": ws.messages,
            "ws_error": ws.error,
            "answer": ws.answer,
            "is_not_found": _is_not_found(ws.answer) or bool(ws.error),
            "timing_summary": _timing_summary(ws.payload, ws.latency_ms),
            "evidence_hint": _evidence_hint(question["query"], retrieved_chunks),
            "log_markers": marker_lines,
            "marker_summary": _marker_summary(marker_lines),
            "fact_candidate_lines": _candidate_lines(marker_lines),
            "fact_decision_lines": _decision_lines(marker_lines),
            "topic_marker_lines": _topic_marker_lines(marker_lines),
        }
        evaluation = _evaluate_result(question, ws.answer, retrieved_chunks, marker_lines)
        result["evaluation"] = evaluation
        result["passed"] = evaluation.get("passed") and not ws.error
        results.append(result)

    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "phase14f_final_answer_validation.json"
    md_path = output_dir / "phase14f_final_answer_validation.md"
    json_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(_report_markdown(results), encoding="utf-8")

    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")
    for result in results:
        timing = result.get("timing_summary", {})
        status = "PASS" if result.get("passed") else "FAIL"
        issues = result.get("evaluation", {}).get("issues") or []
        print(
            f"{status} {result['id']} total_ms={timing.get('total_ms')} "
            f"family={timing.get('query_family_v2')} issues={issues}"
        )
    return 0 if all(r.get("passed") for r in results) else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Phase 14F final answer reliability validation.")
    parser.add_argument("--baseline", action="store_true", help="Write results as phase14f_baseline artifacts.")
    parser.add_argument("--offline-only", action="store_true", help="Run deterministic offline checks only.")
    parser.add_argument("--login-host", default=LOGIN_HOST)
    parser.add_argument("--rag-host", default=RAG_HOST)
    parser.add_argument("--ws-url", default=WS_URL)
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", default="admin")
    parser.add_argument("--tenant-id", type=int, default=None)
    parser.add_argument("--tenant-candidates", default="1,2,3,4,5")
    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument("--timeout", type=float, default=240.0)
    parser.add_argument("--output-dir", default="logs")
    parser.add_argument("--log-path", default="logs/rag.log")
    parser.add_argument("--allow-failures", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.offline_only:
        passed_count, offline_results = run_offline_checks()
        print(f"Offline checks passed: {passed_count}/{len(offline_results)}")
        for item in offline_results:
            status = "PASS" if item.get("passed") else "FAIL"
            print(f"{status} {item['id']} entities={item.get('entities')} issues={item.get('issues')}")
        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        suffix = "baseline" if args.baseline else "offline"
        json_path = output_dir / f"phase14f_{suffix}.json"
        json_path.write_text(json.dumps(offline_results, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Wrote {json_path}")
        return 0 if passed_count == len(offline_results) else 1
    return asyncio.run(run_validation(args))


if __name__ == "__main__":
    raise SystemExit(main())
