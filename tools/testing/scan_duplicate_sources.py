"""Scan Chroma collections for duplicate source identities.

Default mode is read-only. The report groups chunks by canonicalized filename
and highlights cases where the same logical document appears under multiple
stored filenames, source_doc_id values, or source labels.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.knowledge_base import (  # noqa: E402
    canonical_source_doc_id,
    client,
    normalize_uploaded_filename,
    original_filename_from_stored,
)


def _collection_objects():
    collections = client.list_collections()
    for item in collections:
        if isinstance(item, str):
            yield client.get_collection(item)
        else:
            yield item


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _derive_normalized(metadata: dict[str, Any], chunk_id: str) -> str:
    for key in ("normalized_filename", "original_filename", "stored_filename", "filename", "source_filename", "source_name"):
        value = _clean(metadata.get(key))
        if value:
            return normalize_uploaded_filename(original_filename_from_stored(Path(value).name))

    source = _clean(metadata.get("source"))
    if source and not source.startswith("doc_"):
        return normalize_uploaded_filename(original_filename_from_stored(Path(source).name))

    token = chunk_id
    if "_chunk_" in token:
        token = token.split("_chunk_", 1)[0]
    if token.startswith("upload_"):
        token = token[len("upload_") :]
    return normalize_uploaded_filename(original_filename_from_stored(Path(token).name))


def scan_sources() -> dict[str, Any]:
    groups: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "chunks": 0,
            "collections": set(),
            "source_doc_ids": set(),
            "sources": set(),
            "stored_filenames": set(),
            "original_filenames": set(),
            "chunk_id_prefixes": set(),
        }
    )

    collection_count = 0
    chunk_count = 0
    for collection in _collection_objects():
        collection_count += 1
        name = getattr(collection, "name", "unknown")
        try:
            raw = collection.get(include=["metadatas"])
        except Exception as exc:
            groups[f"__collection_error__:{name}"]["error"] = str(exc)
            continue

        ids = raw.get("ids") or []
        metadatas = raw.get("metadatas") or []
        for chunk_id, metadata in zip(ids, metadatas):
            metadata = metadata if isinstance(metadata, dict) else {}
            normalized = _derive_normalized(metadata, str(chunk_id))
            if not normalized:
                normalized = "__unknown__"
            group = groups[normalized]
            group["chunks"] += 1
            chunk_count += 1
            group["collections"].add(name)
            for key, target in (
                ("source_doc_id", "source_doc_ids"),
                ("source", "sources"),
                ("stored_filename", "stored_filenames"),
                ("filename", "stored_filenames"),
                ("source_filename", "stored_filenames"),
                ("original_filename", "original_filenames"),
                ("source_name", "original_filenames"),
            ):
                value = _clean(metadata.get(key))
                if value:
                    group[target].add(value)
            prefix = str(chunk_id).split("_chunk_", 1)[0]
            if prefix:
                group["chunk_id_prefixes"].add(prefix)

    normalized_groups: dict[str, Any] = {}
    duplicates: dict[str, Any] = {}
    for normalized, group in groups.items():
        serializable = {
            key: sorted(value) if isinstance(value, set) else value
            for key, value in group.items()
        }
        if normalized and normalized not in ("__unknown__",) and not normalized.startswith("__collection_error__"):
            serializable["expected_source_doc_id"] = canonical_source_doc_id(normalized)
        normalized_groups[normalized] = serializable

        has_duplicate_identity = (
            len(serializable.get("source_doc_ids", [])) > 1
            or len(serializable.get("stored_filenames", [])) > 1
            or len(serializable.get("chunk_id_prefixes", [])) > 1
        )
        if has_duplicate_identity:
            duplicates[normalized] = serializable

    return {
        "collection_count": collection_count,
        "chunk_count": chunk_count,
        "group_count": len(normalized_groups),
        "duplicate_group_count": len(duplicates),
        "duplicates": duplicates,
        "groups": normalized_groups,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan Chroma source metadata for duplicate document identities.")
    parser.add_argument("--json", action="store_true", help="Emit full JSON report.")
    parser.add_argument("--fix", action="store_true", help="Reserved; no writes are performed by this tool.")
    args = parser.parse_args()

    if args.fix:
        print("--fix is intentionally disabled; this scanner is read-only.", file=sys.stderr)
        return 2

    report = scan_sources()
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if report["duplicate_group_count"] == 0 else 1

    print(f"collections={report['collection_count']} chunks={report['chunk_count']} groups={report['group_count']} duplicates={report['duplicate_group_count']}")
    if report["duplicate_group_count"] == 0:
        print("No duplicate source identities detected.")
        return 0

    for normalized, group in report["duplicates"].items():
        print(f"\n[DUPLICATE] normalized_filename={normalized}")
        print(f"  expected_source_doc_id={group.get('expected_source_doc_id', '')}")
        print(f"  chunks={group.get('chunks')} collections={group.get('collections')}")
        print(f"  source_doc_ids={group.get('source_doc_ids')}")
        print(f"  sources={group.get('sources')}")
        print(f"  stored_filenames={group.get('stored_filenames')}")
        print(f"  chunk_id_prefixes={group.get('chunk_id_prefixes')}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())