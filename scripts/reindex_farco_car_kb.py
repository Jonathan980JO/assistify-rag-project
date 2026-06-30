#!/usr/bin/env python3
"""Reindex Farco tenant (id=3) car knowledge base with current chunking pipeline."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

FARCO_TENANT_ID = 3


def _pick_car_pdf(assets_dir: Path) -> Path:
    pdfs = sorted(assets_dir.glob("*.pdf"), key=lambda p: p.stat().st_mtime, reverse=True)
    car_pdfs = [p for p in pdfs if "car" in p.name.lower() or "knowledge" in p.name.lower()]
    if not car_pdfs:
        car_pdfs = pdfs
    if not car_pdfs:
        raise FileNotFoundError(f"No PDF files in {assets_dir}")
    return car_pdfs[0]


def reindex_farco(path: Path, tenant_id: int = FARCO_TENANT_ID) -> int:
    from backend.assistify_rag_server import get_tenant_rag, _TenantScope, _sync_live_retrieval_collection
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
        upload_id="farco_reindex",
        document_version=str(int(path.stat().st_mtime)),
    )
    metadata["file_ext"] = "pdf"
    metadata["tenant_id"] = int(tenant_id)
    doc_id = str(
        metadata.get("source_doc_id")
        or canonical_source_doc_id(metadata.get("normalized_filename") or original_filename)
    )

    delete_report = delete_documents_by_source_identity(
        source_doc_id=str(metadata.get("source_doc_id") or ""),
        original_filename=str(metadata.get("original_filename") or ""),
        stored_filename=str(metadata.get("stored_filename") or path.name),
        normalized_filename=str(metadata.get("normalized_filename") or ""),
        doc_prefix=doc_id,
        tenant_id=tenant_id,
    )
    deleted = int(delete_report.get("deleted_count") or 0)

    details = chunk_and_add_document(
        doc_id=doc_id,
        text=text,
        metadata=metadata,
        kb_version=1,
        return_details=True,
        tenant_id=tenant_id,
    )
    indexed = int(details.get("indexed_chunks") or 0)
    generated = int(details.get("generated_chunks") or 0)

    with _TenantScope(tenant_id):
        _sync_live_retrieval_collection(tenant_id=tenant_id)
        mgr = get_tenant_rag(tenant_id)
        mgr.vs = None

    print(
        f"Farco tenant={tenant_id} file={path.name} "
        f"pages={total_pages} non_empty={non_empty} "
        f"deleted={deleted} generated={generated} indexed={indexed}"
    )
    return indexed


def main() -> int:
    parser = argparse.ArgumentParser(description="Reindex Farco car KB for tenant 3")
    parser.add_argument(
        "--pdf",
        type=Path,
        default=None,
        help="Path to car knowledge PDF (default: newest in backend/assets/tenant_3)",
    )
    parser.add_argument("--tenant-id", type=int, default=FARCO_TENANT_ID)
    args = parser.parse_args()

    pdf_path = args.pdf
    if pdf_path is None:
        assets_dir = REPO_ROOT / "backend" / "assets" / f"tenant_{args.tenant_id}"
        if not assets_dir.is_dir():
            print(f"FAIL: {assets_dir} not found")
            return 1
        pdf_path = _pick_car_pdf(assets_dir)

    if not pdf_path.is_file():
        print(f"FAIL: PDF not found: {pdf_path}")
        return 1

    try:
        indexed = reindex_farco(pdf_path, tenant_id=args.tenant_id)
    except Exception as exc:
        print(f"FAIL: {exc}")
        return 1

    if indexed <= 0:
        print("FAIL: no chunks indexed")
        return 1

    print("Done. Restart RAG server if it was already running.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
