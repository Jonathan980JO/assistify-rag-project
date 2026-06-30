"""Extracted retrieval helpers (Phase 8H).

Moved verbatim from ``assistify_rag_server.py``. This module is a leaf in the
retrieval package and never imports the server. Shared mutable state, the
logger, and engine functions still in the monolith are reached through ``S``,
the server module injected via ``bind_server`` at registration time. Behavior is
identical to the monolith original.
"""
from __future__ import annotations

from backend.config_head import *  # noqa: F401,F403 - mirrors the server module
from typing import Dict
from backend.rag_chunk_heuristics import looks_table_or_heading_like_chunk as _looks_table_or_heading_like_chunk
import re

S = None


def bind_server(server) -> None:
    """Bind the live server module so extracted helpers can reach shared state."""
    global S
    S = server

_SYMBOLIC_LIST_CARDINALS: Dict[str, int] = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
}

_DIRECT_DEFINITION_CUE_RE = re.compile(
    r"\b(?:is|are|refers\s+to|means|can\s+be\s+defined\s+as|is\s+defined\s+as|are\s+defined\s+as|defined\s+as)\b",
    flags=re.IGNORECASE,
)

_ANY_DEFINITION_CUE_RE = re.compile(
    r"\b(?:is|are|has|have|had|refers\s+to|means|can\s+be\s+defined\s+as|is\s+defined\s+as|are\s+defined\s+as|defined\s+as|"
    r"involves|include|includes|included|consists\s+of|characteri[sz]ed\s+by|focuses\s+on|deals\s+with|"
    r"considered|classified|regarded|viewed|treated|relies\s+on|depends\s+on|requires|"
    r"covers|cover|insured|insures|insure|provides|provide|protects|protect|guarantees|guarantee|"
    r"offers|offer|charges|charge|bills|bill|lets|let|allows|allow|comes\s+with|gives|give|earns|earn|pays|pay|"
    r"equals|equal|costs|cost|up\s+to|at\s+least|minimum|maximum|per\s+depositor)\b",
    flags=re.IGNORECASE,
)

def _preview_for_quality_log(text: str, limit: int = 180) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip())[:limit]

def _ocr_filter_rejected_reason(text: str, query_text: str = "") -> str | None:
    raw_lines = [str(ln or "").strip() for ln in str(text or "").splitlines() if str(ln or "").strip()]
    s = re.sub(r"\s+", " ", str(text or "").strip())
    if not s:
        return "empty"
    if s == RAG_NO_MATCH_RESPONSE:
        return None
    low = s.lower()
    query_low = re.sub(r"\s+", " ", str(query_text or "").strip().lower())
    explicit_list_or_table_query = bool(
        query_low
        and (
            S._is_targeted_list_question(query_low)
            or re.match(r"^\s*(?:what|which)\s+are\b", query_low)
            or re.search(r"\b(?:list|table|figure|fig\.?|columns?|rows?|items?|types?|kinds?|categories?)\b", query_low)
        )
    )

    number_words = {
        "zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
        "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen", "twenty",
    }
    table_fragment_words = {
        "row", "rows", "column", "columns", "group", "groups", "discipline", "disciplines",
        "type", "types", "kind", "kinds", "category", "categories", "figure", "fig", "table",
        "chapter", "section", "unit", "page", "pages", "item", "items", "number", "numbers",
    }

    def _line_fragment_reason(line_value: str) -> str | None:
        payload = re.sub(r"^\s*(?:[-*\u2022]|\d+[.)]|[A-Za-z][.)])\s+", "", str(line_value or "").strip())
        payload = re.sub(r"\s+", " ", payload).strip(" \t\r\n,;:-")
        if not payload:
            return "empty_line_fragment"
        payload_low = payload.lower()
        alpha_words = re.findall(r"[A-Za-z][A-Za-z\-']*", payload)
        if not alpha_words:
            return "no_alpha_words"
        if re.search(r"https?://|www\.|\bisbn\b|copyright|all\s+rights\s+reserved", payload_low):
            return "source_footer_or_link"
        if re.search(r"\b(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty)[a-z]{3,}\b", payload_low):
            return "merged_number_word"
        if re.search(r"\b(?:[bcdfghjklmnpqrstvwxyz]{6,})\b", payload_low):
            return "consonant_dense_ocr"
        if re.search(r"(?<!['’])\b(?![ai]\b)[a-z]\s+[a-z]{3,}\b", payload_low):
            return "split_ocr_word"
        if re.search(r"\b[a-z]{3,}\s+(?:ves|tion|tions|ment|ments|ing|ed|er|ers|al|ally|ity|ities|es)\b", payload_low):
            return "split_ocr_suffix"
        if len(payload) >= 12:
            # Strip runs of 4+ identical separator chars (====, ----, ~~~~) before counting symbols.
            # These are document section dividers, not OCR noise — without this, a heading like
            # "Guide\n======\nOptions\n------\n| col | col |" exceeds the 0.28 threshold.
            payload_for_ratio = re.sub(r"[=\-_~]{4,}", " ", payload)
            symbol_ratio = len(re.findall(r"[^A-Za-z0-9\s]", payload_for_ratio)) / float(max(1, len(payload_for_ratio)))
            if symbol_ratio > 0.28:
                return "symbol_dense_fragment"
        if len(alpha_words) == 1:
            only = alpha_words[0].lower()
            query_has_word = bool(query_low and S._token_match_light(query_low, only))
            if only in number_words:
                return "count_word_fragment"
            if only in table_fragment_words and not query_has_word:
                return "table_column_fragment"
        if not explicit_list_or_table_query:
            meaningful = [w for w in alpha_words if len(w) >= 3]
            has_verb = bool(re.search(r"\b(?:is|are|was|were|be|being|been|has|have|had|does|do|did|means|refers|include|includes|included|involves|describes|explains|contains|consists|focuses|considered|classified|regarded|viewed|treated|relies\s+on|depends\s+on|requires)\b", payload_low))
            if len(meaningful) < 4 and not has_verb:
                return "too_few_meaningful_words"
        return None

    if len(raw_lines) >= 2:
        bullet_lines = [ln for ln in raw_lines if re.match(r"^\s*(?:[-*\u2022]|\d+[.)]|[A-Za-z][.)])\s+\S", ln)]
        if len(bullet_lines) >= 2 and len(bullet_lines) >= max(2, int(len(raw_lines) * 0.70)):
            for bullet_line in bullet_lines:
                line_reason = _line_fragment_reason(bullet_line)
                if line_reason:
                    return f"bullet_{line_reason}"
            # P6: protect well-structured bullet/letter/number lists from
            # OCR rejection and surface that decision in the logs.
            S.logger.info("[OCR FILTER] allowed_structured_list=True bullet_lines=%d total_lines=%d",
                        len(bullet_lines), len(raw_lines))
            return None
    # P6: query-context-aware filtering. Compute meaningful tokens from the
    # query so we can suppress generic OCR rejections when the sentence
    # actually mentions the queried concept. No domain-specific words.
    query_content_tokens = {
        t for t in re.findall(r"[a-z0-9]{4,}", query_low)
        if t not in {"what", "which", "list", "name", "give", "tell", "about", "explain",
                     "define", "describe", "this", "that", "these", "those", "main",
                     "from", "with", "into", "their", "there", "they", "your", "ours",
                     "between", "compare", "difference"}
    }
    sentence_mentions_entity = bool(
        query_content_tokens
        and any(re.search(rf"\b{re.escape(t)}\b", low) for t in query_content_tokens)
    )
    words = re.findall(r"[A-Za-z][A-Za-z\-']*", s)
    if len(words) < 3:
        return "too_short_fragment"
    if re.search(r"\b(?:www\.|https?://|isbn|copyright|all\s+rights\s+reserved)\b", low):
        return "source_footer_or_link"
    line_reason = _line_fragment_reason(s)
    if line_reason and line_reason not in {"too_few_meaningful_words"}:
        return line_reason
    if re.search(r"(?:\b[A-Za-z]\s+){4,}\b", s):
        return "broken_spaced_letters"
    if re.search(r"\b(?:page|p\.)\s*\d{1,4}\b", low) and len(words) <= 12 and not sentence_mentions_entity:
        return "page_header_footer"
    if re.search(r"\b(?:table\s+of\s+contents|contents|index)\b", low) and not re.search(r"\b(?:contents|index|toc|table\s+of\s+contents)\b", query_low):
        return "toc_fragment"
    # P6: sentence-tail rejection now requires (start-with-conjunction OR
    # end-with-dangling-conjunction) AND short length AND no query-entity
    # mention. A long, content-rich sentence beginning with "Of the five..."
    # that mentions the queried concept is a valid sentence, not a tail.
    if re.match(r"^\s*(?:and|or|but|because|therefore|thus|then|while|whereas|which|that|who|whom|whose|of|to|for|with|by|from|in|on|at)\b", low):
        if len(words) <= 14 and not sentence_mentions_entity:
            return "sentence_tail"
    if re.search(r"\b(?:and|or|but|because|therefore|thus|then|while|whereas|which|that|who|whom|whose|of|to|for|with|by|from|in|on|at)\s*$", low):
        if len(words) <= 14 and not sentence_mentions_entity:
            return "sentence_tail"
    punctuation_ratio = len(re.findall(r"[^A-Za-z0-9\s]", s)) / float(max(1, len(s)))
    if punctuation_ratio > 0.30:
        return "punctuation_noise"
    if len(words) >= 8 and (len(set(w.lower() for w in words)) / float(max(1, len(words)))) < 0.35:
        return "repeated_text"
    lines = [re.sub(r"\s+", " ", ln).strip().lower() for ln in str(text or "").splitlines() if ln.strip()]
    if len(lines) >= 2 and len(set(lines)) == 1:
        return "repeated_title_text"
    has_sentence_punct = bool(re.search(r"[.!?]$", s))
    has_predicate = bool(re.search(
        r"\b(?:is|are|was|were|has|have|had|means|refers\s+to|include|includes|included|involves|describes|explains|"
        r"contains|consists\s+of|focuses\s+on|considered|classified|regarded|viewed|treated|relies\s+on|"
        r"depends\s+on|requires|covers|cover|insured|insures|insure|provides|provide|protects|protect|"
        r"guarantees|guarantee|offers|offer|charges|charge|bills|bill|lets|let|allows|allow|gives|give|"
        r"comes\s+with|equals|equal|costs|cost|up\s+to|at\s+least|minimum|maximum|"
        r"per\s+depositor)\b",
        low,
    ))
    structured_sentence_mode = bool(
        query_low
        and (
            S._is_definition_comparison_query(query_low)
            or S._is_definition_style_query(query_low)
            or S._is_explanation_intent_query(query_low)
        )
    )
    if structured_sentence_mode:
        meaningful_words = [w for w in words if len(w) >= 3]
        if len(meaningful_words) < 4:
            return "too_few_meaningful_words"
        if not has_predicate:
            return "no_predicate_fragment"
        if (not has_sentence_punct) and len(meaningful_words) < 8:
            return "incomplete_sentence_fragment"
    cap_words = re.findall(r"\b[A-Z][A-Za-z]{2,}\b", s)
    if (not has_sentence_punct) and (not has_predicate) and len(words) <= 12 and len(cap_words) >= max(3, len(words) // 2):
        return "heading_fragment"
    return None

def _log_ocr_filter_rejection(text: str, reason: str) -> None:
    S.logger.info("[OCR FILTER] rejected=%s reason=%s", _preview_for_quality_log(text), reason)

def _definition_direct_pattern_match(sentence: str, entity_l: str = "") -> bool:
    s = re.sub(r"\s+", " ", str(sentence or "").strip())
    if not s:
        return False
    low = s.lower()
    if entity_l:
        entity_pattern = re.escape(entity_l).replace("\\ ", r"\s+")
        return bool(
            re.search(
                rf"^\s*(?:the\s+)?{entity_pattern}\s+(?:is|are|refers\s+to|means|can\s+be\s+defined\s+as|is\s+defined\s+as|are\s+defined\s+as|defined\s+as)\b",
                low,
                flags=re.IGNORECASE,
            )
        )
    return bool(_DIRECT_DEFINITION_CUE_RE.search(low))

def _definition_quality_rejected_reason(sentence: str, entity_l: str = "", require_definition_cue: bool = True, query_text: str = "") -> str | None:
    s = re.sub(r"\s+", " ", str(sentence or "").strip())
    if not s:
        return "empty"
    # P6: derive a synthetic query string from the entity when no explicit
    # query is supplied so the OCR filter can apply context-aware rules
    # (e.g. don't drop a "page X" sentence if it actually mentions the
    # queried entity). Fully generic; entity comes from the caller.
    _ocr_query = query_text or (f"what is {entity_l}" if entity_l else "")
    ocr_reason = _ocr_filter_rejected_reason(s, _ocr_query)
    if ocr_reason:
        return ocr_reason
    low = s.lower()
    if re.match(r"^\s*(?:[-*\u2022]|\d+[.)]|[a-z][.)])\s+", s, flags=re.IGNORECASE):
        return "list_fragment"
    if re.search(r"\b(?:table\s+of\s+contents|contents|learning\s+objectives?|key\s+terms?|chapter\s+\d+|unit\s+\d+)\b", low):
        return "heading_or_toc_fragment"
    try:
        if _looks_table_or_heading_like_chunk(s) and not _ANY_DEFINITION_CUE_RE.search(low):
            return "table_or_heading_fragment"
    except Exception:
        pass
    if re.search(r"[\u2022|\t]", s) and not _ANY_DEFINITION_CUE_RE.search(low):
        return "table_or_list_fragment"
    # P2: only treat comma-heavy sentences as random list fragments when they
    # are also long (>=20 words). Short comma-rich definitions like
    # "X is a method that uses A, B, and C." must not be hard-rejected.
    if (
        len(re.findall(r",", s)) >= 3
        and not _ANY_DEFINITION_CUE_RE.search(low)
        and len(re.findall(r"[A-Za-z][A-Za-z\-']*", s)) >= 20
    ):
        return "random_list_fragment"
    if entity_l:
        entity_pattern = re.escape(entity_l).replace("\\ ", r"\s+")
        if not re.search(rf"\b{entity_pattern}\b", low):
            entity_tokens = [t for t in re.findall(r"[a-z0-9]{2,}", entity_l) if t not in {"the", "a", "an", "of", "and", "in", "to", "for"}]
            hits = sum(1 for tok in entity_tokens if re.search(rf"\b{re.escape(tok)}\b", low))
            min_hits = max(1, min(2, len(entity_tokens)))
            has_numeric = bool(re.search(r"(?:[\$€£]\s*)?\d", s))
            if S._is_numeric_fact_lookup_query(query_text):
                min_hits = 1
                if has_numeric and hits >= 1:
                    pass
                elif has_numeric and any(t in low for t in entity_tokens[:2]):
                    pass
                elif hits < min_hits:
                    return "missing_query_entity"
            elif hits < min_hits:
                return "missing_query_entity"
    if require_definition_cue and not _ANY_DEFINITION_CUE_RE.search(low):
        return "missing_definition_cue"
    if re.match(r"^\s*(?:he|she|they|it|this|that|these|those|we|i|you)\b", low):
        return "pronoun_led_fragment"
    return None

def _log_definition_quality_rejection(sentence: str, reason: str) -> None:
    S.logger.info("[DEF QUALITY] rejected_reason=%s sentence=%s", reason, _preview_for_quality_log(sentence))

def _log_list_quality_rejection(item: str, reason: str) -> None:
    S.logger.info("[LIST QUALITY] rejected_item=%s reason=%s", _preview_for_quality_log(item, 120), reason)

def _list_query_count_target(query_text: str) -> int | None:
    q = re.sub(r"\s+", " ", str(query_text or "").strip().lower())
    if not q:
        return None
    m = re.search(r"\b(\d{1,2})\b", q)
    if m:
        value = S._symbolic_list_count_value(m.group(1))
        if isinstance(value, int) and 2 <= value <= 20:
            return value
    for token in re.findall(r"[a-z]+", q):
        value = _SYMBOLIC_LIST_CARDINALS.get(token)
        if isinstance(value, int) and 2 <= value <= 20:
            return value
    return None

_STRICT_LIST_LABEL_VERB_RE = re.compile(
    r"\b(?:is|are|was|were|be|been|being|has|have|had|include|includes|included|"
    r"consist|consists|consisted|comprise|comprises|composed|focus|focuses|focused|"
    r"study|studies|studied|explain|explains|explained|describe|describes|described|"
    r"involv(?:e|es|ed)|concern(?:s|ed)?)\b",
    re.IGNORECASE,
)

def _strict_list_label_reject_reason(item_text: str, *, max_words: int = 5, allow_sentence_item: bool = False) -> str:
    s = re.sub(r"\s+", " ", str(item_text or "").strip(" \t\r\n-•*.,;:–—"))
    if not s:
        return "empty"
    low = s.lower()
    if re.search(r"https?://|www\.|\.com\b|isbn|copyright|all\s+rights\s+reserved", low):
        return "source_noise"
    if re.search(r"\b(?:chapter|figure|table|contents?|index|page)\s*\d*\b", low):
        return "document_artifact"
    if re.fullmatch(r"\d+(?:\.\d+)?", low):
        return "numeric_fragment"
    if re.fullmatch(r"(?:and|the|this|that|these|those|with|from|into|within)[a-z]{4,}", low):
        return "broken_spacing"
    if re.search(r"\b(?:and|or|to|of|for|with|by|in|on|at|from|because|however|therefore|thus|then)\s*$", low):
        return "continuation_fragment"
    if re.match(r"^\s*(?:and|or|to|of|for|with|by|in|on|at|from|because|however|therefore|thus|then)\b", low):
        return "continuation_fragment"
    words = re.findall(r"[A-Za-z][A-Za-z\-']*", s)
    if not words:
        return "no_words"
    wc = len(words)
    if wc > max_words and not allow_sentence_item:
        return "long_phrase"
    if wc >= 3 and s[:1].islower():
        return "mid_sentence_fragment"
    if wc <= 2 and words[0].lower() in {"the", "a", "an", "this", "that", "these", "those"}:
        return "weak_leadin_fragment"
    mid_words = [w.lower() for w in words[1:-1]]
    if any(_STRICT_LIST_LABEL_VERB_RE.fullmatch(w) for w in mid_words) and not allow_sentence_item:
        return "verb_in_middle"
    if _STRICT_LIST_LABEL_VERB_RE.search(s) and wc >= 4 and not allow_sentence_item:
        return "sentence_fragment"
    if re.search(r"\b(?:which|that|who|whom|whose|because|while|whereas|although|though|however|therefore)\b", low):
        return "clause_fragment"
    if re.search(r"[.!?]", s):
        return "sentence_punctuation"
    if re.search(r"[;:]", s):
        return "label_with_clause"
    return ""

