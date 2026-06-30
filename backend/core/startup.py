"""Extracted retrieval helpers (Phase 8H).

Moved verbatim from ``assistify_rag_server.py``. This module is a leaf in the
retrieval package and never imports the server. Shared mutable state, the
logger, and engine functions still in the monolith are reached through ``S``,
the server module injected via ``bind_server`` at registration time. Behavior is
identical to the monolith original.
"""
from __future__ import annotations

from backend.config_head import *  # noqa: F401,F403 - mirrors the server module
from pathlib import Path
from backend.retrieval.generation import RAG_DOC_MODE
import asyncio
from backend.knowledge_base import build_canonical_source_metadata
from backend.knowledge_base import canonical_source_doc_id
from collections import defaultdict
from backend.knowledge_base import delete_documents_by_source_identity
from backend.knowledge_base import normalize_uploaded_filename
from backend.knowledge_base import original_filename_from_stored
import os
import time

S = None


def bind_server(server) -> None:
    """Bind the live server module so extracted helpers can reach shared state."""
    global S
    S = server

os.environ['CHROMA_TELEMETRY_IMPL'] = 'none'

INGEST_INDEX_TIMEOUT_S = float(os.environ.get("INGEST_INDEX_TIMEOUT_S", "600"))

_assets_reindex_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

_RECENTLY_DELETED_TTL_S: float = 3600.0  # 1h is plenty: covers a fresh boot

def _normalize_filename_for_tombstone(name: str) -> str:
    return str(name or "").strip().lower()

def _mark_recently_deleted(name: str, seconds: float = _RECENTLY_DELETED_TTL_S) -> None:
    key = _normalize_filename_for_tombstone(name)
    if not key:
        return
    S._recently_deleted_filenames[key] = time.time() + float(seconds)

def _is_recently_deleted(name: str) -> bool:
    key = _normalize_filename_for_tombstone(name)
    if not key:
        return False
    expiry = S._recently_deleted_filenames.get(key)
    if not expiry:
        return False
    if time.time() >= expiry:
        # TTL elapsed — drop stale entry so we don't grow unbounded.
        S._recently_deleted_filenames.pop(key, None)
        return False
    return True

def _ownership_keys_for_filename(name: str) -> set[str]:
    raw = str(name or "").strip()
    keys = {raw.lower()} if raw else set()
    try:
        base = Path(raw).name
        if base:
            keys.add(base.lower())
            keys.add(original_filename_from_stored(base).lower())
            normalized = normalize_uploaded_filename(base)
            if normalized:
                keys.add(normalized)
    except Exception:
        pass
    return {k for k in keys if k}

def _mark_upload_pipeline_owned(*names: str, seconds: float = 600.0) -> None:
    expiry = time.time() + float(seconds)
    for name in names:
        for key in _ownership_keys_for_filename(name):
            S._assets_upload_owned_until[key] = expiry

def _is_upload_pipeline_owned(name: str) -> bool:
    now = time.time()
    owned = False
    for key in _ownership_keys_for_filename(name):
        expiry = S._assets_upload_owned_until.get(key)
        if not expiry:
            continue
        if now >= expiry:
            S._assets_upload_owned_until.pop(key, None)
            continue
        owned = True
    return owned

def _assets_reindex_skip_reason(filename: str) -> str:
    if _is_recently_deleted(filename):
        return "recently_deleted"
    if _is_upload_pipeline_owned(filename):
        return "owned_by_upload_pipeline"
    now = time.time()
    until = S._assets_recently_indexed_until.get(filename)
    if until and now < until:
        return "recently_indexed"
    return ""

def _log_assets_reindex_skip(filename: str, reason: str) -> None:
    if reason == "owned_by_upload_pipeline":
        S.logger.info("[INGEST WATCHER] skipped reason=owned_by_upload_pipeline file=%s", filename)
    elif reason:
        S.logger.info("Assets watcher: skip reason=%s file=%s", reason, filename)

def _should_skip_assets_reindex(filename: str) -> bool:
    """Return True if we should skip reindexing because the upload endpoint
    already indexed it (prevents double work from watchdog create/modify)
    OR because the file was explicitly deleted (anti-resurrection guard).
    """
    return bool(_assets_reindex_skip_reason(filename))

def _mark_assets_recently_indexed(filename: str, seconds: float = 120.0) -> None:
    S._assets_recently_indexed_until[filename] = time.time() + seconds

def _queue_assets_reindex(filename: str, delay_s: float = 0.75) -> None:
    """Debounce reindex requests for the same filename."""
    skip_reason = _assets_reindex_skip_reason(filename)
    if skip_reason:
        _log_assets_reindex_skip(filename, skip_reason)
        return
    prev = S._assets_reindex_tasks.get(filename)
    if prev and not prev.done():
        prev.cancel()
    S._assets_reindex_tasks[filename] = asyncio.create_task(_debounced_reindex(filename, delay_s=delay_s))

async def _debounced_reindex(filename: str, delay_s: float = 0.75) -> None:
    await asyncio.sleep(delay_s)
    skip_reason = _assets_reindex_skip_reason(filename)
    if skip_reason:
        _log_assets_reindex_skip(filename, skip_reason)
        return
    save_path = ASSETS_DIR / filename
    if not save_path.exists():
        return

    # Wait until file stops changing (Windows tends to fire created+modified)
    try:
        last = save_path.stat()
        for _ in range(3):
            await asyncio.sleep(0.35)
            cur = save_path.stat()
            if cur.st_size == last.st_size and cur.st_mtime == last.st_mtime:
                break
            last = cur
    except Exception:
        # If stat fails, just attempt reindex once
        pass

    async with _assets_reindex_locks[filename]:
        # Double-check skip inside the lock
        skip_reason = _assets_reindex_skip_reason(filename)
        if skip_reason:
            _log_assets_reindex_skip(filename, skip_reason)
            return
        await _reindex_file_auto(filename)

def _extract_text_from_asset(save_path: Path) -> str:
    """Extract text from a .txt or .pdf asset.

    IMPORTANT: Never decode PDF bytes as UTF-8. That produces '%PDF-1.4' and
    'obj<</...>>' chunks which are not human text.
    """
    suffix = save_path.suffix.lower()
    if suffix == ".pdf":
        try:
            from backend.pdf_ingestion_rag import extract_pdf_asset_text

            text, total_pages, non_empty_pages = extract_pdf_asset_text(save_path)
            S.logger.info(
                "PDF extraction | file=%s pages=%s non_empty=%s chars=%s",
                save_path.name,
                total_pages,
                non_empty_pages,
                len(text),
            )
            return text
        except Exception as e:
            S.logger.warning(f"Assets watcher: PDF extraction failed for {save_path.name}: {e}")
            return ""

    # Default: treat as text file
    content = save_path.read_bytes()
    try:
        return content.decode("utf-8")
    except Exception:
        return content.decode(errors="ignore")

def _pick_verification_snippet(text: str) -> str:
    """Pick a reasonable human-ish line for verification search."""
    for line in (text or "").splitlines():
        s = line.strip()
        if not s:
            continue
        # Skip PDF headers / object dumps
        if s.startswith("%PDF") or " obj" in s or "<</" in s:
            continue
        if len(s) < 25:
            continue
        # Prefer lines with letters
        if any(ch.isalpha() for ch in s):
            return s[:120]
    # Fallback
    return (text.strip().replace("\n", " ")[:120]) if text else ""

async def _reindex_file_auto(filename: str):
    """Background helper to reindex a file by filename.

    Uses delete_documents_by_filename() to wipe ALL previous chunks for this
    file (including any orphaned chunks with a different doc_id prefix created
    during earlier buggy runs), then re-indexes with a stable doc_id.
    Verifies the new content is searchable after write.
    """
    try:
        skip_reason = _assets_reindex_skip_reason(filename)
        if skip_reason:
            _log_assets_reindex_skip(filename, skip_reason)
            return
        save_path = ASSETS_DIR / filename
        if not save_path.exists():
            S.logger.warning(f"Assets watcher: file disappeared before reindex: {filename}")
            return
        text = await asyncio.to_thread(_extract_text_from_asset, save_path)

        if not text.strip():
            S.logger.info(f"Assets watcher: skipping empty/unextractable file: {filename}")
            return

        # ---- STEP 1+2 under collection mutation lock ----
        # Serialize delete+index+switch to avoid races with upload/delete endpoints.
        original_filename = original_filename_from_stored(filename)
        metadata = build_canonical_source_metadata(
            original_filename=original_filename,
            stored_filename=filename,
            upload_id="assets_watcher",
            document_version=str(int(save_path.stat().st_mtime)),
        )
        metadata.update({"file_ext": save_path.suffix.lower(), "ingestion_owner": "rag_server_watcher"})
        doc_id = str(metadata.get("source_doc_id") or canonical_source_doc_id(metadata.get("normalized_filename") or original_filename))

        async with S._collection_mutation():
            delete_report = await asyncio.to_thread(
                delete_documents_by_source_identity,
                source_doc_id=str(metadata.get("source_doc_id") or ""),
                original_filename=str(metadata.get("original_filename") or ""),
                stored_filename=str(metadata.get("stored_filename") or filename),
                normalized_filename=str(metadata.get("normalized_filename") or ""),
                doc_prefix=doc_id,
            )
            deleted = int(delete_report.get("deleted_count") or 0)
            S.logger.info(f"Assets watcher [{filename}]: deleted {deleted} old chunk(s)")

            _cad_result = await asyncio.wait_for(
                asyncio.to_thread(
                    chunk_and_add_document,
                    doc_id=doc_id,
                    text=text,
                    metadata=metadata,
                    kb_version=S._kb_global_version + 1,
                ),
                timeout=INGEST_INDEX_TIMEOUT_S,
            )
            added = int(_cad_result) if isinstance(_cad_result, int) else 0
            active_collection = S._sync_live_retrieval_collection()
        if added > 0:
            S._register_active_source(str(metadata.get("normalized_filename") or filename))
        S.logger.info(f"Assets watcher [{filename}]: indexed {added} new chunk(s) (doc_id={doc_id}, collection={active_collection})")

        # Prevent immediate duplicate reindex triggers (created+modified)
        _mark_assets_recently_indexed(filename, seconds=30.0)

        # ---- STEP 3: invalidate all caches + broadcast KB event ----
        await S.invalidate_all_caches(action="reindex", filename=filename,
                                     chunks_added=added, chunks_deleted=deleted,
                                     triggered_by="watcher")

        # ---- STEP 4: verify the new content is searchable ----
        snippet = _pick_verification_snippet(text)
        verify = S._active_rag().search(snippet, top_k=3, distance_threshold=1.5, enable_rerank=True) if snippet else []
        if snippet:
            S.logger.info("[RERANK ACTIVE]")
        if verify:
            S.logger.info(f"Assets watcher [{filename}]: ✓ verification OK — search returns: {str(verify[0])[:60]}...")
        else:
            S.logger.warning(f"Assets watcher [{filename}]: ✗ verification FAILED — search returned nothing for: {snippet[:80]}")
    except Exception as e:
        S.logger.exception(f"Assets watcher reindex failed for {filename}: {e}")

async def _assets_watcher(poll_interval: float = 5.0):
    """Simple polling watcher for the ASSETS_DIR; reindexes changed/new files.

    On the FIRST scan we only record mtimes — we do NOT reindex because the DB
    already contains the data from the original upload.  We only reindex when a
    file is genuinely modified AFTER the server started (mtime changed) or when
    a brand-new file appears that was not present during the first scan.
    """
    S.logger.info("Assets watcher started (polling every %.1fs)", poll_interval)
    seen: dict[str, float] = {}
    first_scan_done = False
    try:
        while True:
            try:
                if not ASSETS_DIR.exists():
                    await asyncio.sleep(poll_interval)
                    continue
                for p in ASSETS_DIR.iterdir():
                    if not p.is_file():
                        continue
                    if p.suffix.lower() not in (".txt", ".pdf", ".md"):
                        continue
                    mtime = p.stat().st_mtime
                    key = str(p.name)
                    prev = seen.get(key)

                    if not first_scan_done:
                        # First scan: just record mtime, don't reindex
                        seen[key] = mtime
                    elif prev is None:
                        # New file added after server started
                        seen[key] = mtime
                        S.logger.info("Assets watcher: new file detected: %s — reindexing", key)
                        _queue_assets_reindex(key)
                    elif mtime != prev:
                        # Existing file was modified
                        seen[key] = mtime
                        S.logger.info("Assets watcher: file modified: %s — reindexing", key)
                        _queue_assets_reindex(key)

                if not first_scan_done:
                    first_scan_done = True
                    S.logger.info("Assets watcher: initial scan done — tracking %d file(s)", len(seen))

                # Remove deleted files from seen
                for key in list(seen.keys()):
                    if not (ASSETS_DIR / key).exists():
                        S.logger.info("Assets watcher: file removed: %s", key)
                        del seen[key]

            except Exception as e:
                S.logger.exception(f"Assets watcher loop error: {e}")
            await asyncio.sleep(poll_interval)
    except asyncio.CancelledError:
        S.logger.info("Assets watcher cancelled; shutting down")

async def _bootstrap_assets_index_if_needed() -> None:
    """Index asset files on startup when they are missing from the active collection.

    Previously skipped whenever *any* chunks existed, leaving orphan PDFs on disk
    unindexed when stale seed data remained in Chroma.
    """
    await asyncio.sleep(1.0)
    try:
        from backend.knowledge_base import find_orphan_asset_files, indexed_source_keys_for_collection

        existing_assets = [
            p.name for p in ASSETS_DIR.iterdir()
            if p.is_file() and p.suffix.lower() in (".txt", ".pdf", ".md")
        ]
        if not existing_assets:
            S.logger.info("KB bootstrap: no asset files found")
            return

        existing_assets = [
            name for name in existing_assets if not _is_recently_deleted(name)
        ]
        if not existing_assets:
            S.logger.info("KB bootstrap: all candidate files are tombstoned (recently deleted)")
            return

        orphans = find_orphan_asset_files(ASSETS_DIR)
        indexed_count = count_documents()
        if not orphans:
            S.logger.info("KB bootstrap: skip (all %d asset file(s) indexed, chunks=%d)", len(existing_assets), indexed_count)
            return

        S.logger.warning(
            "KB bootstrap: %d orphan asset(s) detected (indexed chunks=%d); reindexing now: %s",
            len(orphans),
            indexed_count,
            orphans,
        )

        for filename in orphans:
            await _reindex_file_auto(filename)

        S.logger.info("KB bootstrap complete: indexed chunks=%d orphans_fixed=%d", count_documents(), len(orphans))
    except Exception as e:
        S.logger.exception("KB bootstrap failed: %s", e)

def _rebuild_active_sources_from_collection(tenant_id=None) -> None:
    """Restore in-memory active_sources from chunk metadata.

    Phase 13C: this rebuild is tenant-aware. Retrieval binds strictly to the
    current tenant's collection, so the active-source set must be rebuilt from
    that SAME tenant's collection — never the default/global collection. Reading
    the wrong collection here was the production bug: a tenant's freshly uploaded
    document was validated against another tenant's source list and dropped by
    the anti-leak filter (``Active-source filter returned nothing``).
    """
    try:
        from backend.knowledge_base import (
            get_or_create_collection,
            indexed_source_keys_for_collection,
            resolve_tenant_active_collection,
        )
        from backend.core.tenant_context import current_tenant_id

        try:
            tid = int(tenant_id if tenant_id is not None else current_tenant_id())
        except (TypeError, ValueError):
            tid = int(DEFAULT_TENANT_ID)

        if tid == int(DEFAULT_TENANT_ID):
            col = get_or_create_collection(allow_empty=True)
        else:
            col = resolve_tenant_active_collection(tid)
        if not col or col.count() == 0:
            return
        sources = indexed_source_keys_for_collection(col)
        if not sources:
            return
        mode = S._active_doc_registry.get("mode", RAG_DOC_MODE)
        if mode == "single":
            S._set_active_sources([sorted(sources)[-1]], mode="single", tenant_id=tid)
        else:
            S._set_active_sources(sorted(sources), mode=mode, tenant_id=tid)
        S.logger.info(
            "Active sources rebuilt from collection | tenant=%s mode=%s count=%d",
            tid,
            mode,
            len(sources),
        )
    except Exception as err:
        S.logger.warning("Active source rebuild from collection failed: %s", err)

ASSETS_DIR = Path(ASSETS_DIR)

