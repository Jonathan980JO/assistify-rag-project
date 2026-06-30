#!/usr/bin/env python3
"""RCA Sprint #2 — runtime evidence harness (READ-ONLY, no fixes).

Runs the 17 regression queries through the REAL retrieval + decision pipeline
on the live Chroma collection and captures, per query:
  route, retrieved chunks (+source+scores), reranked order, validator log trace,
  rejection code, final answer, source document.

Also:
  --ocr   : PHASE 1 PDF extraction-vs-stored comparison for corruption origin.
  --leak  : PHASE 4 active-sources leakage demonstration.

CPU-only (RAG_USE_GPU=0) so it never contends with the live server's GPU.
"""
from __future__ import annotations

import os

os.environ.setdefault("RAG_USE_GPU", "0")
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")

import logging
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import backend.assistify_rag_server as srv

DEFINITION_QUERIES = [
    "What is Meridian Financial Services?",
    "What is Meridian Invest?",
    "What is Everyday Checking?",
    "What is High-Yield Savings?",
]
FACT_QUERIES = [
    "What is the FDIC coverage limit?",
    "What is the ACH transfer limit?",
    "What is the outgoing wire fee?",
    "What is the minimum balance requirement for Everyday Checking?",
    "What is the minimum balance requirement for Money Market?",
    "What is the minimum balance requirement for High-Yield Savings?",
]
PROCEDURAL_QUERIES = [
    "How do I open an account?",
    "How do I dispute a transaction?",
    "How do I replace my card?",
    "What happens if I report fraud?",
    "I lost my card. What should I do?",
    "My account was hacked. What should I do?",
    "I need money urgently. Which transfer method is fastest?",
]
ALL_QUERIES = DEFINITION_QUERIES + FACT_QUERIES + PROCEDURAL_QUERIES

VALIDATOR_PATTERNS = re.compile(
    r"ANSWER ROUTE|REJECT|rejected|FINAL DECISION DEBUG|FINAL ANSWER SOURCE|"
    r"missing_query_entity|no_predicate_fragment|missing_definition_cue|"
    r"definition_not_found_strict|DOC ROUTER|OCR|DEF QUALITY|LIST",
    re.IGNORECASE,
)


class TraceHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = record.getMessage()
        except Exception:
            return
        if VALIDATOR_PATTERNS.search(msg):
            self.records.append(msg)


def _preview(text: str, limit: int = 160) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip())[:limit]


def _src(d: dict) -> str:
    md = dict((d or {}).get("metadata") or {})
    return str(md.get("source") or md.get("filename") or md.get("source_name") or "<no-source>")


def run_query(query: str) -> None:
    print("=" * 110)
    print(f"QUERY: {query}")
    print("-" * 110)

    family = srv._classify_query_family_v2(query)
    route = srv._resolve_grounded_answer_route(query)
    print(f"  route={route}  family_v2={family}")

    docs = list(srv.live_rag.search(query, top_k=10, return_dicts=True, enable_rerank=True) or [])
    print(f"  retrieved={len(docs)} (reranked order)")
    for i, d in enumerate(docs[:10]):
        dist = (d or {}).get("distance")
        rer = (d or {}).get("reranker_score")
        sim = (d or {}).get("similarity") or (d or {}).get("score")
        print(f"    [{i}] src={_src(d)} dist={dist} rerank={rer} sim={sim}")
        print(f"         {_preview((d or {}).get('page_content') or (d or {}).get('text'))}")

    # Active-source filter behaviour (default registry state).
    active = srv._get_active_sources()
    filtered = srv._filter_doc_dicts_to_active_sources(docs)
    print(f"  active_sources={sorted(active) if active else '<EMPTY>'} -> filtered_docs={len(filtered)}")

    trace = TraceHandler()
    alog = logging.getLogger("Assistify")
    prev_level = alog.level
    alog.setLevel(logging.INFO)
    alog.addHandler(trace)
    try:
        decision = srv._shared_rag_final_answer_decision(query, docs, llm_text=None)
    finally:
        alog.removeHandler(trace)
        alog.setLevel(prev_level)

    print(f"  answer_type={decision.get('answer_type')} source_mode={decision.get('source_mode')} used_llm={decision.get('used_llm')}")
    print(f"  FINAL_ANSWER={decision.get('answer')!r}")
    print("  VALIDATOR TRACE:")
    for line in trace.records:
        print(f"     | {_preview(line, 200)}")
    print()


def phase1_ocr() -> None:
    import pdfplumber
    from backend.pdf_ingestion_rag import _repair_split_words

    pdf = ROOT / "backend" / "assets" / "adaadcd0_Meridian_Financial_Handbook_Clean.pdf"
    print("=" * 110)
    print("PHASE 1 — OCR / TEXT CORRUPTION ORIGIN")
    print(f"PDF: {pdf}")
    print("-" * 110)
    targets = ["perdepositor", "perownership", "webbanking", "ourmobile", "bankand", "lowannual", "feebilled", "aU.S", "mypassword", "myphone"]
    with pdfplumber.open(str(pdf)) as doc:
        for pno, page in enumerate(doc.pages, 1):
            raw_nolayout = page.extract_text(layout=False) or ""
            repaired = _repair_split_words(raw_nolayout)
            for t in targets:
                in_raw = t.lower() in raw_nolayout.lower()
                in_rep = t.lower() in repaired.lower()
                if in_raw or in_rep:
                    # find context in raw
                    idx = raw_nolayout.lower().find(t.lower())
                    ctx = re.sub(r"\s+", " ", raw_nolayout[max(0, idx - 40): idx + 40]) if idx >= 0 else ""
                    print(f"  page={pno} token={t!r} in_raw_extract={in_raw} in_after_repair={in_rep}")
                    if ctx:
                        print(f"       raw_ctx: ...{ctx}...")


def phase4_leak() -> None:
    print("=" * 110)
    print("PHASE 4 — CROSS-DOCUMENT LEAKAGE DEMO")
    print("-" * 110)
    q = "How do I open an account?"
    docs = list(srv.live_rag.search(q, top_k=10, return_dicts=True, enable_rerank=True) or [])
    print(f"  query={q!r} retrieved={len(docs)}")
    for i, d in enumerate(docs):
        md = dict((d or {}).get("metadata") or {})
        keys = sorted(k for k in md.keys())
        source_keys = srv._metadata_source_keys(md)
        print(f"    [{i}] src={_src(d)} source_keys={sorted(source_keys) if source_keys else '<NONE>'}")
        print(f"         meta_keys={keys}")
        print(f"         {_preview((d or {}).get('page_content') or (d or {}).get('text'))}")
    print(f"\n  _get_active_sources() at rest = {sorted(srv._get_active_sources()) or '<EMPTY>'}")


def main() -> int:
    if "--ocr" in sys.argv:
        phase1_ocr()
        return 0
    if "--leak" in sys.argv:
        phase4_leak()
        return 0
    only = None
    for a in sys.argv[1:]:
        if a.startswith("--only="):
            only = a.split("=", 1)[1]
    queries = ALL_QUERIES
    if only == "def":
        queries = DEFINITION_QUERIES
    elif only == "fact":
        queries = FACT_QUERIES
    elif only == "proc":
        queries = PROCEDURAL_QUERIES
    for q in queries:
        run_query(q)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
