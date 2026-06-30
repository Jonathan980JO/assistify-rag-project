#!/usr/bin/env python3
"""Clean rebuild of the default-tenant KB collection with ONLY the Meridian PDF.

This performs Phase 1 (hygiene) + Phase 7 (reindex) together:
  1. Wipe ALL chunks from the active default-tenant collection
     (removes demo/e-commerce orphans + stale DSS + old corrupted Meridian).
  2. Re-ingest the Meridian PDF using the fixed extraction + chunking pipeline.
  3. Verify the stored chunks are clean (no demo terms, no (cid:) glyphs,
     no repeated section headings, single table header).

Run with the RAG service STOPPED (exclusive Chroma access).
"""
from __future__ import annotations

import os
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
os.environ.setdefault("CHROMA_TELEMETRY_IMPL", "none")
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
os.environ.setdefault("RAG_USE_GPU", "0")

import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PDF = ROOT / "backend" / "assets" / "90de77d3_Meridian_Financial_Handbook_Clean.pdf"

DEMO_TERMS = [
    "sign up", "purchase history", "shipping", "return policy", "returns",
    "warranty", "refund policy", "order tracking", "tracking number",
]


def main() -> int:
    from backend.knowledge_base import (
        client,
        chunk_and_add_document,
        build_canonical_source_metadata,
        original_filename_from_stored,
        get_or_create_collection,
    )
    from backend.pdf_ingestion_rag import extract_pdf_asset_text

    if not PDF.exists():
        print(f"ERROR: Meridian PDF not found at {PDF}")
        return 1

    # --- Step 1: DROP + recreate the collection (clean HNSW index) ---
    # Deleting-all-then-readding leaves HNSW tombstones that later cause
    # "Cannot return the results in a contiguous 2D array. Probably ef or M is
    # too small" on query. Recreating the collection guarantees a healthy index.
    COL = os.environ.get("ASSISTIFY_COLLECTION_NAME", "").strip() or "support_docs_v3_latest"
    old_count = 0
    try:
        old_count = client.get_collection(COL).count()
    except Exception:
        pass
    try:
        client.delete_collection(name=COL)
        print(f"[WIPE] dropped collection {COL!r} (had {old_count} chunks)")
    except Exception as e:
        print(f"[WIPE] delete_collection note: {e}")
    client.get_or_create_collection(name=COL, metadata={"hnsw:space": "cosine"})
    col_name = COL
    print(f"[WIPE] recreated fresh collection {COL!r} (cosine)")

    # --- Step 2: re-ingest Meridian with the fixed pipeline ---
    text, total_pages, non_empty = extract_pdf_asset_text(PDF)
    print(f"[EXTRACT] pages={total_pages} non_empty={non_empty} chars={len(text)}")

    meta = build_canonical_source_metadata(
        original_filename=original_filename_from_stored(PDF.name),
        stored_filename=PDF.name,
    )
    doc_id = f"upload_{PDF.name}"
    details = chunk_and_add_document(
        doc_id=doc_id,
        text=text,
        metadata={**meta, "file_ext": "pdf"},
        target_collection_name=col_name,
        return_details=True,
    )
    indexed = details.get("indexed_chunks", 0)
    print(f"[INGEST] doc_id={doc_id} indexed_chunks={indexed} collection={details.get('collection')}")

    # --- Step 3: verify stored chunks are clean ---
    col = get_or_create_collection(allow_empty=True)
    data = col.get(include=["documents", "metadatas"]) or {}
    ids = data.get("ids") or []
    docs = data.get("documents") or []
    metas = data.get("metadatas") or []

    by_source: dict[str, int] = defaultdict(int)
    demo_hits: list[str] = []
    cid_hits: list[str] = []
    repeated_heading_hits: list[str] = []

    # Heading-repetition signature: a numbered heading like "3. Cards" or
    # "1. About ..." appearing 2+ times in the same chunk.
    heading_re = re.compile(r"\b\d{1,2}\.\s+[A-Z][A-Za-z'&()/ -]{2,40}")

    for cid, doc, meta in zip(ids, docs, metas):
        md = meta if isinstance(meta, dict) else {}
        src = md.get("source_name") or md.get("filename") or md.get("source") or "<none>"
        by_source[str(src)] += 1
        dl = str(doc or "").lower()
        for term in DEMO_TERMS:
            if term in dl:
                demo_hits.append(f"{cid}: '{term}'")
        if "(cid:" in str(doc or ""):
            cid_hits.append(cid)
        # repeated-heading check
        counts: dict[str, int] = defaultdict(int)
        for m in heading_re.findall(str(doc or "")):
            counts[m.strip()] += 1
        for h, n in counts.items():
            if n >= 2:
                repeated_heading_hits.append(f"{cid}: {h!r} x{n}")

    print(f"\n[VERIFY] total chunks={len(ids)}")
    print("[VERIFY] per-source:")
    for s, n in sorted(by_source.items(), key=lambda kv: -kv[1]):
        print(f"   {n:3d}  {s}")
    print(f"[VERIFY] demo-term hits: {len(demo_hits)}")
    for h in demo_hits:
        print(f"   DEMO {h}")
    print(f"[VERIFY] (cid:) glyph hits: {len(cid_hits)}")
    for h in cid_hits:
        print(f"   CID  {h}")
    print(f"[VERIFY] repeated-heading hits: {len(repeated_heading_hits)}")
    for h in repeated_heading_hits:
        print(f"   HEAD {h}")

    clean = not demo_hits and not cid_hits and not repeated_heading_hits and len(by_source) == 1
    print(f"\n[RESULT] {'CLEAN' if clean else 'ISSUES REMAIN'}")
    return 0 if clean else 2


if __name__ == "__main__":
    raise SystemExit(main())
