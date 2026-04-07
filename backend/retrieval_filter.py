"""
Retrieval Filter & Deduplication Layer for Assistify RAG.

This module provides intent-aware filtering and deduplication that runs
AFTER raw retrieval but BEFORE final ranking/selection.  It addresses
the problem of structure queries (unit / section / topics) returning
noisy or repeated chunks.

Design goals:
  - Do NOT break factual queries or out-of-scope rejection
  - Do NOT touch chunking or embeddings
  - Lightweight, safe, and minimal
"""

import re
from typing import List, Dict, Any, Optional, Tuple


# ---------------------------------------------------------------------------
# STEP 1 — Intent Detection
# ---------------------------------------------------------------------------

def detect_query_intent(query: str) -> Dict[str, Any]:
    """Detect the retrieval intent from a user query.

    Returns a dict with:
      - intent: "unit" | "structure" | "general"
      - unit_num: int or None  (e.g. 2 for "Unit 2")
      - chapter_num: int or None
      - is_unit_sections_query: bool
      - is_unit_topics_query: bool
      - is_list_units_query: bool
    """
    q = (query or "").strip().lower()

    # Extract unit / chapter numbers
    unit_match = re.search(r'\bunit\s+(\d+)', q)
    chapter_match = re.search(r'\bchapter\s+(\d+)', q)
    unit_num = int(unit_match.group(1)) if unit_match else None
    chapter_num = int(chapter_match.group(1)) if chapter_match else None

    # Sub-intent flags
    is_unit_sections_query = bool(re.search(r'sections?\s+in\s+unit\s+\d+', q))
    is_unit_topics_query = bool(unit_match) and any(
        k in q for k in ["about", "topics", "covered", "discussed"]
    )
    is_list_units_query = (
        ("list" in q and "unit" in q)
        or ("units in the book" in q)
        or ("units in the document" in q)
        or ("all units" in q)
    )

    # Primary intent
    if "unit" in q:
        intent = "unit"
    elif "chapter" in q:
        intent = "unit"  # treat chapter same as unit for structure queries
    elif any(k in q for k in ["section", "topics", "table of contents", "contents", "list"]):
        intent = "structure"
    else:
        intent = "general"

    return {
        "intent": intent,
        "unit_num": unit_num,
        "chapter_num": chapter_num,
        "is_unit_sections_query": is_unit_sections_query,
        "is_unit_topics_query": is_unit_topics_query,
        "is_list_units_query": is_list_units_query,
    }


# ---------------------------------------------------------------------------
# STEP 2 — Intent-Aware Candidate Filtering
# ---------------------------------------------------------------------------

_JUNK_PATTERNS = re.compile(
    r'\b(further\s+reading|references?|isbn|bibliography|works\s+cited'
    r'|self[-\s]*published|createspace|openstax)\b',
    re.IGNORECASE,
)


def _chunk_text_and_meta_hay(item: dict) -> str:
    """Build a searchable haystack from a chunk's text + metadata."""
    md = (item or {}).get("metadata") or {}
    txt = str((item or {}).get("text") or "")[:1400]
    section = str(md.get("section") or "")
    chapter = str(md.get("chapter") or "")
    title = str(md.get("title") or "")
    unit = str(md.get("unit") or "")
    chunk_role = str(md.get("chunk_role") or "")
    return f"{section}\n{chapter}\n{title}\n{unit}\n{chunk_role}\n{txt}".lower()


def _has_unit_signal(item: dict, unit_num: Optional[int] = None) -> bool:
    """Check if a chunk relates to the requested unit number."""
    hay = _chunk_text_and_meta_hay(item)
    md = (item or {}).get("metadata") or {}
    section = str(md.get("section") or "").lower()
    unit_meta = str(md.get("unit") or "").lower()

    if unit_num is not None:
        target = f"unit {unit_num}"
        # Direct hit in metadata or text
        if target in hay:
            return True
        # Section like "Section 5.2" → belongs to Unit 5
        if re.search(rf'\b{unit_num}\.\d+', section):
            return True
        if re.search(rf'\b{unit_num}\.\d+', hay):
            return True
        return False

    # Generic: any unit reference
    if re.search(r'\bunit\s+\d+', hay):
        return True
    if unit_meta:
        return True
    return False


def _has_structure_signal(item: dict) -> bool:
    """Check if chunk has structural markers (TOC, section headings, etc.)."""
    md = (item or {}).get("metadata") or {}
    hay = _chunk_text_and_meta_hay(item)
    chunk_role = str(md.get("chunk_role") or "").lower().strip()

    if chunk_role in {"toc", "section_heading", "chapter_heading", "chapter_intro"}:
        return True
    if re.search(r'\bunit\s+\d+', hay) or re.search(r'\bchapter\s+\d+', hay):
        return True
    if re.search(r'\b\d+(?:\.\d+){1,3}\b', hay):
        return True
    if any(k in hay for k in ["table of contents", "contents", "introduction", "summary", "key terms"]):
        return True
    return False


def _is_junk_chunk(item: dict) -> bool:
    """Identify obviously noisy/junk chunks for general queries."""
    txt = str((item or {}).get("text") or "")[:900].lower()
    words = txt.split()
    if len(words) < 30 and _JUNK_PATTERNS.search(txt):
        return True
    return False


def filter_candidates_by_intent(
    candidates: List[Dict],
    intent_info: Dict[str, Any],
) -> List[Dict]:
    """Filter candidates based on detected intent.

    For unit queries: keep chunks related to the target unit.
    For structure queries: keep chunks with structural signals.
    For general queries: remove obvious junk/noise.

    Always returns at least the original list if filtering removes everything.
    """
    intent = intent_info.get("intent", "general")
    unit_num = intent_info.get("unit_num")
    chapter_num = intent_info.get("chapter_num")

    if not candidates:
        return candidates

    if intent == "unit":
        # Determine which number to filter by (unit takes precedence)
        target_num = unit_num or chapter_num
        if target_num is not None:
            # Keep chunks related to the specific unit
            filtered = [c for c in candidates if _has_unit_signal(c, target_num)]
            if filtered:
                return filtered
            # Fallback: keep anything with structure signal
            struct = [c for c in candidates if _has_structure_signal(c)]
            if struct:
                return struct
        else:
            # "unit" mentioned but no number → list-all-units query
            # Keep anything with unit/chapter/structure signals
            filtered = [c for c in candidates if _has_unit_signal(c) or _has_structure_signal(c)]
            if filtered:
                return filtered

    elif intent == "structure":
        # Keep chunks with structural signals
        filtered = [c for c in candidates if _has_structure_signal(c)]
        if filtered:
            return filtered

    else:
        # General: remove repeated junk but don't over-filter
        cleaned = [c for c in candidates if not _is_junk_chunk(c)]
        if cleaned:
            return cleaned

    # Safety: never return empty if we had candidates
    return candidates


# ---------------------------------------------------------------------------
# STEP 3 — Deduplication
# ---------------------------------------------------------------------------

def _dedup_key(item: dict) -> str:
    """Generate a deduplication key from section + page + text prefix."""
    md = (item or {}).get("metadata") or {}
    section = str(md.get("section") or "").strip().lower()
    page = str(md.get("page") or "").strip()
    txt = str((item or {}).get("text") or "").strip()[:200].lower()
    # Normalize whitespace in text prefix
    txt_norm = re.sub(r'\s+', ' ', txt)
    return f"{section}|{page}|{txt_norm}"


def deduplicate_chunks(candidates: List[Dict]) -> List[Dict]:
    """Remove duplicate chunks based on section + page + text prefix.

    Keeps the first (highest-scored) occurrence of each unique chunk.
    This stops the "Section 5.7.2 spam" problem.
    """
    if not candidates:
        return candidates

    seen_keys = set()
    # Also track section repetition
    section_counts: Dict[str, int] = {}
    MAX_SAME_SECTION = 2  # Allow at most 2 chunks from same section

    deduped = []
    for item in candidates:
        key = _dedup_key(item)

        # Skip exact duplicates
        if key in seen_keys:
            continue
        seen_keys.add(key)

        # Limit per-section repetition
        md = (item or {}).get("metadata") or {}
        section = str(md.get("section") or "").strip().lower()
        if section:
            count = section_counts.get(section, 0)
            if count >= MAX_SAME_SECTION:
                continue
            section_counts[section] = count + 1

        deduped.append(item)

    return deduped


# ---------------------------------------------------------------------------
# STEP 4 — Unified Pipeline: Filter → Dedup → Rank → Select
# ---------------------------------------------------------------------------

def apply_retrieval_filters(
    candidates: List[Dict],
    query: str,
    top_k: int = 5,
) -> List[Dict]:
    """Main entry point: apply intent filtering + dedup before final selection.

    Call this AFTER raw retrieval returns candidates, BEFORE taking top_k.

    Pipeline:
      1. Detect intent from query
      2. Filter candidates by intent
      3. Deduplicate
      4. Sort by similarity/score (descending)
      5. Take top_k

    Returns the filtered, deduped, ranked list (up to top_k items).
    """
    if not candidates:
        return candidates

    # Step 1: Detect intent
    intent_info = detect_query_intent(query)

    # Step 2: Filter by intent
    filtered = filter_candidates_by_intent(candidates, intent_info)

    # Step 3: Deduplicate
    deduped = deduplicate_chunks(filtered)

    # Step 4: Sort by similarity (descending)
    def _sort_key(item: dict) -> float:
        return float(
            item.get("similarity", item.get("score", 0.0)) or 0.0
        )

    ranked = sorted(deduped, key=_sort_key, reverse=True)

    # Step 5: Take top_k
    return ranked[:max(1, top_k)]
