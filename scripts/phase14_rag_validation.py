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
    {
        "id": "q1_document_about",
        "query": "What is this document about?",
        "expected": "High-level document overview derived from retrieved evidence.",
    },
    {
        "id": "q2_document_summary",
        "query": "Give me a summary of this document.",
        "expected": "Multi-paragraph summary grounded in retrieved chunks.",
    },
    {
        "id": "q3_major_schools",
        "query": "What are the major schools of psychology discussed in this document?",
        "expected": "Complete answer with no truncation or timeout.",
    },
    {
        "id": "q4_long_term_memory",
        "query": "Explain long-term memory according to the document.",
        "expected": "Evidence-grounded explanation, not a generic model answer.",
    },
    {
        "id": "q5_freud",
        "query": "What does the document say about Freud?",
        "expected": "Evidence-grounded answer referencing retrieved material.",
    },
    {
        "id": "q6_chapter_overview",
        "query": "Provide a chapter-by-chapter overview of this document.",
        "expected": "Representative chapter/topic breakdown from retrieved evidence.",
    },
]

_NOT_FOUND_PATTERNS = (
    "not found in the document",
    "couldn't find",
    "could not find",
    "no relevant information",
    "not enough information",
    "not in the uploaded materials",
    "not in the uploaded help materials",
)


def is_partial_fragment(answer: str) -> bool:
    text = re.sub(r"\s+", " ", str(answer or "").strip())
    if not text:
        return True
    if text.lower() == "not found in the document.":
        return False
    if len(text.split()) <= 3 and not re.search(r"[.!?]$", text):
        return True
    if text.lower() in {"the major", "the major schools", "the major schools are"}:
        return True
    return False


def answer_has_not_found(answer: str) -> bool:
    lower = str(answer or "").lower()
    return any(pattern in lower for pattern in _NOT_FOUND_PATTERNS)


def session_cookie_header(session: requests.Session) -> str:
    return "; ".join(f"{c.name}={c.value}" for c in session.cookies)


def websocket_header_kwargs(cookie_header: str) -> dict[str, Any]:
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


def login(login_host: str, username: str, password: str) -> requests.Session:
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


def get_json(session: requests.Session, url: str, *, timeout: int = 30) -> dict[str, Any]:
    response = session.get(url, timeout=timeout)
    response.raise_for_status()
    payload = response.json()
    return payload if isinstance(payload, dict) else {"value": payload}


def retrieve_debug(session: requests.Session, rag_host: str, query: str, top_k: int, tenant_id: int | None = None) -> dict[str, Any]:
    params: dict[str, Any] = {"query": query, "top_k": top_k}
    if tenant_id is not None:
        params["tenant_id"] = int(tenant_id)
    response = session.get(
        f"{rag_host}/rag/retrieve-debug",
        params=params,
        timeout=120,
    )
    response.raise_for_status()
    payload = response.json()
    return payload if isinstance(payload, dict) else {"value": payload}


@dataclass
class WsResult:
    answer: str
    payload: dict[str, Any]
    chunks: list[str]
    messages: list[dict[str, Any]]
    latency_ms: int


async def run_ws_query(
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

    connect_kwargs = websocket_header_kwargs(cookie_header)

    async with websockets.connect(ws_url, **connect_kwargs) as websocket:
        payload: dict[str, Any] = {
            "text": query,
            "language": "en",
            "tts_enabled": False,
            "phase14_trace": True,
            "client_trace_id": trace_id,
        }
        if tenant_id is not None:
            payload["tenant_id"] = tenant_id
        await websocket.send(json.dumps(payload))
        while True:
            raw = await asyncio.wait_for(websocket.recv(), timeout=timeout_s)
            if isinstance(raw, bytes):
                continue
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                message = {"type": "raw", "text": raw}
            if isinstance(message, dict):
                messages.append(message)
                if message.get("type") == "aiResponseChunk":
                    chunks.append(str(message.get("text") or ""))
                if message.get("type") == "aiResponseDone":
                    done_payload = message
                    break
                if message.get("type") == "error" or message.get("error"):
                    done_payload = message
                    break

    elapsed = int(round((time.perf_counter() - started) * 1000))
    answer = str(done_payload.get("fullText") or "".join(chunks))
    return WsResult(answer=answer, payload=done_payload, chunks=chunks, messages=messages, latency_ms=elapsed)


def evaluate_result(answer: str, retrieval: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    entries = retrieval.get("results") or retrieval.get("entries") or []
    timing = payload.get("timing") if isinstance(payload, dict) else {}
    trace = timing if isinstance(timing, dict) else {}
    trace_retrieved_count = trace.get("phase14_retrieved_count")
    if isinstance(trace_retrieved_count, int):
        retrieved_count = trace_retrieved_count
    else:
        retrieved_count = len(entries) if isinstance(entries, list) else 0
    answer_lower = str(answer or "").lower()
    is_timeout = bool(
        "request timed out" in answer_lower
        or "timed out" in answer_lower
        or "timeout" in answer_lower
    )
    return {
        "has_retrieval": retrieved_count > 0,
        "retrieved_count": retrieved_count,
        "has_selected_context": bool(trace.get("phase14_selected_context")),
        "is_partial_fragment": is_partial_fragment(answer),
        "is_not_found": answer_has_not_found(answer),
        "is_timeout": is_timeout,
        "websocket_error": bool(payload.get("error") or payload.get("type") == "error" or is_timeout),
    }


def report_markdown(results: list[dict[str, Any]]) -> str:
    lines = ["# Phase 14 Live Validation Trace", ""]
    for result in results:
        evaluation = result["evaluation"]
        lines.extend(
            [
                f"## {result['id']}",
                f"Query: `{result['query']}`",
                f"Latency: `{result['latency_ms']} ms`",
                f"Query family: `{result.get('query_family') or 'unknown'}`",
                f"Retrieved chunks: `{evaluation['retrieved_count']}`",
                f"Partial fragment: `{evaluation['is_partial_fragment']}`",
                f"Not found: `{evaluation['is_not_found']}`",
                "",
                "Answer:",
                "",
                result["answer"].strip() or "(empty)",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


async def run_validation(args: argparse.Namespace) -> int:
    login_host = args.login_host.rstrip("/")
    rag_host = args.rag_host.rstrip("/")
    session = login(login_host, args.username, args.password)
    cookie_header = session_cookie_header(session)
    kb_status = get_json(session, f"{rag_host}/kb_status", timeout=60)
    tenant_id = args.tenant_id if args.tenant_id is not None else kb_status.get("tenant_id")
    tenant_id = int(tenant_id) if tenant_id is not None else None

    results: list[dict[str, Any]] = []
    for question in VALIDATION_QUESTIONS:
        trace_id = f"phase14-{question['id']}-{int(time.time() * 1000)}"
        retrieval = retrieve_debug(session, rag_host, question["query"], args.top_k, tenant_id=tenant_id)
        ws = await run_ws_query(
            ws_url=args.ws_url,
            cookie_header=cookie_header,
            query=question["query"],
            trace_id=trace_id,
            tenant_id=tenant_id,
            timeout_s=args.timeout,
        )
        timing = ws.payload.get("timing") if isinstance(ws.payload, dict) else {}
        query_family = None
        if isinstance(timing, dict):
            query_family = timing.get("query_family_v2") or timing.get("phase14_query_family_v2")
        evaluation = evaluate_result(ws.answer, retrieval, ws.payload)
        results.append(
            {
                **question,
                "trace_id": trace_id,
                "tenant_id": tenant_id,
                "kb_status": kb_status,
                "retrieval_debug": retrieval,
                "ws_payload": ws.payload,
                "ws_chunks": ws.chunks,
                "answer": ws.answer,
                "latency_ms": ws.latency_ms,
                "query_family": query_family,
                "evaluation": evaluation,
            }
        )

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "phase14_validation_trace.json"
    md_path = output_dir / "phase14_validation_trace.md"
    json_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(report_markdown(results), encoding="utf-8")

    failures = [
        result
        for result in results
        if result["evaluation"]["websocket_error"]
        or result["evaluation"].get("is_timeout")
        or result["evaluation"]["is_partial_fragment"]
        or result["evaluation"]["is_not_found"]
        or not result["evaluation"]["has_retrieval"]
        or not result["evaluation"]["has_selected_context"]
    ]
    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")
    for result in results:
        status = "FAIL" if result in failures else "PASS"
        print(f"{status} {result['id']} latency_ms={result['latency_ms']} family={result.get('query_family')}")
    return 0 if args.allow_failures or not failures else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Phase 14 live RAG validation with trace evidence.")
    parser.add_argument("--login-host", default=LOGIN_HOST)
    parser.add_argument("--rag-host", default=RAG_HOST)
    parser.add_argument("--ws-url", default=WS_URL)
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", default="admin")
    parser.add_argument("--tenant-id", type=int, default=None)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--timeout", type=float, default=240.0)
    parser.add_argument("--output-dir", default="logs")
    parser.add_argument("--allow-failures", action="store_true")
    return parser


def main() -> int:
    return asyncio.run(run_validation(build_parser().parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
