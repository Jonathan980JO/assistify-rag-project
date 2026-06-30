"""Pure text/time helper functions for the RAG backend.

Extracted verbatim from ``assistify_rag_server.py`` during the Phase 1 refactor.
No database access, no FastAPI imports, no module-global state.
"""
import re
from datetime import datetime, timezone


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dedup_preserve_order(values: list[str]) -> list[str]:
    seen_values: set[str] = set()
    deduped_values: list[str] = []
    for value in values:
        cleaned_value = re.sub(r"\s+", " ", str(value or "").strip().strip(" .;:-"))
        key = re.sub(r"[^a-z0-9\u0600-\u06FF]+", " ", cleaned_value.lower()).strip()
        if not cleaned_value or not key or key in seen_values:
            continue
        seen_values.add(key)
        deduped_values.append(cleaned_value)
    return deduped_values


def _is_arabic_text(value: str) -> bool:
    return bool(re.search(r"[\u0600-\u06FF]", str(value or "")))
