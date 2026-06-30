#!/usr/bin/env python3
"""
Collection Hygiene Utility — Sprint #3 Phase 1.

Removes orphan chunks from the active Chroma collection:
  - chunks missing source, filename, and document_id
  - chunks whose source does not match any active tenant document
  - stale DSS.pdf / demo chunks not part of any active upload

Usage:
    python -m backend.cleanup_collection [--tenant-id N] [--dry-run] [--verbose]
"""
from __future__ import annotations

import argparse
import logging
import re
import sys
from pathlib import Path
from typing import Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("cleanup_collection")

# Known orphan / demo source labels — chunks whose source matches any of these
# (and that are NOT the currently active upload) will be deleted.
_DEMO_SOURCE_LABELS = frozenset({
    "dss.pdf",
    "dss",
    "demo",
    "sample",
    "test",
    "sign up",
    "purchase history",
    "warranty",
    "shipping",
    "returns",
    "return policy",
})

_STORED_PREFIX_RE = re.compile(r"^[0-9a-fA-F]{8}_")


def _normalize(s: str) -> str:
    raw = Path(str(s or "").strip()).name
    raw = _STORED_PREFIX_RE.sub("", raw)
    return raw.lower()


def _chunk_source_keys(metadata: dict) -> set[str]:
    md = metadata or {}
    candidates = {
        str(md.get("source_doc_id") or "").strip(),
        str(md.get("source_name") or "").strip(),
        str(md.get("original_filename") or "").strip(),
        str(md.get("stored_filename") or "").strip(),
        str(md.get("normalized_filename") or "").strip(),
        str(md.get("source") or "").strip(),
        str(md.get("filename") or "").strip(),
        str(md.get("source_filename") or "").strip(),
        str(md.get("file") or "").strip(),
        str(md.get("doc_id") or "").strip(),
        str(md.get("document_id") or "").strip(),
        str(md.get("base_doc_id") or "").strip(),
    }
    keys: set[str] = set()
    for c in candidates:
        n = _normalize(c)
        if n:
            keys.add(n)
    return keys


def _is_orphan(metadata: dict) -> bool:
    """True when the chunk has no usable source identity at all."""
    return not _chunk_source_keys(metadata)


def _is_demo_chunk(metadata: dict, active_sources: set[str]) -> bool:
    """True when the chunk belongs to a known demo/stale source and is not active."""
    keys = _chunk_source_keys(metadata)
    if not keys:
        return False  # already handled by _is_orphan
    if keys & active_sources:
        return False  # chunk belongs to an active document — keep it
    # Check whether any key matches a known stale label
    for k in keys:
        if k in _DEMO_SOURCE_LABELS:
            return True
        # DSS.pdf by any variant
        if "dss" in k:
            return True
    return False


def cleanup_collection(
    tenant_id: Optional[int] = None,
    dry_run: bool = True,
    verbose: bool = False,
) -> dict:
    """
    Scan the active collection for orphan and stale demo chunks and delete them.

    Returns a summary dict with counts.
    """
    try:
        from backend.knowledge_base import (
            client,
            get_or_create_collection,
            resolve_tenant_active_collection,
            indexed_source_keys_for_collection,
        )
    except ImportError:
        import os, sys
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from backend.knowledge_base import (
            client,
            get_or_create_collection,
            resolve_tenant_active_collection,
            indexed_source_keys_for_collection,
        )

    if tenant_id is not None:
        collection = resolve_tenant_active_collection(tenant_id)
    else:
        collection = get_or_create_collection(allow_empty=True)

    if not collection:
        logger.error("No collection available — aborting.")
        return {"error": "no collection"}

    col_name = getattr(collection, "name", "<unknown>")
    total = collection.count()
    logger.info("Collection: %s  chunks: %d", col_name, total)

    if total == 0:
        logger.info("Collection is empty — nothing to clean up.")
        return {"collection": col_name, "total": 0, "orphans": 0, "demo": 0, "deleted": 0}

    # Retrieve all chunk metadata
    result = collection.get(include=["metadatas"]) or {}
    ids: list[str] = list(result.get("ids") or [])
    metas: list[dict] = list(result.get("metadatas") or [])

    if len(ids) != len(metas):
        logger.warning("ids/metadatas length mismatch (%d vs %d) — using min", len(ids), len(metas))
        n = min(len(ids), len(metas))
        ids, metas = ids[:n], metas[:n]

    # Determine the active sources from the collection itself
    active_sources = indexed_source_keys_for_collection(collection)
    logger.info("Active sources in collection (%d): %s", len(active_sources), sorted(active_sources)[:20])

    orphan_ids: list[str] = []
    demo_ids: list[str] = []

    for chunk_id, meta in zip(ids, metas):
        md = meta if isinstance(meta, dict) else {}
        if _is_orphan(md):
            orphan_ids.append(chunk_id)
            if verbose:
                logger.info("  ORPHAN %s", chunk_id)
            continue
        if _is_demo_chunk(md, active_sources):
            demo_ids.append(chunk_id)
            if verbose:
                src = _chunk_source_keys(md)
                logger.info("  DEMO   %s  source=%s", chunk_id, sorted(src))

    to_delete = orphan_ids + demo_ids
    logger.info(
        "Cleanup plan: orphans=%d  demo=%d  total_to_delete=%d  dry_run=%s",
        len(orphan_ids), len(demo_ids), len(to_delete), dry_run,
    )

    if not to_delete:
        logger.info("Nothing to delete — collection is clean.")
        return {
            "collection": col_name,
            "total": total,
            "orphans": 0,
            "demo": 0,
            "deleted": 0,
        }

    if dry_run:
        logger.info("[DRY RUN] Would delete %d chunks. Pass --no-dry-run to execute.", len(to_delete))
        return {
            "collection": col_name,
            "total": total,
            "orphans": len(orphan_ids),
            "demo": len(demo_ids),
            "deleted": 0,
            "dry_run": True,
        }

    # Delete in batches of 500
    batch_size = 500
    deleted = 0
    for i in range(0, len(to_delete), batch_size):
        batch = to_delete[i : i + batch_size]
        try:
            collection.delete(ids=batch)
            deleted += len(batch)
            logger.info("Deleted batch %d/%d (%d chunks)", i // batch_size + 1, (len(to_delete) + batch_size - 1) // batch_size, len(batch))
        except Exception as e:
            logger.error("Batch delete failed: %s", e)

    after = collection.count()
    logger.info("Done. before=%d  deleted=%d  after=%d", total, deleted, after)
    return {
        "collection": col_name,
        "total": total,
        "orphans": len(orphan_ids),
        "demo": len(demo_ids),
        "deleted": deleted,
        "after": after,
    }


def _add_null_source_retrieval_guard():
    """
    Log the null-source chunks that would leak through retrieval.
    This is informational — the actual guard is in _filter_results_to_active_sources.
    """
    pass  # guard is enforced in assistify_rag_server.py


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Clean orphan chunks from the Chroma collection.")
    parser.add_argument("--tenant-id", type=int, default=None, help="Tenant ID (default: global)")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Simulate without deleting (default: True)")
    parser.add_argument("--no-dry-run", dest="dry_run", action="store_false", help="Actually delete chunks")
    parser.add_argument("--verbose", action="store_true", help="Log every chunk ID being deleted")
    args = parser.parse_args()

    summary = cleanup_collection(
        tenant_id=args.tenant_id,
        dry_run=args.dry_run,
        verbose=args.verbose,
    )
    print("\nSummary:")
    for k, v in summary.items():
        print(f"  {k}: {v}")
