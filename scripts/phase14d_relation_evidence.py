from __future__ import annotations

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

RELATION_QUERIES: list[dict[str, str]] = [
    {"id": "relation_found_behaviorism", "group": "relation", "query": "Who founded behaviorism?"},
    {"id": "relation_found_functionalism", "group": "relation", "query": "Who founded functionalism?"},
    {"id": "relation_found_gestalt", "group": "relation", "query": "Who founded Gestalt psychology?"},
    {"id": "relation_found_structuralism", "group": "relation", "query": "Who founded structuralism?"},
    {"id": "relation_created_psychoanalysis", "group": "relation", "query": "Who created psychoanalysis?"},
    {"id": "relation_developed_analytical", "group": "relation", "query": "Who developed analytical psychology?"},
    {"id": "relation_proposed_classical", "group": "relation", "query": "Who proposed classical conditioning?"},
]

TOPIC_QUERIES: list[dict[str, str]] = [
    {"id": "topic_major_topics", "group": "topic", "query": "List major topics in this document"},
    {"id": "topic_subjects", "group": "topic", "query": "What subjects are covered?"},
    {"id": "topic_chapters", "group": "topic", "query": "What chapters are covered?"},
    {"id": "topic_main_concepts", "group": "topic", "query": "What are the main concepts?"},
    {"id": "topic_major_themes", "group": "topic", "query": "What are the major themes?"},
]

VALIDATION_QUESTIONS = RELATION_QUERIES + TOPIC_QUERIES

MARKER_PATTERNS = (
    "[QUERY FAMILY]",
    "[ANSWER ROUTE]",
    "[FACT TOPK]",
    "[FACT RETRY]",
    "[FACT RESCUE QUERY]",
    "[FACT RELATION FILTER]",
    "[FACT MULTI-CHUNK]",
    "[FACT ANCHOR SCORE]",
    "[FACT CHUNK SELECTION]",
    "[FACT EXTRACTION]",
    "[FACT OCR CLEANUP]",
    "[FACT PERSON VALIDATOR]",
    "[FACT CANDIDATE]",
    "[FACT DECISION]",
    "[FACT ACCEPTED]",
    "[FACT ANSWER GUARD]",
    "[FACT FALLBACK]",
    "[FACT MULTI-CHUNK FALLBACK]",
    "[OCR FILTER]",
    "[FINAL CANDIDATE REJECTED]",
    "[FINAL ANSWER SOURCE]",
    "[FINAL DECISION DEBUG]",
    "[ANSWER BLOCKED]",
    "[LIST MODE ACTIVE]",
    "[LIST EXTRACTION MODE]",
    "[LIST DEBUG]",
    "[SECTION DEBUG]",
    "[SECTION COHERENCE DEBUG]",
    "[SECTION SELECT]",
    "[LIST WINNER]",
    "[LIST ROUTE]",
    "[LIST REJECTED]",
    "[LIST FALLBACK]",
    "[LIST FINAL DECISION]",
    "[LIST FINAL ITEMS]",
    "[LIST QUALITY]",
    "[LIST CANDIDATE REJECTED]",
    "[LIST TOKEN MISMATCH]",
    "[LIST GROUNDING]",
    "[LIST SOURCE DEBUG]",
    "[LIST MERGE GUARD]",
    "[LIST COHERENCE DEBUG]",
    "[LIST CLEAN",
    "[FAST LIST GUARD]",
    "[STRUCTURE QUERY DETECTED]",
    "[STRUCTURE QUERY RESCUE]",
    "[STRUCTURE ANSWER FINAL]",
    "[LEXICAL RESCUE]",
    "[SYMBOLIC LIST QUERY DETECTED]",
    "[COUNTED LIST QUERY DETECTED]",
    "RAG_NO_MATCH",
    "not_found",
    "fact_",
    "list_",
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


def _report_markdown(results: list[dict[str, Any]]) -> str:
    lines = [
        "# Phase 14D-A Relation/Topic Evidence",
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
        results.append(result)

    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "phase14d_relation_evidence.json"
    md_path = output_dir / "phase14d_relation_evidence.md"
    json_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(_report_markdown(results), encoding="utf-8")

    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")
    for result in results:
        timing = result.get("timing_summary", {})
        status = "FAIL" if result.get("is_not_found") else "PASS"
        print(
            f"{status} {result['id']} total_ms={timing.get('total_ms')} "
            f"family={timing.get('query_family_v2')} markers={len(result.get('log_markers') or [])}"
        )
    return 0 if args.allow_failures or not any(r.get("is_not_found") for r in results) else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Phase 14D-A relation/topic evidence audit.")
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
    return asyncio.run(run_validation(build_parser().parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
