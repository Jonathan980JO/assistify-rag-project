"""Regression coverage for Phase 13C active-source filtering."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend import assistify_rag_server as server


def _snapshot_active_registry() -> dict:
    return {
        "mode": server._active_doc_registry.get("mode"),
        "default_active_sources": set(server._active_doc_registry.get("active_sources") or set()),
        "tenant_active_sources": {
            int(tenant_id): set(sources)
            for tenant_id, sources in server._tenant_active_sources.items()
        },
    }


def _restore_active_registry(snapshot: dict) -> None:
    server._active_doc_registry["mode"] = snapshot["mode"]
    server._active_doc_registry["active_sources"] = set(snapshot["default_active_sources"])
    server._tenant_active_sources.clear()
    for tenant_id, sources in snapshot["tenant_active_sources"].items():
        server._tenant_active_sources[int(tenant_id)] = set(sources)


def test_tenant_active_source_filter_uses_current_tenant_registry() -> None:
    snapshot = _snapshot_active_registry()
    try:
        server._tenant_active_sources.clear()
        server._active_doc_registry["mode"] = "multi"
        server._set_active_sources(
            ["doc_2efea6f8654b42ec", "stale_document.pdf"],
            tenant_id=server.DEFAULT_TENANT_ID,
        )

        tenant_id = 2
        retrieved_metadata = {
            "source_doc_id": "doc_e9336e9c82eb08a5",
            "source": "doc_e9336e9c82eb08a5",
            "normalized_filename": "uploaded_document.pdf",
            "stored_filename": "a2448b13_uploaded_document.pdf",
        }
        server._register_active_source_aliases(
            sorted(server._source_aliases_from_metadata(retrieved_metadata)),
            tenant_id=tenant_id,
        )

        retrieved = [{"content": "Tenant 2 evidence", "metadata": retrieved_metadata}]

        with server._TenantScope(tenant_id):
            filtered = server._filter_results_to_active_sources(retrieved)
            active_sources = server._get_active_sources()

        assert filtered == retrieved
        assert "doc_e9336e9c82eb08a5" in active_sources
        assert "doc_2efea6f8654b42ec" not in active_sources

        with server._TenantScope(server.DEFAULT_TENANT_ID):
            assert server._filter_results_to_active_sources(retrieved) == []
    finally:
        _restore_active_registry(snapshot)


def test_single_mode_reupload_replaces_old_tenant_source_aliases() -> None:
    snapshot = _snapshot_active_registry()
    try:
        server._tenant_active_sources.clear()
        server._active_doc_registry["mode"] = "single"
        tenant_id = 2

        old_metadata = {
            "source_doc_id": "doc_old_source",
            "normalized_filename": "old_document.pdf",
        }
        new_metadata = {
            "source_doc_id": "doc_new_source",
            "normalized_filename": "new_document.pdf",
        }

        server._register_active_source_aliases(
            sorted(server._source_aliases_from_metadata(old_metadata)),
            tenant_id=tenant_id,
        )
        server._register_active_source_aliases(
            sorted(server._source_aliases_from_metadata(new_metadata)),
            tenant_id=tenant_id,
        )

        active_sources = server._get_active_sources(tenant_id=tenant_id)

        assert "doc_new_source" in active_sources
        assert "new_document.pdf" in active_sources
        assert "doc_old_source" not in active_sources
        assert "old_document.pdf" not in active_sources
    finally:
        _restore_active_registry(snapshot)


def test_delete_then_reupload_activates_new_tenant_source_aliases() -> None:
    snapshot = _snapshot_active_registry()
    try:
        server._tenant_active_sources.clear()
        server._active_doc_registry["mode"] = "single"
        tenant_id = 2

        server._set_active_sources([], mode="single", tenant_id=tenant_id)
        reuploaded_metadata = {
            "source_doc_id": "doc_reuploaded_source",
            "normalized_filename": "same_filename.pdf",
            "stored_filename": "newupload_same_filename.pdf",
        }
        server._register_active_source_aliases(
            sorted(server._source_aliases_from_metadata(reuploaded_metadata)),
            tenant_id=tenant_id,
        )

        retrieved = [{"content": "Reuploaded evidence", "metadata": reuploaded_metadata}]

        with server._TenantScope(tenant_id):
            assert server._filter_results_to_active_sources(retrieved) == retrieved
            active_sources = server._get_active_sources()

        assert "doc_reuploaded_source" in active_sources
        assert "same_filename.pdf" in active_sources
    finally:
        _restore_active_registry(snapshot)
