"""Knowledge-base management routes for the RAG backend.

Extracted from ``assistify_rag_server.py`` during the Phase 8D refactor.

The handlers read live server state (KB pipeline state, active sources, the
live/tenant RAG managers, analytics readers). To keep behavior byte-identical
and avoid an import cycle, the router is built by a factory that receives the
live server module and reads attributes from it at request time. Paths,
methods, and response bodies are unchanged.

Note: ``/debug/runtime-rag`` stays in the server module because it introspects
that module's own source via ``__name__``/``globals()`` and must keep its
module identity.
"""
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse


def _build_retrieve_debug_row(doc: dict, *, rank: int, heading: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build a complete, evidence-only retrieval diagnostic row."""
    md = dict((doc or {}).get("metadata") or {})
    similarity = (doc or {}).get("similarity")
    rerank_score = (doc or {}).get("rerank_score")
    base_score = (doc or {}).get("score")
    effective_score = rerank_score if rerank_score is not None else (similarity if similarity is not None else base_score)
    source = md.get("source") or md.get("source_filename") or md.get("source_doc_id") or md.get("filename")
    filename = md.get("filename") or md.get("normalized_filename") or md.get("stored_filename")
    text = str((doc or {}).get("text") or (doc or {}).get("page_content") or (doc or {}).get("content") or "")
    return {
        "rank": rank,
        "id": (doc or {}).get("id"),
        "score": effective_score,
        "similarity": similarity if similarity is not None else base_score,
        "rerank_score": rerank_score,
        "source": source,
        "filename": filename,
        "page": md.get("page"),
        "section": md.get("section"),
        "chapter": md.get("chapter"),
        "title": md.get("title"),
        "unit": md.get("unit"),
        "chunk_role": md.get("chunk_role"),
        "metadata": md,
        "heading": heading or {},
        "text_preview": text[:600],
    }


def _raw_chroma_debug_candidates(rag: Any, retrieval_query: str, *, top_k: int) -> list[dict[str, Any]]:
    """Return raw Chroma candidates for diagnostics when the normal search path gates everything."""
    try:
        normalized_query = rag._normalize_query_text(retrieval_query)
        query_for_embedding = rag._to_e5_query(normalized_query)
        encoded = rag.embedding_model.encode([query_for_embedding], show_progress_bar=False)[0]
        query_embedding = encoded.tolist() if hasattr(encoded, "tolist") else list(encoded)
        results = rag.collection.query(
            query_embeddings=[query_embedding],
            n_results=max(1, min(int(top_k or 1), 20)),
        )
    except Exception:
        return []

    documents = ((results or {}).get("documents") or [[]])[0]
    metadatas = ((results or {}).get("metadatas") or [[]])[0]
    distances = ((results or {}).get("distances") or [[]])[0]
    ids = ((results or {}).get("ids") or [[]])[0]
    max_i = min(len(documents), len(metadatas), len(distances))
    candidates: list[dict[str, Any]] = []
    for index in range(max_i):
        text = str(documents[index] or "")
        metadata = metadatas[index] if isinstance(metadatas[index], dict) else {}
        distance = float(distances[index])
        similarity = 1.0 - distance
        candidates.append(
            {
                "id": ids[index] if index < len(ids) else f"debug_{index}",
                "text": text,
                "page_content": text,
                "metadata": metadata,
                "distance": distance,
                "similarity": similarity,
                "score": similarity,
            }
        )

    reranker = getattr(rag, "reranker", None)
    if reranker is not None and candidates:
        try:
            scores = reranker.predict([[str(retrieval_query or ""), str(c.get("text") or "")] for c in candidates])
            for index, score in enumerate(scores):
                candidates[index]["rerank_score"] = float(score)
                candidates[index]["score"] = float(score)
            candidates.sort(key=lambda item: float(item.get("score", 0.0) or 0.0), reverse=True)
        except Exception:
            pass
    return candidates[: max(1, min(int(top_k or 1), 20))]


def build_kb_router(server) -> APIRouter:
    """Build the KB management router bound to the live server module."""
    router = APIRouter()

    @router.get("/rag/files")
    def get_rag_files(user=Depends(server.require_tenant_staff())):
        """Return uploaded files indexed in the RAG collection (tenant-scoped)."""
        try:
            from backend.knowledge_base import list_uploaded_files
            files = list_uploaded_files(tenant_id=server._kb_admin_scope_tenant(user))
            return {"files": files}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/rag/debug")
    def rag_debug(user=Depends(server.require_tenant_staff())):
        """Return ALL entries in ChromaDB for debugging — shows ids, filenames, and text previews."""
        try:
            from backend.knowledge_base import get_or_create_collection
            collection = get_or_create_collection(tenant_id=server._kb_admin_scope_tenant(user))
            if not collection:
                return {"count": 0, "entries": []}
            result = collection.get(include=["metadatas", "documents"]) or {}  # type: ignore[call-overload]
            ids = result.get("ids", [])
            metadatas = result.get("metadatas") or []
            documents = result.get("documents") or []
            entries = []
            for i, (doc_id, meta, doc) in enumerate(zip(ids, metadatas, documents)):
                entries.append({
                    "id": doc_id,
                    "filename": meta.get("filename", "") if isinstance(meta, dict) else "",
                    "source": meta.get("source", "") if isinstance(meta, dict) else "",
                    "chunk_index": meta.get("chunk_index", "") if isinstance(meta, dict) else "",
                    "text_preview": (doc or "")[:120],
                })
            return {"count": len(entries), "entries": entries}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/rag/retrieve-debug")
    def rag_retrieve_debug(query: str, top_k: int = 7, tenant_id: int | None = None, user=Depends(server.require_tenant_staff())):
        """Run retrieval only and return chosen chunks with source/page metadata."""
        # Bind to the admin's tenant so the debug view reflects only that business's KB.
        debug_tenant_id = int(tenant_id) if tenant_id is not None else server.require_request_tenant(user)
        server._request_tenant_id.set(debug_tenant_id)
        try:
            from backend.retrieval.routing import (
                _classify_query_family_v2,
                _overview_seed_query,
                _resolve_doc_heading_source,
            )

            query_family_v2 = _classify_query_family_v2(query)
            retrieval_query = _overview_seed_query() if query_family_v2 == "document_summary" else query
            top_k_req = max(1, min(int(top_k or 1), 20))
            rag = server._active_rag()
            docs = rag.search(
                retrieval_query,
                top_k=top_k_req,
                distance_threshold=999.0,
                return_dicts=True,
                enable_rerank=True,
            )
            diagnostic_fallback_used = False
            if not docs:
                docs = _raw_chroma_debug_candidates(rag, retrieval_query, top_k=top_k_req)
                diagnostic_fallback_used = bool(docs)
            server.logger.info("[RERANK ACTIVE]")
            rows = []
            for rank, d in enumerate(docs or [], start=1):
                try:
                    heading = _resolve_doc_heading_source(query, d or {})
                except Exception:
                    heading = {}
                rows.append(_build_retrieve_debug_row(d or {}, rank=rank, heading=heading))
            return {
                "query": query,
                "retrieval_query": retrieval_query,
                "query_family_v2": query_family_v2,
                "diagnostic_fallback_used": diagnostic_fallback_used,
                "tenant_id": debug_tenant_id,
                "doc_mode": server._active_doc_registry.get("mode", server.RAG_DOC_MODE),
                "active_sources": sorted(server._get_active_sources()),
                "count": len(rows),
                "results": rows,
                # Backwards-compatible alias for older test harnesses expecting
                # an `entries` key containing the same per-chunk rows.
                "entries": rows,
            }
        except Exception as e:
            server.logger.warning(f"retrieve-debug failed for query='{query[:80]}': {e}")
            return {
                "query": query,
                "retrieval_query": query,
                "tenant_id": int(tenant_id) if tenant_id is not None else None,
                "doc_mode": server._active_doc_registry.get("mode", server.RAG_DOC_MODE),
                "active_sources": sorted(server._get_active_sources()),
                "count": 0,
                "results": [],
                "entries": [],
                "error": str(e),
            }

    @router.get("/kb_status")
    async def kb_status(user=Depends(server.require_login())):
        """KB pipeline state for admin upload polling (tenant-scoped).

        Returns the lifecycle state (uploading | processing | ready | failed),
        the current filename being processed (if any), per-stage timings, and
        the cumulative upload-to-ready duration. Scoped to the caller's business.
        """
        server._maybe_recover_stale_kb_pipeline()
        tenant_id = server.require_request_tenant(user)
        server._request_tenant_id.set(tenant_id)
        scope_tid = None if int(tenant_id) == int(server.DEFAULT_TENANT_ID) else int(tenant_id)
        assets_dir = server.ASSETS_DIR if scope_tid is None else server.tenant_assets_dir(scope_tid)
        snapshot = dict(server._kb_pipeline_state)
        snapshot["stage_timings"] = dict(server._kb_pipeline_state.get("stage_timings") or {})
        snapshot["active_sources"] = sorted(server._get_active_sources())
        snapshot["doc_mode"] = server._active_doc_registry.get("mode", server.RAG_DOC_MODE)
        snapshot["tenant_id"] = int(tenant_id)
        pipeline_state = str(snapshot.get("state") or "ready").lower()
        if pipeline_state in ("processing", "uploading"):
            return snapshot
        if pipeline_state == "ready":
            snapshot["stage"] = "ready"
            snapshot["percent"] = 100
        try:
            from backend.knowledge_base import find_orphan_asset_files, get_or_create_collection

            kb_col = get_or_create_collection(allow_empty=True, tenant_id=scope_tid)
            snapshot["active_collection"] = getattr(kb_col, "name", None) if kb_col else None
            collection_count = kb_col.count() if kb_col else 0
            snapshot["collection_chunks"] = collection_count
            snapshot["indexed_chunks"] = collection_count
            prev_total = snapshot.get("total_chunks")
            if isinstance(prev_total, int) and prev_total > 0:
                snapshot["total_chunks"] = max(prev_total, collection_count)
            else:
                snapshot["total_chunks"] = collection_count
            if (
                isinstance(snapshot.get("indexed_chunks"), int)
                and isinstance(snapshot.get("total_chunks"), int)
                and snapshot["total_chunks"] > 0
                and snapshot["indexed_chunks"] > snapshot["total_chunks"]
            ):
                snapshot["total_chunks"] = snapshot["indexed_chunks"]
            if int(tenant_id) == int(server.DEFAULT_TENANT_ID):
                retrieval_col = getattr(getattr(server.live_rag, "vs", None), "collection", None)
                snapshot["retrieval_collection"] = getattr(retrieval_col, "name", None) if retrieval_col else None
            else:
                tenant_mgr = server.get_tenant_rag(tenant_id)
                retrieval_col = getattr(getattr(tenant_mgr, "vs", None), "collection", None)
                snapshot["retrieval_collection"] = getattr(retrieval_col, "name", None) if retrieval_col else None
            snapshot["orphan_files"] = find_orphan_asset_files(assets_dir)
        except Exception as status_err:
            snapshot["status_error"] = str(status_err)
        return snapshot

    @router.get("/rag/ready")
    async def rag_ready(user=Depends(server.require_login())):
        ready, reason = server._kb_is_ready_for_queries()
        collection_name = getattr(getattr(server.live_rag, "vs", None), "collection", None)
        collection_name = getattr(collection_name, "name", None)
        collection_count = None
        try:
            _ready_vs = server.live_rag.vs
            _ready_col = getattr(_ready_vs, "collection", None) if _ready_vs is not None else None
            if _ready_col is not None:
                collection_count = int(_ready_col.count() or 0)
        except Exception:
            collection_count = None
        return {
            "ready": ready,
            "reason": reason,
            "state": dict(server._kb_pipeline_state),
            "doc_mode": server._active_doc_registry.get("mode", server.RAG_DOC_MODE),
            "active_sources": sorted(server._get_active_sources()),
            "active_collection": collection_name,
            "active_collection_chunks": collection_count,
        }

    @router.post("/rag/clear-cache")
    async def rag_clear_cache(request: Request, user=Depends(server.require_tenant_staff())):
        server.verify_csrf(request)
        """Manually flush all caches so the next query uses fully fresh KB data.

        Clears:
          - All in-memory conversation histories (prevents stale Q&A reuse)
          - Ollama model KV cache (forces model reload so no cached completions)

        Use this when the LLM keeps returning old/wrong answers after a KB edit.
        """
        await server.invalidate_all_caches(action="clear_cache", filename="*", triggered_by="admin")
        return {
            "status": "ok",
            "message": "All caches cleared — conversations wiped and LLM model cache flushed. Next query will use fresh KB data."
        }

    @router.get("/rag/doc-mode")
    async def rag_get_doc_mode(user=Depends(server.require_tenant_staff())):
        return {
            "mode": server._active_doc_registry.get("mode", server.RAG_DOC_MODE),
            "active_sources": sorted(server._get_active_sources()),
        }

    @router.post("/rag/doc-mode")
    async def rag_set_doc_mode(payload: dict, request: Request, user=Depends(server.require_tenant_staff())):
        server.verify_csrf(request)
        mode = str((payload or {}).get("mode") or "").strip().lower()
        if mode not in {"single", "multi"}:
            raise HTTPException(status_code=400, detail="mode must be 'single' or 'multi'")
        sources = (payload or {}).get("active_sources")
        if isinstance(sources, list):
            server._set_active_sources([str(s) for s in sources], mode=mode)
        else:
            server._set_active_sources(list(server._get_active_sources()), mode=mode)
        return {
            "mode": server._active_doc_registry.get("mode", server.RAG_DOC_MODE),
            "active_sources": sorted(server._get_active_sources()),
        }

    @router.get("/admin/kb-monitor", response_class=HTMLResponse)
    def admin_kb_monitor_page(request: Request, user=Depends(server.require_tenant_staff())):
        """Serve the KB monitoring dashboard HTML page."""
        html_path = Path(server.__file__).parent / "templates" / "admin_kb_monitor.html"
        if not html_path.exists():
            raise HTTPException(status_code=404, detail="KB monitor template not found.")
        return HTMLResponse(content=html_path.read_text(encoding="utf-8"))

    @router.get("/api/kb-stats")
    def api_kb_stats(days: int = 30, tenant_id: int | None = None, user=Depends(server.require_tenant_staff())):
        """Return KB performance and mutation metrics for the monitoring dashboard."""
        stats = server.get_kb_stats(days=days, tenant_id=server.analytics_scope_tenant(user, tenant_id))
        stats["kb_version"] = server._kb_global_version
        stats["active_sessions"] = len(server._active_ws_connections)
        stats["kb_event_subscribers"] = len(server._kb_event_subscribers)
        return stats

    @router.get("/api/kb-events")
    def api_kb_events(limit: int = 100, tenant_id: int | None = None, user=Depends(server.require_tenant_staff())):
        """Return recent KB mutation events for the monitoring dashboard (tenant-scoped)."""
        return {
            "events": server.get_kb_events(limit=limit, tenant_id=server.analytics_scope_tenant(user, tenant_id)),
            "kb_version": server._kb_global_version,
        }

    @router.get("/internal/preflight")
    def preflight_check():
        """System preflight check — verifies strict stability config."""
        checks = server._system_preflight()
        mem = server._get_memory_snapshot()
        checks["memory"] = mem
        checks["sessions_blocked"] = server.memory_guard.sessions_blocked
        checks["consecutive_gpu_growth"] = server.memory_guard.consecutive_gpu_growth
        checks["pipeline_runs"] = server.memory_guard.pipeline_run_count
        return checks

    return router
