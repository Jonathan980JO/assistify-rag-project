#!/usr/bin/env python3
"""Verify knowledge-base indexing and live retrieval against ChromaDB."""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _print_header(title: str) -> None:
    print(f"\n=== {title} ===")


def _safe_preview(text: str, limit: int = 80) -> str:
    raw = str(text or "")[:limit].replace("\n", " ")
    return raw.encode("ascii", "replace").decode("ascii")


def main() -> int:
    ok = True
    print(f"Project root: {REPO_ROOT}")

    try:
        from config import ASSETS_DIR
        from backend.knowledge_base import (
            find_orphan_asset_files,
            get_or_create_collection,
            indexed_source_keys_for_collection,
            list_uploaded_files,
        )
    except Exception as exc:
        print(f"FAIL: import error ({exc})")
        return 1

    chroma_path = REPO_ROOT / "backend" / "chroma_db_v3"
    _print_header("Chroma collections")
    if not chroma_path.is_dir():
        print("FAIL: chroma_db_v3 missing")
        return 1
    try:
        import chromadb

        client = chromadb.PersistentClient(path=str(chroma_path))
        names = client.list_collections()
        for item in names:
            name = item if isinstance(item, str) else getattr(item, "name", str(item))
            col = client.get_collection(name)
            print(f"  {name!r}: {col.count()} chunks")
    except Exception as exc:
        print(f"WARN: chroma listing failed ({exc})")
        ok = False

    _print_header("Active indexing collection")
    collection = get_or_create_collection(allow_empty=True)
    if not collection:
        print("FAIL: no active collection")
        return 1
    active_name = getattr(collection, "name", "<unknown>")
    active_count = collection.count()
    print(f"  collection: {active_name!r}")
    print(f"  chunks: {active_count}")
    if active_count < 50:
        print("  WARN: chunk count is very low for large PDFs (expect hundreds+)")

    _print_header("Chunks by source (indexed files)")
    indexed_files = list_uploaded_files()
    ibm_chunks = 0
    psych_chunks = 0
    if not indexed_files:
        print("  (none)")
    else:
        for entry in indexed_files:
            fname_l = str(entry.get("filename") or "").lower()
            chunks_n = int(entry.get("chunks") or 0)
            print(f"  {entry.get('filename')}: {chunks_n} chunks (doc_id={entry.get('doc_id')})")
            if "ibm" in fname_l and "attrition" in fname_l:
                ibm_chunks = chunks_n
            elif "psychology" in fname_l:
                psych_chunks = chunks_n

    IBM_CHUNK_FLOOR = 40
    PSYCH_CHUNK_FLOOR = 300
    if ibm_chunks and ibm_chunks < IBM_CHUNK_FLOOR:
        ok = False
        print(f"  FAIL: IBM HR PDF has {ibm_chunks} chunks (need >= {IBM_CHUNK_FLOOR}) — reindex after chunking fix")
    elif ibm_chunks:
        print(f"  OK: IBM HR chunk count {ibm_chunks} >= {IBM_CHUNK_FLOOR}")
    if psych_chunks and psych_chunks < PSYCH_CHUNK_FLOOR:
        ok = False
        print(f"  FAIL: Psychology PDF has {psych_chunks} chunks (need >= {PSYCH_CHUNK_FLOOR})")
    elif psych_chunks:
        print(f"  OK: Psychology chunk count {psych_chunks} >= {PSYCH_CHUNK_FLOOR}")

    _print_header("On-disk assets vs index (orphan detection)")
    assets_dir = Path(ASSETS_DIR)
    disk_files = sorted(
        p.name
        for p in assets_dir.iterdir()
        if p.is_file() and p.suffix.lower() in {".pdf", ".txt", ".md"}
    ) if assets_dir.is_dir() else []
    print(f"  disk files: {len(disk_files)}")
    orphans = find_orphan_asset_files(assets_dir)
    if orphans:
        ok = False
        print(f"  ORPHAN assets (on disk, 0 indexed chunks): {len(orphans)}")
        for name in orphans:
            print(f"    - {name}")
    else:
        print("  no orphan assets")

    indexed_keys = indexed_source_keys_for_collection(collection)
    print(f"  indexed source keys: {len(indexed_keys)}")

    _print_header("Live retrieval probes")
    try:
        from backend.pdf_ingestion_rag import VectorStore

        db_path = str(chroma_path)
        vs = VectorStore(persist_directory=db_path, collection_name=None)
        retrieval_name = getattr(getattr(vs, "collection", None), "name", "<none>")
        print(f"  VectorStore collection: {retrieval_name!r} (count={vs.collection.count()})")
        if retrieval_name != active_name:
            print(f"  WARN: indexing collection {active_name!r} != retrieval {retrieval_name!r}")
            ok = False

        metric_probes = (
            ("psychology", None),
            ("theory of mind", None),
            ("employee attrition", "ibm"),
            ("attrition rate 16.12 Sales department", "ibm"),
            ("ROC-AUC logistic regression 0.7272", "ibm"),
            ("Plato three parts of the soul rational", "psych"),
            ("medulla oblongata cardio inhibitory vasomotor", "psych"),
        )
        for query, expect_source in metric_probes:
            hits = vs.search(
                query,
                top_k=8,
                distance_threshold=1.2,
                return_dicts=True,
                enable_rerank=False,
            )
            print(f"  query {query!r}: {len(hits or [])} hit(s)")
            for i, hit in enumerate((hits or [])[:2], 1):
                meta = (hit or {}).get("metadata") or {}
                src = meta.get("original_filename") or meta.get("filename") or meta.get("source") or "?"
                preview = _safe_preview((hit or {}).get("text") or "")
                score = (hit or {}).get("score") or (hit or {}).get("similarity")
                print(f"    #{i} score={score} source={src!r} preview={preview!r}...")
            if not hits:
                ok = False
                print(f"    FAIL: no hits for probe {query!r}")
            elif expect_source == "ibm":
                src_parts: list[str] = []
                for h in (hits or [])[:3]:
                    meta = (h or {}).get("metadata") if isinstance(h, dict) else {}
                    if not isinstance(meta, dict):
                        meta = {}
                    for k in ("original_filename", "filename", "source", "normalized_filename"):
                        src_parts.append(str(meta.get(k) or ""))
                src_blob = " ".join(src_parts).lower()
                if "ibm" not in src_blob and "attrition" not in src_blob and "crisp" not in src_blob:
                    ok = False
                    print(f"    FAIL: IBM probe {query!r} did not retrieve IBM HR source")
            elif expect_source == "psych":
                src_parts = []
                for h in (hits or [])[:3]:
                    meta = (h or {}).get("metadata") if isinstance(h, dict) else {}
                    if not isinstance(meta, dict):
                        meta = {}
                    for k in ("original_filename", "filename", "source", "normalized_filename"):
                        src_parts.append(str(meta.get(k) or ""))
                src_blob = " ".join(src_parts).lower()
                if "psychology" not in src_blob:
                    ok = False
                    print(f"    FAIL: Psychology probe {query!r} did not retrieve Psychology source")
    except Exception as exc:
        print(f"  FAIL: live probe error ({exc})")
        ok = False

    _print_header("KB pipeline status (RAG HTTP)")
    try:
        import urllib.request
        import json

        req = urllib.request.urlopen("http://127.0.0.1:7000/kb_status", timeout=3)
        data = json.loads(req.read().decode("utf-8"))
        print(f"  state/stage: {data.get('state')}/{data.get('stage')}")
        print(f"  message: {data.get('message')}")
        print(f"  active_sources: {data.get('active_sources')}")
        if data.get("orphan_files"):
            print(f"  orphan_files: {data.get('orphan_files')}")
    except Exception as exc:
        print(f"  (RAG server not reachable: {exc})")

    _print_header("Result")
    if ok:
        print("PASS: knowledge base looks healthy")
        return 0
    print("FAIL: knowledge base has indexing or retrieval issues — run Reindex All in admin KB")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
