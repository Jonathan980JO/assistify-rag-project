#!/usr/bin/env python3
"""READ-ONLY full-pipeline evidence trace (no fixes, no behavior changes).

For each query this prints RAW evidence only:
  - resolved tenant + collection + chunk count
  - route selected (definition/fact/list/generation) + family + fact_type
  - retrieved chunks: chunk IDs, distance / similarity / reranker scores
  - exact chunk text as stored in Chroma (full, untruncated)
  - candidate answers produced by each deterministic extractor
  - raw "Assistify" decision log trace (candidate generation + rejection reasons)
  - the final deterministic answer returned by _shared_rag_final_answer_decision
  - response_validator.validate_response() result on that final answer

CPU-only so it does not contend with a live server GPU.

Usage:
    python scripts/rca_evidence_full.py            # auto-detect Meridian tenant
    python scripts/rca_evidence_full.py --tenant-id 4
"""
from __future__ import annotations

import os

os.environ.setdefault("RAG_USE_GPU", "0")
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")

import argparse
import logging
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import backend.assistify_rag_server as srv
from backend.response_validator import validate_response

QUERIES = [
    "What is Meridian Financial Services?",
    "What is Meridian Invest?",
    "What is Everyday Checking?",
    "What is the FDIC coverage limit?",
    "How do I open an account?",
]

PROBE_TENANTS = [4, 1, 2, 3, 5, 6, 7, 8]
PROBE_TERMS = ("meridian", "everyday checking", "fdic")


class RawTrace(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.records.append(record.getMessage())
        except Exception:
            pass


def _full(text: str) -> str:
    return re.sub(r"[ \t]+", " ", str(text or "").replace("\r", "")).strip()


def _score_str(d: dict) -> str:
    dist = (d or {}).get("distance")
    rer = (d or {}).get("reranker_score")
    sim = (d or {}).get("similarity")
    if sim is None:
        sim = (d or {}).get("score")
    return f"distance={dist} similarity={sim} reranker={rer}"


def _src(d: dict) -> str:
    md = dict((d or {}).get("metadata") or {})
    return str(md.get("source") or md.get("filename") or md.get("source_name") or "<no-source>")


def detect_tenant(explicit: int | None) -> tuple[int, object]:
    from backend.knowledge_base import resolve_tenant_active_collection

    if explicit is not None:
        return explicit, resolve_tenant_active_collection(explicit)

    best = None
    for tid in PROBE_TENANTS:
        try:
            col = resolve_tenant_active_collection(tid)
        except Exception:
            continue
        if not col:
            continue
        try:
            n = col.count()
        except Exception:
            n = 0
        if n == 0:
            continue
        try:
            sample = col.get(include=["documents"]) or {}
            blob = " ".join(str(x) for x in (sample.get("documents") or [])).lower()
        except Exception:
            blob = ""
        hits = sum(1 for t in PROBE_TERMS if t in blob)
        print(f"  probe tenant={tid} collection={getattr(col,'name','?')} count={n} term_hits={hits}")
        if hits and best is None:
            best = (tid, col, hits)
        elif hits and best and hits > best[2]:
            best = (tid, col, hits)
    if best:
        return best[0], best[1]
    return 1, resolve_tenant_active_collection(1)


def dump_collection_meridian(col) -> None:
    """Show how the source PDF chunks are physically stored (chunk quality)."""
    try:
        data = col.get(include=["documents", "metadatas"]) or {}
    except Exception as exc:
        print(f"  collection.get failed: {exc}")
        return
    ids = list(data.get("ids") or [])
    docs = list(data.get("documents") or [])
    print(f"  collection={getattr(col,'name','?')} total_chunks={len(ids)}")


def trace_query(query: str, rag, col) -> None:
    print("=" * 120)
    print(f"QUERY: {query}")
    print("=" * 120)

    family = srv._classify_query_family_v2(query)
    route = srv._resolve_grounded_answer_route(query)
    fact_type = srv._detect_fact_query_type(query)
    try:
        numeric = srv._is_numeric_fact_lookup_query(query)
    except Exception as exc:
        numeric = f"<err {exc}>"
    print(f"route_selected        = {route}")
    print(f"query_family_v2       = {family}")
    print(f"fact_query_type       = {fact_type}")
    print(f"is_numeric_fact_query = {numeric}")

    docs = list(rag.search(query, top_k=10, return_dicts=True, enable_rerank=True) or [])
    print(f"\nRETRIEVED CHUNKS ({len(docs)}), reranked order:")
    for i, d in enumerate(docs):
        cid = (d or {}).get("id")
        md = dict((d or {}).get("metadata") or {})
        marker = "  <-- TOP5" if i < 5 else ""
        print(f"\n  [{i}] chunk_id={cid!r}{marker}")
        print(f"      {_score_str(d)}")
        print(f"      source={_src(d)} chunk_index={md.get('chunk_index')} page={md.get('page')}")
        text = (d or {}).get("page_content") or (d or {}).get("text") or ""
        print(f"      EXACT_STORED_TEXT: {_full(text)}")

    print("\nCANDIDATE ANSWERS (deterministic extractors):")
    for label, fn in (
        ("definition_route", srv._extract_definition_route_answer),
        ("fact_route", srv._extract_fact_route_answer),
        ("table_fact", srv._extract_table_fact_answer),
    ):
        try:
            cand = fn(query, docs)
        except Exception as exc:
            cand = f"<error: {exc}>"
        print(f"  {label:16} = {cand!r}")

    trace = RawTrace()
    alog = logging.getLogger("Assistify")
    prev = alog.level
    alog.setLevel(logging.DEBUG)
    alog.addHandler(trace)
    try:
        decision = srv._shared_rag_final_answer_decision(query, docs, llm_text=None)
    finally:
        alog.removeHandler(trace)
        alog.setLevel(prev)

    print("\nDECISION TRACE (raw Assistify logs during decision):")
    for line in trace.records:
        print(f"  | {_full(line)}")

    final_answer = decision.get("answer")
    print("\nDECISION RESULT:")
    print(f"  answer_type = {decision.get('answer_type')}")
    print(f"  source_mode = {decision.get('source_mode')}")
    print(f"  used_llm    = {decision.get('used_llm')}")
    print(f"  FINAL_ANSWER = {final_answer!r}")

    vr = validate_response(str(final_answer or ""), query, docs)
    print("\nVALIDATION (response_validator.validate_response):")
    print(f"  is_valid = {vr.is_valid}  severity = {vr.severity}")
    for issue in (vr.issues or []):
        print(f"  issue: {issue.get('severity')}: {issue.get('message')}")
    if vr.modified_response:
        print(f"  modified_response = {vr.modified_response!r}")
    print()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant-id", type=int, default=None)
    args = parser.parse_args()

    print("Detecting tenant / collection holding Meridian KB ...")
    tid, col = detect_tenant(args.tenant_id)
    print(f"\nUSING tenant_id={tid}")
    if col is not None:
        dump_collection_meridian(col)
    rag = srv.get_tenant_rag(tid)
    print()

    for q in QUERIES:
        trace_query(q, rag, col)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
