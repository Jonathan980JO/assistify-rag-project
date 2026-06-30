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

VALIDATION_QUESTIONS: list[dict[str, str]] = [
    {"id": "q1_who_jung", "query": "Who is Jung?"},
    {"id": "q2_document_jung", "query": "What does the document say about Jung?"},
    {"id": "q3_define_behaviorism", "query": "Define behaviorism."},
    {"id": "q4_define_structuralism", "query": "Define structuralism."},
    {"id": "q5_define_functionalism", "query": "Define functionalism."},
    {"id": "q6_long_term_memory", "query": "What is long-term memory?"},
    {"id": "q7_psychology", "query": "What is psychology?"},
    {"id": "q8_classical_conditioning", "query": "What is classical conditioning?"},
    {"id": "q9_operant_conditioning", "query": "What is operant conditioning?"},
    {"id": "q10_gestalt_psychology", "query": "What is Gestalt psychology?"},
]

MARKER_PATTERNS = (
    "[CONCEPT FILTER]",
    "[ENTITY DEF FILTER]",
    "[ENTITY DEF FILTER CHUNKS]",
    "[ENTITY DEF REJECT]",
    "[DEF REJECT WEAK]",
    "[STRICT DEF PREF",
    "[CONTAMINATION GUARD]",
    "[OCR FILTER]",
    "[FACT DECISION]",
    "[FACT ACCEPTED]",
    "[DEF FILTER]",
    "[DEF FILTER EMPTY]",
    "[DEF POOL",
    "[ACCEPT FINAL]",
    "[FINAL CONCEPT CHECK]",
    "[DEF QUALITY REJECT]",
    "definition_candidate_rejected",
    "definition_not_found",
    "fact_",
    "RAG_NO_MATCH",
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
    lines = []
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


def _compact_entry(entry: dict[str, Any], idx: int) -> dict[str, Any]:
    text = _text_from_entry(entry)
    metadata = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
    return {
        "rank": idx + 1,
        "score": entry.get("score"),
        "rerank_score": entry.get("rerank_score") or entry.get("cross_encoder_score"),
        "chunk_index": metadata.get("chunk_index") or entry.get("chunk_index"),
        "source": metadata.get("source") or metadata.get("file_name") or entry.get("source"),
        "section": metadata.get("section") or metadata.get("chapter") or metadata.get("title"),
        "text": re.sub(r"\s+", " ", text).strip(),
    }


def _query_terms(query: str) -> list[str]:
    stop = {
        "what",
        "does",
        "the",
        "document",
        "say",
        "about",
        "define",
        "who",
        "is",
        "was",
        "are",
        "a",
        "an",
        "of",
    }
    return [tok for tok in re.findall(r"[a-z0-9]+", query.lower()) if len(tok) > 2 and tok not in stop]


def _evidence_hint(query: str, entries: list[dict[str, Any]]) -> dict[str, Any]:
    terms = _query_terms(query)
    if not terms:
        return {"answer_present_in_retrieval": "unknown", "matched_ranks": []}
    matched = []
    for entry in entries:
        text = str(entry.get("text") or "").lower()
        hits = [term for term in terms if term in text]
        if hits:
            matched.append({"rank": entry.get("rank"), "terms": hits, "preview": entry.get("text", "")[:240]})
    return {
        "answer_present_in_retrieval": "needs_review" if matched else "no_term_hit",
        "matched_ranks": matched[:5],
    }


def _tenant_evidence_score(session: requests.Session, rag_host: str, tenant_id: int, top_k: int) -> tuple[int, dict[str, Any]]:
    probe_queries = ("What is psychology?", "Who is Jung?", "Define behaviorism.")
    score = 0
    probe_payload: dict[str, Any] = {}
    for query in probe_queries:
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
        hint = _evidence_hint(query, entries)
        score += sum(len(match.get("terms") or []) for match in hint.get("matched_ranks") or [])
        source_blob = " ".join(str(entry.get("source") or "") for entry in entries).lower()
        text_blob = " ".join(str(entry.get("text") or "")[:500] for entry in entries).lower()
        if "psychology" in source_blob or "psychology" in text_blob:
            score += 5
        if "jung" in text_blob:
            score += 5
        if "behaviorism" in text_blob:
            score += 5
        probe_payload[query] = {
            "count": len(entries),
            "score": score,
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
) -> tuple[int | None, dict[str, Any]]:
    if requested_tenant_id is not None:
        return int(requested_tenant_id), {"mode": "explicit", "tenant_id": int(requested_tenant_id)}

    candidate_ids = []
    status_tenant = kb_status.get("tenant_id")
    if status_tenant is not None:
        candidate_ids.append(int(status_tenant))
    for tenant_id in tenant_candidates:
        if int(tenant_id) not in candidate_ids:
            candidate_ids.append(int(tenant_id))

    scored: list[dict[str, Any]] = []
    for tenant_id in candidate_ids:
        score, probe = _tenant_evidence_score(session, rag_host, tenant_id, top_k)
        scored.append({"tenant_id": tenant_id, "score": score, "probe": probe})

    chosen = max(scored, key=lambda item: int(item.get("score") or 0), default=None)
    if chosen and int(chosen.get("score") or 0) > 0:
        return int(chosen["tenant_id"]), {"mode": "auto_probe", "chosen": chosen, "candidates": scored}
    return (int(status_tenant) if status_tenant is not None else None), {
        "mode": "kb_status_fallback",
        "tenant_id": status_tenant,
        "candidates": scored,
    }


def _timing_summary(payload: dict[str, Any], latency_ms: int) -> dict[str, Any]:
    timing = payload.get("timing") if isinstance(payload, dict) else {}
    timing = timing if isinstance(timing, dict) else {}
    return {
        "retrieval_ms": timing.get("retrieval_ms"),
        "rerank_ms": timing.get("rerank_ms"),
        "definition_pipeline_ms": timing.get("definition_pipeline_ms") or timing.get("answer_generation_ms"),
        "answer_generation_ms": timing.get("answer_generation_ms"),
        "total_ms": timing.get("total_ms") or latency_ms,
        "phase14_retrieved_count": timing.get("phase14_retrieved_count"),
        "query_family_v2": timing.get("query_family_v2") or timing.get("phase14_query_family_v2"),
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


def _report_markdown(results: list[dict[str, Any]]) -> str:
    lines = [
        "# Phase 14C Definition/Fact Evidence",
        "",
        "## Evidence Matrix",
        "",
        "| Query | Retrieval Evidence Hint | Answer Returned To User | Result | Total ms | Rejecting Markers |",
        "| --- | --- | --- | --- | ---: | --- |",
    ]
    for result in results:
        hint = result.get("evidence_hint", {}).get("answer_present_in_retrieval", "unknown")
        answer = "YES" if result.get("answer") and not result.get("is_not_found") else "NO"
        outcome = "needs_review"
        if result.get("is_not_found") and hint == "needs_review":
            outcome = "pipeline_failure_candidate"
        elif answer == "YES":
            outcome = "answered"
        markers = "; ".join(result.get("marker_summary") or []) or "(none captured)"
        lines.append(
            f"| `{result['query']}` | `{hint}` | `{answer}` | `{outcome}` | "
            f"`{result.get('timing_summary', {}).get('total_ms')}` | {markers} |"
        )

    for result in results:
        lines.extend(
            [
                "",
                f"## {result['id']}",
                "",
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
                "Top retrieved/reranked chunks:",
                "",
            ]
        )
        for entry in result.get("retrieved_chunks", [])[:8]:
            lines.extend(
                [
                    f"- rank `{entry.get('rank')}` score `{entry.get('score')}` rerank `{entry.get('rerank_score')}` "
                    f"chunk `{entry.get('chunk_index')}` source `{entry.get('source')}`",
                    f"  - {entry.get('text', '')[:500]}",
                ]
            )
        lines.extend(["", "Relevant log markers:", ""])
        markers = result.get("log_markers") or []
        if not markers:
            lines.append("(none captured)")
        else:
            for marker in markers[:80]:
                lines.append(f"- `{marker}`")
    return "\n".join(lines).rstrip() + "\n"


def _marker_summary(lines: list[str]) -> list[str]:
    counts: dict[str, int] = {}
    for line in lines:
        for marker in MARKER_PATTERNS:
            if marker.lower() in line.lower():
                counts[marker] = counts.get(marker, 0) + 1
                break
    return [f"`{marker}` x{count}" for marker, count in sorted(counts.items())]


async def run_validation(args: argparse.Namespace) -> int:
    login_host = args.login_host.rstrip("/")
    rag_host = args.rag_host.rstrip("/")
    log_path = Path(args.log_path)
    output_dir = Path(args.output_dir)

    session = _login(login_host, args.username, args.password)
    cookie_header = _session_cookie_header(session)
    kb_status = _get_json(session, f"{rag_host}/kb_status", timeout=60)
    tenant_candidates = [int(x) for x in str(args.tenant_candidates).split(",") if str(x).strip()]
    tenant_id, tenant_detection = _resolve_tenant_id(
        session,
        rag_host,
        kb_status,
        args.tenant_id,
        tenant_candidates,
        args.top_k,
    )

    results: list[dict[str, Any]] = []
    log_cursor = _log_offset(log_path)
    for question in VALIDATION_QUESTIONS:
        trace_id = f"phase14c-{question['id']}-{int(time.time() * 1000)}"
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
        }
        results.append(result)

    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "phase14c_definition_evidence.json"
    md_path = output_dir / "phase14c_definition_evidence.md"
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
    parser = argparse.ArgumentParser(description="Run Phase 14C definition/fact evidence trace.")
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
