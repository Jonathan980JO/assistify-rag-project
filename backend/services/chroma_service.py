"""Live retrieval (Chroma) management for the RAG backend.

Extracted verbatim from ``assistify_rag_server.py`` during the Phase 8G
refactor. Owns the per-tenant retrieval managers and the critical
upload->query collection handoff. This also absorbs the tenant-RAG cache that
Phase 8B deferred (``get_tenant_rag`` / ``_sync_live_retrieval_collection``).

Behavior-preserving notes:
- ``live_rag`` is a module-level singleton; the server re-imports it so every
  reference (and every mutation of ``live_rag.vs``) targets the same object.
- Heavy dependencies (``VectorStore``) are loaded lazily on first search, so
  importing this module stays cheap.
- This module never imports ``assistify_rag_server`` (avoids an import cycle).
"""
import os
import logging
from threading import RLock
from typing import Optional

from backend.pdf_ingestion_rag import VectorStore
from backend.knowledge_base import CHROMA_DB_PATH
from backend.config_head import DEFAULT_TENANT_ID
from backend.core.tenant_context import current_tenant_id
from config import tenant_collection_name

logger = logging.getLogger("Assistify")


class LiveRAGManager:
    def __init__(self, tenant_id=None):
        # Lazy initialization: defer heavy VectorStore / embedding model loading
        # until the first search call. This keeps module import fast and
        # avoids pulling large models into memory when not needed (e.g., tests).
        self._init_args = {}
        db_path = str(CHROMA_DB_PATH)
        self._init_args["persist_directory"] = db_path
        self.vs: Optional[VectorStore] = None
        # Resolve the tenant this manager serves. The default tenant keeps the
        # historical auto-resolution behavior (no explicit collection name) so
        # existing single-tenant data continues to work unchanged. Other tenants
        # bind to their own namespaced collection, which VectorStore enforces in
        # its per-tenant "explicit" resolution branch — guaranteeing a query for
        # one business can never read another business's vectors.
        try:
            self.tenant_id = DEFAULT_TENANT_ID if tenant_id is None else int(tenant_id)
        except (TypeError, ValueError):
            self.tenant_id = DEFAULT_TENANT_ID
        if self.tenant_id == DEFAULT_TENANT_ID:
            self.collection_name = "support_docs_v3_latest"
            # None => preserve legacy auto-resolution inside VectorStore.
            self._vs_collection_name = None
        else:
            try:
                self.collection_name = tenant_collection_name(self.tenant_id)
            except Exception:
                self.collection_name = f"t{self.tenant_id}_support_docs_v3_latest"
            self._vs_collection_name = self.collection_name
        # The ASSISTIFY_COLLECTION_NAME override only applies to the default
        # tenant; honoring it for every tenant would break isolation.
        if self.tenant_id == DEFAULT_TENANT_ID:
            self._preferred_collection = os.environ.get("ASSISTIFY_COLLECTION_NAME", "").strip() or self.collection_name
        else:
            self._preferred_collection = self.collection_name

    def search(self, query: str, top_k: int = 5, distance_threshold: float = 1.0, return_dicts: bool = False, enable_rerank: bool = True):
        """High-level search orchestration."""
        logger.debug("[LiveRAGManager] tenant=%s Query: %r", self.tenant_id, query)

        # Lazy-create VectorStore on first use (safe, idempotent)
        if self.vs is None:
            try:
                self.vs = VectorStore(
                    persist_directory=str(self._init_args.get("persist_directory") or ""),
                    collection_name=self._vs_collection_name,
                )
                # If a preferred collection is set but empty, VectorStore logic will
                # handle fallback; keep behavior consistent with previous design.
            except Exception as e:
                logger.warning(f"LiveRAGManager lazy init of VectorStore failed: {e}")

        # Basic intent detection for logging
        q_lower = (query or "").lower()
        if "unit" in q_lower or "chapter" in q_lower:
            intent = "structural"
        elif any(k in q_lower for k in ["list", "section", "table of contents"]):
            intent = "structure"
        else:
            intent = "general"

        logger.info(f"[LiveRAGManager] Detected intent: {intent}")

        # Delegate to VectorStore for optimized retrieval and reranking
        results = None
        if self.vs is None:
            logger.warning("LiveRAGManager.vs is not available; returning empty results")
            results = []
        else:
            results = self.vs.search(
                query=query,
                top_k=top_k,
                distance_threshold=distance_threshold,
                return_dicts=return_dicts,
                enable_rerank=enable_rerank,
            )

        return results

    # --- DEPRECATED OLD SEARCH HELPERS REMOVED ---


# Inject the new pipeline wrapper. `live_rag` serves the default tenant and
# preserves the historical single-tenant retrieval behavior exactly.
live_rag = LiveRAGManager()

# Per-tenant retrieval managers. Each non-default tenant gets its own
# LiveRAGManager (and therefore its own ChromaDB collection + cached VectorStore),
# so retrieval is physically isolated per business.
_tenant_rag_managers: dict = {}
_tenant_rag_lock = RLock()


def get_tenant_rag(tenant_id=None) -> "LiveRAGManager":
    """Return the retrieval manager bound to a tenant's knowledge base.

    The default tenant reuses the legacy `live_rag` singleton; every other
    tenant gets a lazily-created, cached manager pinned to its own collection.
    """
    try:
        tid = int(tenant_id) if tenant_id is not None else DEFAULT_TENANT_ID
    except (TypeError, ValueError):
        tid = DEFAULT_TENANT_ID
    if tid <= 0:
        tid = DEFAULT_TENANT_ID
    if tid == DEFAULT_TENANT_ID:
        return live_rag
    with _tenant_rag_lock:
        mgr = _tenant_rag_managers.get(tid)
        if mgr is None:
            mgr = LiveRAGManager(tenant_id=tid)
            _tenant_rag_managers[tid] = mgr
        return mgr


def _active_rag() -> "LiveRAGManager":
    """Retrieval manager for the tenant bound to the current request context."""
    try:
        return get_tenant_rag(current_tenant_id())
    except Exception:
        return live_rag


def _sync_live_retrieval_collection(target_collection_name: str | None = None, tenant_id: int | None = None) -> str:
    """Ensure live retrieval is pointed at the same collection used by indexing.

    This is the CRITICAL handoff point between upload/indexing and live queries.
    After every upload, this function MUST be called to guarantee that live_rag
    is querying the same collection that just received the new chunks.

    Fixes the 'Not found in the document' bug that occurred when:
    - The indexing collection and retrieval collection fell out of sync
    - ChromaDB returned a stale collection object after deletions
    """
    from backend.knowledge_base import _collection_owned_by_tenant, get_or_create_collection

    tid = int(tenant_id if tenant_id is not None else current_tenant_id())
    scope_tid = None if int(tid) == int(DEFAULT_TENANT_ID) else int(tid)
    kb_collection = get_or_create_collection(allow_empty=True, tenant_id=scope_tid)
    if not kb_collection:
        raise RuntimeError("No KB collection available for live retrieval sync")

    desired = str(target_collection_name or getattr(kb_collection, "name", "") or "").strip()
    if not desired:
        raise RuntimeError("Resolved KB collection has no valid name")

    # Always get a FRESH collection reference from ChromaDB — never reuse
    # cached references which may be stale after delete_all + re-index.
    client = getattr(getattr(live_rag, "vs", None), "client", None)
    if client is None:
        from backend.knowledge_base import client as kb_client
        client = kb_client

    try:
        fresh_collection = client.get_collection(name=desired)
        fresh_count = fresh_collection.count()
    except Exception as e:
        logger.error("Failed to get fresh collection '%s': %s", desired, e)
        raise RuntimeError(f"Collection '{desired}' not found: {e}")

    # If the target collection is empty, scan only collections owned by this tenant.
    if fresh_count == 0:
        logger.warning(
            "Target collection '%s' is empty after sync attempt — scanning tenant-owned alternatives",
            desired,
        )
        try:
            all_collections = client.list_collections()
            collection_names: list[str] = []
            for c in all_collections or []:
                if isinstance(c, str):
                    collection_names.append(c)
                else:
                    name = getattr(c, "name", None)
                    if name:
                        collection_names.append(str(name))
            for c_name in sorted(collection_names, reverse=True):
                if not _collection_owned_by_tenant(c_name, tid):
                    continue
                try:
                    candidate = client.get_collection(name=c_name)
                    if candidate.count() > 0:
                        fresh_collection = candidate
                        fresh_count = candidate.count()
                        desired = c_name
                        logger.info("Fallback: using non-empty collection '%s' (count=%s)", desired, fresh_count)
                        break
                except Exception:
                    continue
        except Exception as scan_err:
            logger.warning("Collection scan failed: %s", scan_err)

    _vs_collection_ref = getattr(getattr(live_rag, "vs", None), "collection", None)
    old_name = str(_vs_collection_ref.name) if _vs_collection_ref is not None else "<none>"
    _live_vs = live_rag.vs
    if _live_vs is not None:
        _live_vs.collection = fresh_collection
    # Invalidate rerank cache when the active collection changes — entries
    # are keyed by collection name + query + candidate-ids, so stale entries
    # would never match anyway, but clearing keeps memory bounded after
    # uploads/deletes/hot-swaps. Safe no-op if helper is unavailable.
    if old_name != desired:
        try:
            from backend.pdf_ingestion_rag import _rerank_cache_clear as _rc_clear
            _rc_clear(reason=f"collection_swap {old_name}->{desired}")
        except Exception as _rc_err:
            logger.warning("[RERANK CACHE] clear-on-swap failed: %s", _rc_err)
    logger.info(
        "Live retrieval collection synced | previous=%s current=%s count=%s",
        old_name, desired, fresh_count,
    )
    return desired
