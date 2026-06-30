"""Ingestion progress wiring for the RAG backend.

Extracted from ``assistify_rag_server.py`` during the Phase 8E refactor. Holds
the ingest progress callback that maps low-level pdf/text ingestion events onto
the server's KB pipeline-state machine.

The pipeline-state machine (``_set_kb_pipeline_stage``) stays in the server
module (it is shared with startup and the websocket gate). It is imported
lazily inside the callback to avoid a load-time import cycle, mirroring the
deferred-import pattern used elsewhere in the decomposition.
"""


def _on_ingest_progress(event: dict, filename: str) -> None:
    from backend.assistify_rag_server import _set_kb_pipeline_stage

    stage = str((event or {}).get("stage") or "").strip().lower()
    if stage == "complete":
        return
    status_stage = "writing" if stage == "writing" else (stage if stage in {"chunking", "embedding"} else "processing")
    indexed = (event or {}).get("indexed")
    total = (event or {}).get("total")
    percent = (event or {}).get("percent")
    message = status_stage
    if total:
        message = f"{status_stage} {indexed or 0}/{total}"
    _set_kb_pipeline_stage(
        status_stage,
        message=message,
        filename=filename,
        indexed=int(indexed) if indexed is not None else None,
        total=int(total) if total is not None else None,
        percent=int(percent) if percent is not None else None,
    )
