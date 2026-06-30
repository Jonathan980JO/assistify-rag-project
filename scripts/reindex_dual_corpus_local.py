#!/usr/bin/env python3
"""Reindex IBM HR and Psychology PDFs locally (no HTTP server required)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _find_asset(name_fragment: str, assets_dir: Path) -> Path | None:
    frag = name_fragment.lower()
    for path in sorted(assets_dir.iterdir()):
        if not path.is_file() or path.suffix.lower() != ".pdf":
            continue
        if frag in path.name.lower():
            return path
    return None


def reindex_file(path: Path) -> int:
    from backend.knowledge_base import (
        build_canonical_source_metadata,
        canonical_source_doc_id,
        chunk_and_add_document,
        delete_documents_by_source_identity,
        original_filename_from_stored,
    )
    from backend.pdf_ingestion_rag import extract_pdf_asset_text

    text, total_pages, non_empty = extract_pdf_asset_text(path)
    if not text.strip():
        raise RuntimeError(f"Extraction produced no text for {path.name}")

    original_filename = original_filename_from_stored(path.name)
    metadata = build_canonical_source_metadata(
        original_filename=original_filename,
        stored_filename=path.name,
        upload_id="local_reindex",
        document_version=str(int(path.stat().st_mtime)),
    )
    doc_id = str(metadata.get("source_doc_id") or canonical_source_doc_id(metadata.get("normalized_filename") or original_filename))
    delete_report = delete_documents_by_source_identity(
        source_doc_id=str(metadata.get("source_doc_id") or ""),
        original_filename=str(metadata.get("original_filename") or ""),
        stored_filename=str(metadata.get("stored_filename") or path.name),
        normalized_filename=str(metadata.get("normalized_filename") or ""),
        doc_prefix=doc_id,
    )
    deleted = int(delete_report.get("deleted_count") or 0)
    chunks = chunk_and_add_document(doc_id=doc_id, text=text, metadata=metadata, kb_version=1)
    print(f"  {path.name}: pages={total_pages} non_empty={non_empty} deleted={deleted} indexed={chunks}")
    return int(chunks or 0)


def main() -> int:
    parser = argparse.ArgumentParser(description="Reindex dual-corpus PDFs locally")
    parser.add_argument("--ibm-only", action="store_true", help="Reindex IBM HR PDF only")
    parser.add_argument("--all", action="store_true", help="Reindex all PDFs in assets dir")
    args = parser.parse_args()

    from config import ASSETS_DIR

    assets_dir = Path(ASSETS_DIR)
    if not assets_dir.is_dir():
        print(f"FAIL: assets dir missing: {assets_dir}")
        return 1

    targets: list[Path] = []
    if args.all:
        targets = sorted(p for p in assets_dir.iterdir() if p.is_file() and p.suffix.lower() == ".pdf")
    elif args.ibm_only:
        ibm = _find_asset("ibm", assets_dir) or _find_asset("attrition", assets_dir)
        if not ibm:
            print("FAIL: IBM HR PDF not found in assets")
            return 1
        targets = [ibm]
    else:
        ibm = _find_asset("ibm", assets_dir) or _find_asset("attrition", assets_dir)
        psych = _find_asset("psychology", assets_dir)
        if ibm:
            targets.append(ibm)
        if psych:
            targets.append(psych)
        if not targets:
            print("FAIL: no IBM/Psychology PDFs found")
            return 1

    print(f"Reindexing {len(targets)} file(s) from {assets_dir}")
    total = 0
    for path in targets:
        try:
            total += reindex_file(path)
        except Exception as exc:
            print(f"  FAIL {path.name}: {exc}")
            return 1

    print(f"Done. Total chunks indexed: {total}")
    print("NOTE: Restart RAG server (or use Admin Reindex) so live queries pick up the new index.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
