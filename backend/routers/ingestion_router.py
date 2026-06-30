"""Document ingestion routes for the RAG backend.

Extracted from ``assistify_rag_server.py`` during the Phase 8E refactor.

The upload/reindex handlers orchestrate a large amount of live server state
(KB pipeline-state machine, collection mutation lock, per-tenant assets dirs,
background indexing tasks, knowledge-base helpers). To keep behavior
byte-identical and avoid an import cycle, the router is built by a factory that
receives the live server module and reads attributes from it at request time.
Paths, methods, and response bodies are unchanged.
"""
import asyncio
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile


def build_ingestion_router(server) -> APIRouter:
    """Build the ingestion router bound to the live server module."""
    router = APIRouter()

    @router.post("/upload_rag")
    async def upload_rag(request: Request, file: UploadFile = File(...), user=Depends(server.require_tenant_staff())):
        server.verify_csrf(request)
        server._maybe_recover_stale_kb_pipeline()

        # Scope this upload to the admin's business so documents are indexed into
        # the tenant's own collection and stored under its own assets directory.
        tenant_id = server.require_request_tenant(user)
        server._request_tenant_id.set(tenant_id)

        if not server._check_rate_limit(f"upload:{tenant_id}", limit=10, window=60):
            raise HTTPException(status_code=429, detail="Too many upload requests. Please wait before uploading again.")

        upload_id = uuid.uuid4().hex[:8]
        filename = f"{upload_id}_{Path(file.filename or 'upload').name}"
        original_filename = Path(file.filename or "upload").name
        source_metadata = server.build_canonical_source_metadata(
            original_filename=original_filename,
            stored_filename=filename,
            upload_id=upload_id,
            document_version=upload_id,
        )
        source_doc_id = str(source_metadata.get("source_doc_id") or "")
        normalized_filename = str(source_metadata.get("normalized_filename") or server.normalize_uploaded_filename(original_filename))
        file_ext = filename.split('.')[-1].lower()
        if file_ext not in ["pdf", "txt"]:
            return {"message": "Unsupported file type. Use PDF or TXT."}

        # ---- Non-default tenant: isolated ingestion into the tenant collection ----
        if int(tenant_id) != int(server.DEFAULT_TENANT_ID):
            server._set_kb_pipeline_stage("uploading", message="Upload received; indexing into business knowledge base", filename=filename)
            server.clear_all_conversation_history()
            tenant_dir = server.tenant_assets_dir(tenant_id)
            save_path = tenant_dir / filename
            content = await file.read()
            file_size_mb = len(content) / (1024 * 1024)
            save_path.write_bytes(content)
            server.logger.info("[TENANT UPLOAD] tenant=%s saved asset %s (%.2fMB)", tenant_id, save_path, file_size_mb)
            if filename in server._pdf_indexing_tasks and not server._pdf_indexing_tasks[filename].done():
                server.logger.info("upload_rag duplicate background task suppressed | filename=%s", filename)
            else:
                _bg_task = asyncio.create_task(
                    server._finalize_tenant_pdf_upload_background(
                        tenant_id=tenant_id,
                        filename=filename,
                        original_filename=original_filename,
                        file_ext=file_ext,
                        save_path=save_path,
                        source_metadata=source_metadata,
                    )
                )
                server._pdf_indexing_tasks[filename] = _bg_task
            return {
                "status": "processing",
                "message": "File received. Indexing into your business knowledge base.",
                "filename": filename,
                "original_filename": original_filename,
                "source_doc_id": source_doc_id,
                "normalized_filename": normalized_filename,
                "file_size_mb": file_size_mb,
                "tenant_id": int(tenant_id),
                "ready_state": dict(server._kb_pipeline_state),
            }

        server._set_kb_pipeline_stage("uploading", message="Upload received; extracting and indexing document", filename=filename)
        # Hard-reset all in-memory conversation state immediately so that no old
        # document content can leak into follow-up queries during indexing.
        server.clear_all_conversation_history()
        server.logger.info("[KB HOT-SWAP] conversation + follow-up state cleared (pre-indexing) for filename=%s", filename)

        deleted_for_overwrite = 0
        removed_assets = []
        dedup_deleted = 0
        dedup_removed_assets = []

        try:
            async with server._collection_mutation():
                delete_report = server.delete_documents_by_source_identity(
                    source_doc_id=source_doc_id,
                    original_filename=original_filename,
                    stored_filename=filename,
                    normalized_filename=normalized_filename,
                    upload_id=upload_id,
                    document_version=upload_id,
                    doc_prefix=source_doc_id,
                    extra_keys=[original_filename, filename],
                )
                dedup_deleted += int(delete_report.get("deleted_count") or 0)
            target_norm = server._normalize_source_label(normalized_filename or original_filename)
            existing_files = [f.get("filename") for f in server.list_uploaded_files() if f.get("filename")]
            for existing in existing_files:
                if server._normalize_source_label(existing) != target_norm:
                    continue
                asset_path = server.ASSETS_DIR / existing
                if asset_path.exists() and asset_path.is_file():
                    try:
                        asset_path.unlink()
                        dedup_removed_assets.append(existing)
                    except Exception as dedup_remove_err:
                        server.logger.warning(f"Dedup mode: failed removing old asset {existing}: {dedup_remove_err}")
                current_sources = server._get_active_sources()
                current_sources.discard(server._normalize_source_label(existing))
                server._set_active_sources(sorted(current_sources), mode=server._active_doc_registry.get("mode", server.RAG_DOC_MODE))
        except Exception as dedup_err:
            server.logger.warning(f"Upload dedup pre-clean skipped for {original_filename}: {dedup_err}")

        # BLUE/GREEN INDEXING: Generate a fresh collection name to avoid ChromaDB caching bugs
        # and allow zero-downtime updates in single-doc mode.
        # We do NOT delete the old collection yet; we just prepare a new target.
        _target_collection_name = ""
        _old_single_mode_collection = ""

        if server._active_doc_registry.get("mode", server.RAG_DOC_MODE) == "single":
            import time as _time
            _target_collection_name = f"support_docs_v3_{int(_time.time())}"

            # Save the name of the currently active collection so we can delete it later
            _old_kb_col = server.get_or_create_collection(allow_empty=True)
            if _old_kb_col:
                _old_single_mode_collection = getattr(_old_kb_col, "name", "")

            server.logger.info("Single-mode: preparing new blue/green collection '%s'. Old was '%s'", _target_collection_name, _old_single_mode_collection)
            for old_file in server.ASSETS_DIR.iterdir():
                if not old_file.is_file():
                    continue
                if old_file.suffix.lower() not in {".pdf", ".txt"}:
                    continue
                try:
                    old_file.unlink()
                    removed_assets.append(old_file.name)
                except Exception as remove_err:
                    server.logger.warning(f"Overwrite mode: failed removing old asset {old_file.name}: {remove_err}")
            server._set_active_sources([], mode="single")

        save_path = server.ASSETS_DIR / filename
        content = await file.read()
        file_size_mb = len(content) / (1024 * 1024)
        if file_size_mb > 10:
            server.logger.warning(f"Large file upload: {filename} ({file_size_mb:.1f}MB) - processing may take time")

        server._mark_upload_pipeline_owned(filename, original_filename, normalized_filename, source_doc_id, seconds=600.0)
        save_path.write_bytes(content)
        server.logger.info(f"✓ Received file: {filename} ({file_size_mb:.1f}MB)")
        server._record_kb_stage("file_saved")
        # Watchdog fires created+modified for this write; suppress immediate watcher reindex.
        server._mark_assets_recently_indexed(filename, seconds=15.0)

        # ---- ASYNC HOT-SWAP DISPATCH -------------------------------------------
        # Refuse to schedule a duplicate background task for the same filename.
        if filename in server._pdf_indexing_tasks and not server._pdf_indexing_tasks[filename].done():
            server.logger.info("upload_rag duplicate background task suppressed | filename=%s", filename)
        else:
            _bg_task = asyncio.create_task(
                server._finalize_pdf_upload_background(
                    filename=filename,
                    original_filename=original_filename,
                    file_ext=file_ext,
                    save_path=save_path,
                    file_size_mb=file_size_mb,
                    target_collection_name=_target_collection_name,
                    old_single_mode_collection=_old_single_mode_collection,
                    source_metadata=source_metadata,
                )
            )
            server._pdf_indexing_tasks[filename] = _bg_task

        # Return immediately so the client UI is unblocked. The actual indexing
        # progress is observable via /kb_status (which reads _kb_pipeline_state)
        # and via the /ws "System is loading the document. Please wait..." gate.
        return {
            "status": "processing",
            "message": "File received. Indexing in background.",
            "filename": filename,
            "original_filename": original_filename,
            "source_doc_id": source_doc_id,
            "normalized_filename": normalized_filename,
            "file_size_mb": file_size_mb,
            "doc_mode": server._active_doc_registry.get("mode", server.RAG_DOC_MODE),
            "deleted_for_overwrite": deleted_for_overwrite,
            "removed_assets": removed_assets,
            "dedup_deleted": dedup_deleted,
            "dedup_removed_assets": dedup_removed_assets,
            "ready_state": dict(server._kb_pipeline_state),
        }

    @router.post("/rag/reindex-file")
    async def rag_reindex_file(filename: str, request: Request, user=Depends(server.require_tenant_staff())):
        server.verify_csrf(request)
        """Reindex an uploaded file by filename (uploads are saved to assets dir).

        Clears all existing chunks associated with this filename (including any
        orphans from a previous broken run), then re-indexes fresh from disk.
        """
        if not filename:
            raise HTTPException(status_code=400, detail="filename is required")
        scope_tid = server._kb_admin_scope_tenant(user)
        req_assets_dir = server.ASSETS_DIR if scope_tid is None else server.tenant_assets_dir(scope_tid)
        save_path = req_assets_dir / filename
        if not save_path.exists():
            raise HTTPException(status_code=404, detail="file not found")

        try:
            result = await asyncio.to_thread(
                server._reindex_asset_sync,
                save_path,
                scope_tid,
                upload_id="manual_reindex",
                ingestion_owner="rag_server_reindex",
            )
            chunks = int(result.get("chunks") or 0)
            deleted = int(result.get("deleted_old") or 0)
            delete_report = result.get("delete_verification") or {}
            if chunks:
                server._set_kb_pipeline_stage("activating", message="Activating live retrieval", filename=filename)
                if scope_tid is None:
                    active_collection = server._sync_live_retrieval_collection()
                    server._rebuild_active_sources_from_collection()
                else:
                    server.get_tenant_rag(scope_tid).vs = None
                    active_collection = server.tenant_collection_name(scope_tid)
                await server.invalidate_all_caches(action="reindex", filename=filename,
                                             chunks_added=chunks, chunks_deleted=deleted,
                                             triggered_by="admin")
                server._set_kb_pipeline_state("ready", message="Reindex complete and active", filename=filename)
                return {"reindexed_chunks": chunks, "deleted_old": deleted, "delete_verification": delete_report, "active_collection": active_collection, "ready_state": dict(server._kb_pipeline_state)}
            server._set_kb_pipeline_state("failed", message="Reindex produced no chunks", filename=filename)
            raise HTTPException(status_code=500, detail="Reindex produced no chunks")
        except HTTPException:
            raise
        except RuntimeError as e:
            server._set_kb_pipeline_state("failed", message=str(e), filename=filename)
            raise HTTPException(status_code=500, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/rag/rebuild-active-sources")
    async def rag_rebuild_active_sources(request: Request, user=Depends(server.require_tenant_staff())):
        server.verify_csrf(request)
        """Rebuild in-memory active_sources from the current Chroma collection."""
        server._rebuild_active_sources_from_collection()
        if server._kb_admin_scope_tenant(user) is None:
            server._sync_live_retrieval_collection()
        return {
            "active_sources": sorted(server._get_active_sources()),
            "mode": server._active_doc_registry.get("mode"),
            "ready_state": dict(server._kb_pipeline_state),
        }

    @router.post("/rag/reindex-all")
    async def rag_reindex_all(request: Request, user=Depends(server.require_tenant_staff())):
        server.verify_csrf(request)
        """Reindex every .txt and .pdf file currently in the ASSETS_DIR.

        This is the recovery operation — it clears ALL existing chunks for each
        file and rebuilds them fresh, fixing any duplicate/orphan chunks that
        accumulated during a previous buggy run.
        """
        scope_tid = server._kb_admin_scope_tenant(user)
        req_assets_dir = server.ASSETS_DIR if scope_tid is None else server.tenant_assets_dir(scope_tid)
        if not req_assets_dir.exists():
            return {"message": "Assets directory not found", "files": []}
        server._set_kb_pipeline_state("processing", message="Reindexing all assets", filename="*")
        results = []
        for p in req_assets_dir.iterdir():
            if not p.is_file():
                continue
            if p.suffix.lower() not in (".txt", ".pdf"):
                continue
            filename = p.name
            try:
                result = await asyncio.to_thread(
                    server._reindex_asset_sync,
                    p,
                    scope_tid,
                    upload_id="manual_reindex_all",
                    ingestion_owner="rag_server_reindex_all",
                )
                results.append({**result, "status": "ok"})
            except Exception as e:
                results.append({"filename": filename, "status": "error", "error": str(e)})
            await asyncio.sleep(0)
        total_added = sum(r.get("chunks", 0) for r in results if r.get("status") == "ok")
        total_deleted = sum(r.get("deleted_old", 0) for r in results if r.get("status") == "ok")
        if scope_tid is None:
            active_collection = server._sync_live_retrieval_collection()
            server._rebuild_active_sources_from_collection()
        else:
            server.get_tenant_rag(scope_tid).vs = None
            active_collection = server.tenant_collection_name(scope_tid)
        await server.invalidate_all_caches(action="reindex_all", filename="*",
                                     chunks_added=total_added, chunks_deleted=total_deleted,
                                     triggered_by="admin")
        server._set_kb_pipeline_state("ready", message="Reindex-all complete and active", filename="*")
        return {"reindexed": len([r for r in results if r.get("status") == "ok"]), "files": results, "active_collection": active_collection, "ready_state": dict(server._kb_pipeline_state)}

    return router
