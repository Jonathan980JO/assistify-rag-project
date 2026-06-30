#!/usr/bin/env python3
"""
Phase 6 — Reindex Meridian after OCR / chunking fixes.

Usage:
    python scripts/reindex_meridian.py [--tenant-id 4] [--dry-run]

Steps:
  1. Locate the active Meridian PDF asset on disk.
  2. Delete all existing Meridian chunks from the collection.
  3. Re-ingest the PDF using the fixed OCR / chunking pipeline.
  4. Verify the new chunks do not contain merged words.
  5. Print a summary.
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Ensure project root is on sys.path when run as a standalone script.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("reindex_meridian")

MERIDIAN_KEYWORDS = (
    "meridian",
    "meridian financial",
    "meridian_financial",
)

# Merged words that should no longer appear after the OCR fix.
BANNED_MERGED = (
    "webbanking",
    "lowannual",
    "feebilled",
    "mypassword",
    "myphone",
    "perdepositor",
    "perownership",
)


def find_meridian_asset(assets_dir: Path) -> Path | None:
    for path in sorted(assets_dir.iterdir()):
        if not path.is_file():
            continue
        name_l = path.name.lower()
        if any(k in name_l for k in MERIDIAN_KEYWORDS) and path.suffix.lower() == ".pdf":
            return path
    return None


def delete_meridian_chunks(tenant_id: int | None, dry_run: bool) -> int:
    from backend.knowledge_base import (
        resolve_tenant_active_collection,
        get_or_create_collection,
        indexed_source_keys_for_collection,
    )

    if tenant_id is not None:
        col = resolve_tenant_active_collection(tenant_id)
    else:
        col = get_or_create_collection(allow_empty=True)

    if not col:
        logger.error("No collection found.")
        return 0

    result = col.get(include=["metadatas"]) or {}
    ids = list(result.get("ids") or [])
    metas = list(result.get("metadatas") or [])

    to_delete = []
    for chunk_id, meta in zip(ids, metas):
        md = meta if isinstance(meta, dict) else {}
        all_vals = " ".join(str(v) for v in md.values()).lower()
        if any(k in all_vals for k in MERIDIAN_KEYWORDS):
            to_delete.append(chunk_id)

    logger.info("Found %d Meridian chunks to delete (dry_run=%s)", len(to_delete), dry_run)
    if not dry_run and to_delete:
        batch = 500
        for i in range(0, len(to_delete), batch):
            col.delete(ids=to_delete[i : i + batch])
        logger.info("Deleted %d Meridian chunks.", len(to_delete))
    return len(to_delete)


def ingest_meridian(pdf_path: Path, tenant_id: int | None, dry_run: bool) -> int:
    if dry_run:
        logger.info("[DRY RUN] Would ingest: %s", pdf_path)
        return 0

    from backend.pdf_ingestion_rag import extract_pdf_asset_text, format_pdf_pages_for_indexing
    from backend.knowledge_base import (
        chunk_and_add_document,
        build_canonical_source_metadata,
        resolve_tenant_active_collection,
        get_or_create_collection,
    )

    logger.info("Extracting text from %s ...", pdf_path)
    text, total_pages, non_empty = extract_pdf_asset_text(pdf_path)
    logger.info("Extracted %d pages (%d non-empty).", total_pages, non_empty)

    source_meta = build_canonical_source_metadata(
        original_filename=pdf_path.name,
        stored_filename=pdf_path.name,
    )
    doc_id = f"upload_{pdf_path.name}"

    if tenant_id is not None:
        col = resolve_tenant_active_collection(tenant_id)
    else:
        col = get_or_create_collection(allow_empty=True)

    col_name = getattr(col, "name", None) if col else None
    details = chunk_and_add_document(
        doc_id=doc_id,
        text=text,
        metadata={**source_meta, "file_ext": "pdf"},
        target_collection_name=col_name,
        tenant_id=tenant_id,
        return_details=True,
    )
    indexed = details.get("indexed_chunks", 0) if isinstance(details, dict) else int(details or 0)
    logger.info("Indexed %d chunks.", indexed)
    return indexed


def verify_no_merged_words(tenant_id: int | None) -> list[str]:
    """Scan stored Meridian chunks for known OCR-merged words."""
    from backend.knowledge_base import (
        resolve_tenant_active_collection,
        get_or_create_collection,
    )

    if tenant_id is not None:
        col = resolve_tenant_active_collection(tenant_id)
    else:
        col = get_or_create_collection(allow_empty=True)

    if not col:
        return []

    result = col.get(include=["documents", "metadatas"]) or {}
    ids = list(result.get("ids") or [])
    docs = list(result.get("documents") or [])
    metas = list(result.get("metadatas") or [])

    found_merged: list[str] = []
    for chunk_id, doc, meta in zip(ids, docs, metas):
        md = meta if isinstance(meta, dict) else {}
        all_vals = " ".join(str(v) for v in md.values()).lower()
        if not any(k in all_vals for k in MERIDIAN_KEYWORDS):
            continue
        doc_l = str(doc or "").lower()
        for banned in BANNED_MERGED:
            if banned in doc_l:
                found_merged.append(f"{chunk_id}: contains '{banned}'")
    return found_merged


def main() -> None:
    parser = argparse.ArgumentParser(description="Reindex Meridian PDF after OCR/chunking fixes.")
    parser.add_argument("--tenant-id", type=int, default=4, help="Tenant ID for Meridian (default: 4)")
    parser.add_argument("--dry-run", action="store_true", default=False, help="Simulate without modifying data")
    parser.add_argument("--assets-dir", type=str, default=None, help="Override assets directory path")
    args = parser.parse_args()

    tenant_id = args.tenant_id
    dry_run = args.dry_run

    if args.assets_dir:
        assets_dir = Path(args.assets_dir)
    else:
        assets_dir = ROOT / "backend" / "assets" / f"tenant_{tenant_id}"

    logger.info("=== Reindex Meridian — tenant_id=%s dry_run=%s ===", tenant_id, dry_run)

    # Step 1: Locate Meridian PDF
    pdf_path = find_meridian_asset(assets_dir)
    if not pdf_path:
        logger.error("No Meridian PDF found in %s", assets_dir)
        sys.exit(1)
    logger.info("Meridian PDF: %s", pdf_path)

    # Step 2: Delete existing Meridian vectors
    deleted = delete_meridian_chunks(tenant_id, dry_run)
    logger.info("Step 2 complete: deleted=%d", deleted)

    # Step 3: Re-ingest
    indexed = ingest_meridian(pdf_path, tenant_id, dry_run)
    logger.info("Step 3 complete: indexed=%d", indexed)

    # Step 4: Verify no merged words
    if not dry_run:
        issues = verify_no_merged_words(tenant_id)
        if issues:
            logger.warning("OCR MERGE ISSUES FOUND (%d):", len(issues))
            for issue in issues:
                logger.warning("  %s", issue)
        else:
            logger.info("Step 4: No merged words found — OCR fix confirmed.")

    logger.info("=== Reindex complete ===")
    print(f"\ndeleted={deleted}  indexed={indexed}  dry_run={dry_run}")


if __name__ == "__main__":
    main()
