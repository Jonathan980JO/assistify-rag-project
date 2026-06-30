from __future__ import annotations

"""Phase 14D-X   Fact Answer Forensic harness (read-only, no fixes).

This harness collects evidence ONLY. It does not modify any production code,
retrieval, reranking, embeddings, Chroma, ingestion, Ollama, streaming,
validators, or the deterministic extractor.

It re-drives the REAL deterministic fact layer in
``backend/retrieval/routing.py`` (``_extract_fact_from_context`` and its
helpers ``_detect_fact_query_type`` / ``_extract_relation_subject_terms``)
against the EXACT retrieved-chunk texts already captured for the five forensic
queries in ``logs/phase14d_relation_evidence.json``.

A lightweight stub logger is bound via ``routing.bind_server`` purely so the
extractor's ``S.logger.info(...)`` marker calls are captured in-memory. The
extractor's behavior is unchanged; we only observe its emitted markers,
candidate list, scores, validation decisions, and final FACT_DECISION.

Output: logs/phase14d_fact_forensics.json
"""

import json
import re
from pathlib import Path
from typing import Any

import backend.assistify_rag_server as server  # auto-binds routing to the real server (read-only)
import backend.retrieval.routing as routing


# --- forensic queries (exact strings from the task) -----------------------
FORENSIC_QUERIES = [
    "Who founded Gestalt psychology?",
    "Who founded behaviorism?",
    "Who founded structuralism?",
    "Who created psychoanalysis?",
    "Who developed analytical psychology?",
]


class _CaptureLogger:
    """Minimal logger that records every formatted record routing emits."""

    def __init__(self) -> None:
        self.records: list[str] = []

    def _emit(self, msg: str, args: tuple[Any, ...]) -> None:
        try:
            self.records.append(str(msg) % args if args else str(msg))
        except Exception:
            self.records.append(str(msg) + " " + repr(args))

    def info(self, msg: str, *args: Any) -> None:
        self._emit(msg, args)

    # routing may call these too; capture them harmlessly.
    def debug(self, msg: str, *args: Any) -> None:
        self._emit(msg, args)

    def warning(self, msg: str, *args: Any) -> None:
        self._emit(msg, args)

    def error(self, msg: str, *args: Any) -> None:
        self._emit(msg, args)


class _StubServer:
    """(unused) retained for reference; the real server module is used instead."""

    def __init__(self) -> None:
        self.logger = _CaptureLogger()


def _load_evidence() -> dict[str, dict[str, Any]]:
    path = Path("logs/phase14d_relation_evidence.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    results = data if isinstance(data, list) else data.get("results", [])
    by_query: dict[str, dict[str, Any]] = {}
    for r in results:
        by_query[str(r.get("query") or "").strip()] = r
    return by_query


def _markers(records: list[str], needle: str) -> list[str]:
    return [r for r in records if needle in r]


def _trace_one(query: str, evidence: dict[str, Any]) -> dict[str, Any]:
    chunks_meta = evidence.get("retrieved_chunks") or []
    # chunk texts in rerank order (rank 1 first), exactly as captured.
    ordered = sorted(chunks_meta, key=lambda c: int(c.get("rank") or 0))
    chunk_texts = [str(c.get("text") or "") for c in ordered]

    # Temporarily attach a capturing logger to the REAL server module so the
    # extractor's S.logger.info(...) markers are recorded. Behavior unchanged.
    cap = _CaptureLogger()
    real_logger = getattr(server, "logger", None)
    server.logger = cap
    try:
        fact_type = routing._detect_fact_query_type(query)
        subject_terms = routing._extract_relation_subject_terms(query, fact_type)
        final = routing._extract_fact_from_context(query, chunk_texts)
    finally:
        if real_logger is not None:
            server.logger = real_logger
    records = cap.records

    return {
        "query": query,
        "id": evidence.get("id"),
        "fact_type_detected": fact_type,
        "subject_terms": subject_terms,
        "observed_runtime_answer": evidence.get("answer"),
        "observed_is_not_found": evidence.get("is_not_found"),
        "redriven_fact_decision": final,
        "retrieved_chunks": [
            {
                "rank": c.get("rank"),
                "score": c.get("score"),
                "rerank_score": c.get("rerank_score"),
                "chunk_index": c.get("chunk_index"),
                "page": c.get("page"),
                "source": c.get("source"),
                "metadata": c.get("metadata"),
                "text": str(c.get("text") or ""),
            }
            for c in ordered
        ],
        "markers": {
            "fact_extraction": _markers(records, "[FACT EXTRACTION]"),
            "fact_candidate": _markers(records, "[FACT CANDIDATE]"),
            "fact_person_validator": _markers(records, "[FACT PERSON VALIDATOR]"),
            "fact_decision": _markers(records, "[FACT DECISION]"),
            "fact_accepted": _markers(records, "[FACT ACCEPTED]"),
            "fact_ocr_cleanup": _markers(records, "[FACT OCR CLEANUP]"),
        },
        "all_records": records,
    }


def main() -> int:
    by_query = _load_evidence()
    traces: list[dict[str, Any]] = []
    for q in FORENSIC_QUERIES:
        ev = by_query.get(q)
        if ev is None:
            traces.append({"query": q, "error": "no captured evidence for this query"})
            continue
        traces.append(_trace_one(q, ev))

    out = {
        "harness": "phase14dx_fact_forensics",
        "note": "Read-only re-drive of real deterministic fact extractor over captured retrieved chunks. No production code modified.",
        "source_evidence": "logs/phase14d_relation_evidence.json",
        "queries": traces,
    }
    out_path = Path("logs/phase14d_fact_forensics.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {out_path}")

    # console summary
    for t in traces:
        if t.get("error"):
            print(f"  {t['query']!r}: ERROR {t['error']}")
            continue
        cand_lines = t["markers"]["fact_candidate"]
        print(f"\n=== {t['query']!r} (type={t['fact_type_detected']}, subj={t['subject_terms']}) ===")
        print(f"  runtime answer : {t['observed_runtime_answer']!r}")
        print(f"  re-driven decision: {t['redriven_fact_decision']!r}")
        for ln in cand_lines:
            print("   ", ln)
        for ln in t["markers"]["fact_decision"]:
            print("   ", ln)
        for ln in t["markers"]["fact_person_validator"]:
            print("   ", ln)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
