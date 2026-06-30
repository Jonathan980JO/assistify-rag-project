"""Chroma mutation routes (delete / update / replace) for the RAG backend.

Extracted from ``assistify_rag_server.py`` during the Phase 8G refactor.

These handlers mutate live ChromaDB collections and a large amount of server
state. To keep behavior byte-identical and avoid an import cycle, the router is
built by a factory that receives the live server module and reads/writes
attributes on it at request time. The ``_current_active_doc_id`` module global
is written via ``server._current_active_doc_id`` so the server module's value
(not a router-local copy) is updated, exactly as the original ``global``
statement did. Paths, methods, and response bodies are unchanged.
"""
import time
from pathlib import Path
from typing import Set

from fastapi import APIRouter, Depends, HTTPException, Request


def build_chroma_router(server) -> APIRouter:
    """Build the Chroma mutation router bound to the live server module."""
    router = APIRouter()

    @router.post("/rag/delete")
    async def rag_delete(doc_prefix: str, request: Request, user=Depends(server.require_tenant_staff())):
        server.verify_csrf(request)
        """Atomically delete a document: chunks, asset file, active state, and
        any pending watcher work. Returns a truthful report — if the on-disk
        file still exists or the active state still references the deletion
        target, the response surfaces that as failure rather than fake success.

        Example: pass `upload_Best_player.txt` or just `Best_player.txt`
        to remove all chunks associated with that file.
        """
        if not doc_prefix:
            raise HTTPException(status_code=400, detail="doc_prefix is required")

        # Scope this delete to the admin's business: chunk deletion is restricted to
        # the tenant's own collections, and asset cleanup runs in the tenant's own
        # directory. (scope_tid is None for the default tenant, preserving legacy
        # cross-collection orphan cleanup behavior for it only.)
        scope_tid = server._kb_admin_scope_tenant(user)
        req_assets_dirs = server.kb_asset_search_dirs(scope_tid)

        # ---- 0. Compute every plausible filename / asset candidate ---------------
        import re as _re
        _bare = _re.sub(r'^upload_(?:[0-9a-fA-F]{8}_)?', '', doc_prefix)
        asset_candidates: Set[str] = {doc_prefix, _bare}
        if doc_prefix.startswith("upload_"):
            asset_candidates.add(doc_prefix[len("upload_"):])
        asset_candidates = {c.strip() for c in asset_candidates if c and c.strip()}

        # Also include the actual filenames currently sitting in the tenant assets
        # dirs whose bare (UUID-stripped) name matches the requested target. This is
        # how the admin UI's "delete by base name" call still finds the file.
        try:
            target_bare = _re.sub(r'^[0-9a-fA-F]{8}_', '', _bare).lower()
            if target_bare:
                for req_assets_dir in req_assets_dirs:
                    if not req_assets_dir.exists():
                        continue
                    for p in req_assets_dir.iterdir():
                        if not p.is_file():
                            continue
                        if p.suffix.lower() not in {".pdf", ".txt", ".md"}:
                            continue
                        p_bare = _re.sub(r'^[0-9a-fA-F]{8}_', '', p.name).lower()
                        if p_bare == target_bare or p.name.lower() == _bare.lower():
                            asset_candidates.add(p.name)
        except Exception as scan_err:
            server.logger.warning("rag_delete: candidate scan failed: %s", scan_err)

        server.logger.info("[KB DELETE] start | doc_prefix=%s candidates=%s",
                    doc_prefix, sorted(asset_candidates))

        # ---- 0a. Cancel ANY pending watcher reindex tasks for these candidates ---
        # (otherwise a debounced reindex queued just before this call could
        #  resurrect the chunks moments after we delete them).
        cancelled_tasks: list[str] = []
        for cand in list(asset_candidates) + [doc_prefix]:
            task = server._assets_reindex_tasks.pop(cand, None)
            if task and not task.done():
                task.cancel()
                cancelled_tasks.append(cand)

        # ---- 0b. Tombstone every candidate filename so the watchdog/bootstrap ---
        # cannot reindex this file even if the on-disk unlink fails for any reason.
        for cand in list(asset_candidates) + [doc_prefix]:
            server._mark_recently_deleted(cand)

        # ---- 1. Remove all ChromaDB chunks across every collection --------------
        gc_report: dict = {}
        delete_report: dict = {}
        deleted = 0
        async with server._collection_mutation():
            try:
                normalized_target = server.normalize_uploaded_filename(_bare or doc_prefix)
                source_doc_id = server.canonical_source_doc_id(normalized_target) if normalized_target else ""
                delete_report = server.delete_documents_by_source_identity(
                    source_doc_id=source_doc_id,
                    original_filename=server.original_filename_from_stored(_bare or doc_prefix),
                    stored_filename=doc_prefix,
                    normalized_filename=normalized_target,
                    doc_prefix=doc_prefix,
                    extra_keys=sorted(asset_candidates),
                    tenant_id=scope_tid,
                )
                deleted = int(delete_report.get("deleted_count") or 0)
            except Exception as e:
                server.logger.warning("rag_delete: canonical delete failed: %s", e)

            # Garbage-collect now-empty stale support_docs_v3_* collections so
            # _sync_live_retrieval_collection's "scan for non-empty alternatives"
            # fallback can't accidentally surface a stale populated collection
            # that still holds the deleted chunks.
            try:
                active_collection = getattr(getattr(server.live_rag, "vs", None), "collection", None)
                active_collection_name = getattr(active_collection, "name", "") if active_collection else ""
                from backend.knowledge_base import garbage_collect_support_collections
                gc_report = garbage_collect_support_collections(
                    active_collection_name=active_collection_name,
                    delete_non_empty=False,
                    prefix="support_docs_v3_",
                )
            except Exception as gc_err:
                server.logger.warning("rag_delete GC skipped due to error: %s", gc_err)

        # ---- 2. Remove the physical asset file(s) — with retries on Windows ----
        # On Windows, the file may briefly be locked by the watchdog Observer
        # thread or a finished PdfReader handle that hasn't been GC'd yet.
        # Silently swallowing PermissionError is what made the previous version
        # report success while the file stayed on disk and got resurrected by
        # bootstrap on next restart.
        deleted_files: list[str] = []
        failed_unlinks: list[dict] = []

        def _try_unlink(path: Path) -> tuple[bool, str]:
            last_err = ""
            for attempt in range(3):
                try:
                    if not path.exists():
                        return True, ""
                    path.unlink()
                    return True, ""
                except Exception as e:  # PermissionError, OSError, etc.
                    last_err = str(e)
                    time.sleep(0.2)
            return (not path.exists()), last_err

        for candidate in sorted(asset_candidates):
            if not candidate:
                continue
            removed = False
            for req_assets_dir in req_assets_dirs:
                asset_path = req_assets_dir / candidate
                if not (asset_path.exists() and asset_path.is_file()):
                    continue
                ok, err = _try_unlink(asset_path)
                if ok:
                    if not removed:
                        deleted_files.append(candidate)
                        removed = True
                    server.logger.info("rag_delete: removed asset file '%s' from %s", candidate, req_assets_dir)
                else:
                    server.logger.error(
                        "rag_delete: could NOT remove asset file '%s' from %s (still on disk): %s",
                        candidate, req_assets_dir, err,
                    )
                    failed_unlinks.append({"file": candidate, "dir": str(req_assets_dir), "error": err})

        # ---- 3. Reset active state if the deleted doc was the live target ------
        current_sources = server._get_active_sources()
        removed_labels = {server._normalize_source_label(x) for x in list(asset_candidates) + [doc_prefix] if x}
        try:
            normalized_delete_target = server.normalize_uploaded_filename(_bare or doc_prefix)
            if normalized_delete_target:
                removed_labels.add(server._normalize_source_label(normalized_delete_target))
                removed_labels.add(server._normalize_source_label(server.canonical_source_doc_id(normalized_delete_target)))
        except Exception:
            pass
        for label in removed_labels:
            current_sources.discard(label)
        server._set_active_sources(sorted(current_sources), mode=server._active_doc_registry.get("mode", server.RAG_DOC_MODE))

        if server._current_active_doc_id and server._current_active_doc_id in removed_labels:
            server._current_active_doc_id = ""
            server.logger.info("[KB HOT-SWAP] _current_active_doc_id cleared after delete of %s", doc_prefix)

        # Wipe in-memory conversation/follow-up state so the next query cannot
        # produce an answer derived from the deleted document's prior turns.
        try:
            server.clear_all_conversation_history()
        except Exception as e:
            server.logger.warning("rag_delete: clear_all_conversation_history failed: %s", e)

        # ---- 4. If KB is now globally empty, mark pipeline ready+empty so the ---
        # gate doesn't get stuck and so live_rag's fallback collection scan
        # cannot pick a stale populated collection (we just GC'd them above).
        try:
            remaining = int(server.count_documents() or 0)
        except Exception as e:
            server.logger.warning("rag_delete: count_documents failed: %s", e)
            remaining = -1

        kb_now_empty = (remaining == 0)
        if kb_now_empty and scope_tid is None:
            # If nothing remains anywhere, also clear any active source that may
            # still be lingering from another code path, and re-point the live
            # retrieval handle to a fresh empty collection so subsequent queries
            # can't accidentally see the previously-active populated handle.
            server._set_active_sources([], mode=server._active_doc_registry.get("mode", server.RAG_DOC_MODE))
            server._current_active_doc_id = ""
            try:
                new_active = server._sync_live_retrieval_collection()
                server.logger.info("rag_delete: KB now empty; live retrieval re-synced to '%s'", new_active)
            except Exception as sync_err:
                server.logger.warning("rag_delete: live retrieval re-sync failed: %s", sync_err)
            server._set_kb_pipeline_state("ready", message="Knowledge base is empty after delete", filename=None)

        # For non-default tenants, force the tenant retrieval manager to rebind so
        # the deleted chunks immediately disappear from that business's search.
        if scope_tid is not None:
            try:
                server.get_tenant_rag(scope_tid).vs = None
            except Exception:
                pass

        await server.invalidate_all_caches(action="delete", filename=doc_prefix,
                                     chunks_deleted=deleted, triggered_by="admin")

        # ---- 5. Truthful response ----------------------------------------------
        target_remaining = int(delete_report.get("remaining_count") or 0) if delete_report else 0
        success = (not failed_unlinks) and target_remaining == 0
        payload = {
            "success": success,
            "deleted": deleted,
            "delete_verification": delete_report,
            "target_remaining_chunks": target_remaining,
            "files_removed": deleted_files,
            "files_failed": failed_unlinks,
            "cancelled_tasks": cancelled_tasks,
            "tombstoned": sorted({server._normalize_filename_for_tombstone(c) for c in (list(asset_candidates) + [doc_prefix]) if c}),
            "remaining_chunks": remaining,
            "kb_empty": kb_now_empty,
            "collection_gc": gc_report,
            "active_sources": sorted(server._get_active_sources()),
            "current_active_doc_id": server._current_active_doc_id,
            "ready_state": dict(server._kb_pipeline_state),
        }
        if not success:
            # Return 207-ish surface as 500 so the admin UI cannot interpret a
            # half-deletion as full success.
            raise HTTPException(status_code=500, detail=payload)
        return payload

    @router.post("/rag/update")
    async def rag_update(req: dict, request: Request, user=Depends(server.require_tenant_staff())):
        """Update an existing uploaded document (replace and re-chunk).

        JSON body: {"doc_id": "upload_xxx_filename", "text": "...", "metadata": {...}}
        """
        server.verify_csrf(request)
        doc_id = req.get("doc_id")
        text = req.get("text")
        metadata_raw = req.get("metadata")
        metadata = dict(metadata_raw) if isinstance(metadata_raw, dict) else {}
        if not doc_id or text is None:
            raise HTTPException(status_code=400, detail="doc_id and text are required")
        # Scope the update to the admin's tenant so it only touches that business's
        # collection (None => default tenant keeps legacy collection behavior).
        scope_tid = server._kb_admin_scope_tenant(user)
        _raw_update = server.update_document(doc_id=doc_id, text=text, metadata=metadata, tenant_id=scope_tid)
        chunks = int(_raw_update) if isinstance(_raw_update, int) else 0
        if chunks:
            await server.invalidate_all_caches(action="update", filename=doc_id,
                                         chunks_added=chunks, triggered_by="admin")
            return {"updated_chunks": chunks}
        else:
            raise HTTPException(status_code=500, detail="Update failed")

    @router.put("/rag/files/{filename}")
    async def rag_update_asset_file(filename: str, request: Request, user=Depends(server.require_tenant_staff())):
        """Update a text asset and reindex it inside the RAG server only (tenant-scoped)."""
        server.verify_csrf(request)
        if not filename:
            raise HTTPException(status_code=400, detail="filename is required")

        scope_tid = server._kb_admin_scope_tenant(user)
        req_assets_dir = server.ASSETS_DIR if scope_tid is None else server.tenant_assets_dir(scope_tid)
        save_path = req_assets_dir / Path(filename).name
        try:
            resolved_path = save_path.resolve()
            if not str(resolved_path).startswith(str(req_assets_dir.resolve())):
                raise HTTPException(status_code=403, detail="Access denied")
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=404, detail="File not found")

        if not save_path.exists() or not save_path.is_file():
            raise HTTPException(status_code=404, detail="File not found")

        if save_path.suffix.lower() != ".txt":
            raise HTTPException(status_code=400, detail="Can only edit text files")

        data = await request.json()
        content = data.get("content", "")
        if not isinstance(content, str):
            raise HTTPException(status_code=400, detail="content must be a string")

        original_filename = server.original_filename_from_stored(save_path.name)
        metadata = server.build_canonical_source_metadata(
            original_filename=original_filename,
            stored_filename=save_path.name,
            upload_id="rag_text_update",
            document_version=str(int(time.time())),
        )
        metadata.update({"ingestion_owner": "rag_server_update", "file_ext": save_path.suffix.lower()})
        doc_id = str(metadata.get("source_doc_id") or server.canonical_source_doc_id(metadata.get("normalized_filename") or original_filename))

        try:
            server._set_kb_pipeline_stage("writing", message="Writing updated text file", filename=save_path.name)
            server._mark_upload_pipeline_owned(save_path.name, original_filename, str(metadata.get("normalized_filename") or ""), doc_id, seconds=300.0)
            save_path.write_text(content, encoding="utf-8")
            server._mark_assets_recently_indexed(save_path.name, seconds=15.0)
            server._set_kb_pipeline_stage("chunking", message="Chunking updated text", filename=save_path.name)
            async with server._collection_mutation():
                delete_report = server.delete_documents_by_source_identity(
                    source_doc_id=str(metadata.get("source_doc_id") or ""),
                    original_filename=str(metadata.get("original_filename") or ""),
                    stored_filename=str(metadata.get("stored_filename") or save_path.name),
                    normalized_filename=str(metadata.get("normalized_filename") or ""),
                    doc_prefix=doc_id,
                    tenant_id=scope_tid,
                )
                _raw_chunks = await server.asyncio.to_thread(
                    server.chunk_and_add_document,
                    doc_id,
                    content,
                    metadata,
                    server._kb_global_version + 1,
                    False,
                    "",
                    lambda event: server._on_ingest_progress(event, save_path.name),
                    scope_tid,
                )
            chunks = int(_raw_chunks) if isinstance(_raw_chunks, int) else 0
            if chunks <= 0:
                server._set_kb_pipeline_state("failed", message="Update produced no chunks", filename=save_path.name)
                raise HTTPException(status_code=500, detail="Update produced no chunks")
            server._set_kb_pipeline_stage("activating", message="Activating updated text", filename=save_path.name)
            if scope_tid is None:
                active_collection = server._sync_live_retrieval_collection(tenant_id=server.require_request_tenant(user))
            else:
                server.get_tenant_rag(scope_tid).vs = None
                active_collection = server.tenant_collection_name(scope_tid)
            server._register_active_source(str(metadata.get("normalized_filename") or save_path.name))
            await server.invalidate_all_caches(
                action="update",
                filename=save_path.name,
                chunks_added=chunks,
                chunks_deleted=int(delete_report.get("deleted_count") or 0),
                triggered_by="admin",
                tenant_id=server.require_request_tenant(user),
            )
            server._set_kb_pipeline_state("ready", message="Text file updated and active", filename=save_path.name)
            return {
                "status": "updated",
                "filename": save_path.name,
                "chunks_indexed": chunks,
                "delete_verification": delete_report,
                "active_collection": active_collection,
                "ready_state": dict(server._kb_pipeline_state),
            }
        except HTTPException:
            raise
        except Exception as e:
            server.logger.exception("rag_update_asset_file failed for %s: %s", save_path.name, e)
            server._set_kb_pipeline_state("failed", message=f"Update failed: {e}", filename=save_path.name)
            raise HTTPException(status_code=500, detail=f"Failed to update file: {str(e)}")

    return router
