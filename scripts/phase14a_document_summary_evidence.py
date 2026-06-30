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

from scripts.phase14_rag_validation import (
    LOGIN_HOST,
    RAG_HOST,
    WS_URL,
    get_json,
    login,
    retrieve_debug,
    run_ws_query,
    session_cookie_header,
)


DOCUMENT_SUMMARY_EVIDENCE_QUERIES: list[dict[str, str]] = [
    {"id": "q1_document_about", "query": "What is this document about?"},
    {"id": "q2_document_summary", "query": "Give me a summary of this document."},
    {"id": "q6_chapter_overview", "query": "Provide a chapter-by-chapter overview of this document."},
]


def _compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def render_markdown_report(results: list[dict[str, Any]]) -> str:
    lines: list[str] = ["# Phase 14A Document Summary Evidence", ""]
    for result in results:
        retrieval = result.get("retrieval") if isinstance(result.get("retrieval"), dict) else {}
        rows = retrieval.get("results") if isinstance(retrieval, dict) else []
        rows = rows if isinstance(rows, list) else []
        selected = result.get("selected_context") if isinstance(result.get("selected_context"), list) else []
        lines.extend(
            [
                f"## {result.get('id')}",
                f"Query: `{result.get('query')}`",
                f"Retrieval query: `{retrieval.get('retrieval_query') or result.get('query')}`",
                "",
                "### Top 20 Retrieved Chunks",
            ]
        )
        for row in rows[:20]:
            lines.append(
                "- "
                f"rank={row.get('rank')} "
                f"page={row.get('page')} "
                f"rerank_score={row.get('rerank_score')} "
                f"score={row.get('score')} "
                f"section={row.get('section')!r} "
                f"title={row.get('title')!r} "
                f"role={row.get('chunk_role')!r}"
            )
            preview = str(row.get("text_preview") or "").replace("\n", " ").strip()
            if preview:
                lines.append(f"  Preview: {preview[:500]}")

        lines.extend(["", "### Page Numbers"])
        lines.append(", ".join(str(row.get("page")) for row in rows[:20]) or "(none)")

        lines.extend(["", "### Rerank Scores"])
        for row in rows[:20]:
            lines.append(f"- rank={row.get('rank')} rerank_score={row.get('rerank_score')} similarity={row.get('similarity')}")

        lines.extend(["", "### Chunk Metadata"])
        for row in rows[:20]:
            lines.append(f"- rank={row.get('rank')} metadata=`{_compact_json(row.get('metadata') or {})}`")

        lines.extend(["", "### Heading Metadata"])
        for row in rows[:20]:
            lines.append(f"- rank={row.get('rank')} heading=`{_compact_json(row.get('heading') or {})}`")

        lines.extend(["", "### Selected Context Sent To The LLM"])
        for row in selected:
            preview = str(row.get("preview") or "").replace("\n", " ").strip()
            lines.append(
                "- "
                f"rank={row.get('rank')} "
                f"page={row.get('page')} "
                f"section={row.get('section')!r} "
                f"score={row.get('score')} "
                f"preview={preview[:500]!r}"
            )
        if not selected:
            lines.append("(none)")

        lines.extend(["", "### Final Answer", "", str(result.get("answer") or "").strip() or "(empty)", ""])
    return "\n".join(lines).rstrip() + "\n"


async def collect_evidence(args: argparse.Namespace) -> list[dict[str, Any]]:
    login_host = args.login_host.rstrip("/")
    rag_host = args.rag_host.rstrip("/")
    session = login(login_host, args.username, args.password)
    cookie_header = session_cookie_header(session)
    kb_status = get_json(session, f"{rag_host}/kb_status", timeout=60)
    tenant_id = args.tenant_id if args.tenant_id is not None else kb_status.get("tenant_id")
    tenant_id = int(tenant_id) if tenant_id is not None else None

    results: list[dict[str, Any]] = []
    for question in DOCUMENT_SUMMARY_EVIDENCE_QUERIES:
        trace_id = f"phase14a-{question['id']}-{int(time.time() * 1000)}"
        retrieval = retrieve_debug(session, rag_host, question["query"], args.top_k, tenant_id=tenant_id)
        ws_payload: dict[str, Any] = {}
        answer = ""
        latency_ms = 0
        try:
            ws = await run_ws_query(
                ws_url=args.ws_url,
                cookie_header=cookie_header,
                query=question["query"],
                trace_id=trace_id,
                tenant_id=tenant_id,
                timeout_s=args.timeout,
            )
            ws_payload = ws.payload
            answer = ws.answer
            latency_ms = ws.latency_ms
        except Exception as exc:  # noqa: BLE001 - preserve retrieval rows on WS failures
            ws_payload = {"error": type(exc).__name__, "detail": str(exc)}
            answer = f"[websocket trace failed: {type(exc).__name__}: {exc}]"
        timing = ws_payload.get("timing") if isinstance(ws_payload, dict) else {}
        timing = timing if isinstance(timing, dict) else {}
        results.append(
            {
                **question,
                "trace_id": trace_id,
                "tenant_id": tenant_id,
                "kb_status": kb_status,
                "retrieval": retrieval,
                "selected_context": timing.get("phase14_selected_context") or [],
                "ws_payload": ws_payload,
                "answer": answer,
                "latency_ms": latency_ms,
            }
        )
    return results


async def run(args: argparse.Namespace) -> int:
    results = await collect_evidence(args)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "phase14a_document_summary_evidence.json"
    md_path = output_dir / "phase14a_document_summary_evidence.md"
    json_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(render_markdown_report(results), encoding="utf-8")
    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect Phase 14A document_summary before/after evidence.")
    parser.add_argument("--login-host", default=LOGIN_HOST)
    parser.add_argument("--rag-host", default=RAG_HOST)
    parser.add_argument("--ws-url", default=WS_URL)
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", default="admin")
    parser.add_argument("--tenant-id", type=int, default=None)
    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument("--timeout", type=float, default=240.0)
    parser.add_argument("--output-dir", default="logs")
    return parser


def main() -> int:
    return asyncio.run(run(build_parser().parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
