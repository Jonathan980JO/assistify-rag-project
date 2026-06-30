"""Lightweight chunk-shape heuristics for RAG retrieval ranking."""
from __future__ import annotations

import re

_COLON_LABEL_VERB_RE = re.compile(
    r"\b(?:is|are|was|were|be|been|being|has|have|had|do|does|did|can|could|should|would|will|"
    r"may|might|must|shall|absorbs?|prevents?|provides?|contains?|includes?|requires?|uses?|used|"
    r"helps?|protects?|reduces?|increases?|allows?|keeps?|maintains?|replaces?|replaced|flows?|"
    r"lubricates?|operates?|works?|functions?|refers\s+to|means|defined\s+as)\b",
    flags=re.IGNORECASE,
)


def _is_colon_led_definition_prose(text: str) -> bool:
    """True for 'Term: full explanation' bullets, not table rows or bare headings."""
    src = str(text or "").strip()
    if not src or ":" not in src:
        return False
    colon_idx = src.find(":")
    if colon_idx < 0 or colon_idx > 100:
        return False
    label = src[:colon_idx].strip()
    after = src[colon_idx + 1 :].strip()
    if not label or not after:
        return False
    if after.count("|") >= 2 or src.count("|") >= 3:
        return False
    if re.match(r"^(?:chapter|section|unit|lesson|part|appendix)\b", label, flags=re.IGNORECASE):
        return False
    if re.match(r"^\d+(?:\.\d+)*$", label):
        return False
    after_words = re.findall(r"[A-Za-z0-9]+(?:'[A-Za-z]+)?", after)
    if len(after_words) > 8:
        return True
    if _COLON_LABEL_VERB_RE.search(after):
        return True
    if "(" in after and len(after_words) >= 5:
        return True
    return False


def _is_colon_led_definition_chunk(text: str) -> bool:
    lines = [ln.strip() for ln in str(text or "").splitlines() if ln.strip()]
    if not lines:
        return False
    colon_def_lines = sum(1 for ln in lines if _is_colon_led_definition_prose(ln))
    if len(lines) == 1:
        return colon_def_lines == 1
    return colon_def_lines >= max(1, len(lines) // 2)


def looks_table_or_heading_like_chunk(text: str) -> bool:
    src = str(text or "")
    if not src.strip():
        return True
    if _is_colon_led_definition_chunk(src):
        return False
    low = src.lower()
    if re.search(r"\b(?:table|fig(?:ure)?|fig\.)\b", low[:1600]):
        return True
    if re.search(r"\b(table\s*\d+|contributors?|classification|contents?|chapter\s+\d+)\b", low[:1400]):
        return True
    if re.search(r"\b\d+\.\s*[A-Z][A-Za-z\s\-]{2,50}\s+[A-Z][a-z]+\s+[A-Z][a-z]+\b", src[:1600]):
        return True
    if re.search(r"\b(figure\s*\d+|fig\.\s*\d+)\b", low[:1400]):
        return True
    concept_person_pairs = re.findall(
        r"(?m)^\s*[A-Z][A-Za-z\s\-]{3,40}\s+[A-Z][a-z]+\s+[A-Z][a-z]+\s*$",
        src[:1400],
    )
    if len(concept_person_pairs) >= 2:
        return True
    lines = [ln.strip() for ln in src.splitlines() if ln.strip()][:40]
    if not lines:
        return True
    strict_def_verb_re = re.compile(r"\b(?:is|refers\s+to|means|defined\s+as)\b", flags=re.IGNORECASE)
    for ln in lines[:20]:
        words = re.findall(r"[A-Za-z][A-Za-z\-']*", ln)
        if not words:
            continue
        cap_words = re.findall(r"\b[A-Z][a-z]{2,}\b", ln)
        has_strict_verb = bool(strict_def_verb_re.search(ln))
        if len(words) <= 12 and len(cap_words) >= 4 and not has_strict_verb:
            return True
        if re.search(r"\S+(?:\s{2,}\S+){2,}", ln):
            return True
    short_lines = sum(1 for ln in lines if len(re.findall(r"[A-Za-z][A-Za-z\-']*", ln)) <= 5)
    bullet_lines = sum(1 for ln in lines if re.match(r"^(?:[-•*]|\d+[.)])\s+", ln))
    sentence_like = sum(1 for ln in lines if re.search(r"[.!?]$", ln))
    numbered_row_lines = sum(1 for ln in lines if re.match(r"^\s*\d+\.\s+[A-Z]", ln))
    if numbered_row_lines >= 3:
        return True
    if short_lines / max(1, len(lines)) >= 0.55:
        return True
    if bullet_lines / max(1, len(lines)) >= 0.30:
        return True
    if sentence_like <= 2 and len(lines) >= 8:
        return True
    return False
