"""Extracted retrieval helpers (Phase 8H).

Moved verbatim from ``assistify_rag_server.py``. This module is a leaf in the
retrieval package and never imports the server. Shared mutable state, the
logger, and engine functions still in the monolith are reached through ``S``,
the server module injected via ``bind_server`` at registration time. Behavior is
identical to the monolith original.
"""
from __future__ import annotations

from backend.config_head import *  # noqa: F401,F403 - mirrors the server module
from typing import Any
from typing import Dict
from typing import List
from typing import Set
from typing import Tuple
from backend.retrieval.validation import _SYMBOLIC_LIST_CARDINALS
from backend.retrieval.routing import _SYMBOLIC_LIST_NUMBER_WORDS
from backend.retrieval.routing import _SYMBOLIC_LIST_QUERY_STOPWORDS
from backend.retrieval.routing import _assess_list_coherence
from backend.retrieval.routing import _clean_ocr_artifacts
from backend.retrieval.routing import _collect_local_window_support
from backend.services.language_service import _detect_language
from backend.retrieval.routing import _extract_list_from_context
from backend.retrieval.routing import _extract_simple_list_from_docs
from backend.retrieval.routing import _is_definition_comparison_query
from backend.retrieval.routing import _is_document_summary_query
from backend.retrieval.routing import _light_normalize_query_token
from backend.retrieval.routing import _mpc15_load_full_corpus_chunks
from backend.retrieval.routing import _normalize_context_entities
from backend.retrieval.routing import _normalize_query_for_router
from backend.retrieval.routing import _not_found_response
from backend.retrieval.routing import _preclean_list_answer_for_assessment
from backend.retrieval.routing import _token_match_light
from collections import defaultdict
import json
import math
import re

S = None


def bind_server(server) -> None:
    """Bind the live server module so extracted helpers can reach shared state."""
    global S
    S = server

_DOC_ROUTER_STOPWORDS: Set[str] = {
    "a", "an", "the", "and", "or", "but", "if", "then", "else", "of", "to", "in", "on", "at",
    "for", "from", "by", "with", "without", "within", "into", "onto", "as", "is", "are", "was",
    "were", "be", "being", "been", "do", "does", "did", "can", "could", "should", "would", "may",
    "might", "must", "will", "shall", "what", "which", "who", "whom", "whose", "when", "where",
    "why", "how", "during", "about", "regarding", "concerning", "between", "among", "against",
    "tell", "show", "give", "name", "mention", "identify", "list", "define", "explain", "describe",
    "please", "me", "we", "you", "they", "he", "she", "it", "this", "that", "these", "those",
    "document", "documents", "source", "sources", "file", "files", "pdf", "pdfs", "both", "all", "each",
    "combine", "combined", "synthesize", "synthesise", "summarize", "summarise", "summary", "info",
    "information", "details", "based", "using", "provided", "context",
}

_DOC_ROUTER_VAGUE_TERMS: Set[str] = {
    "policy", "rule", "rules", "procedure", "procedures", "guideline", "guidelines", "requirement",
    "requirements", "topic", "subject", "section", "chapter", "overview", "summary", "detail", "details",
    "information", "document", "source", "file", "item", "items", "thing", "things",
}

_DOC_ROUTER_COMPARISON_OPERATORS: Set[str] = {
    "difference", "differences", "different", "differentiate", "distinguish",
    "compare", "compared", "comparison", "contrast", "contrasts", "distinction",
    "versus", "vs",
}

_SYMBOLIC_LIST_CATEGORY_WORDS: Set[str] = {
    "step", "steps", "type", "types", "kind", "kinds", "form", "forms", "element", "elements",
    "principle", "principles", "function", "functions", "stage", "stages", "part", "parts",
    "component", "components", "factor", "factors", "feature", "features", "characteristic",
    "characteristics", "category", "categories", "branch", "branches", "method", "methods",
}

def _normalize_symbolic_list_surface(value: str) -> str:
    normalized = str(value or "").replace("’", "'").lower()
    normalized = re.sub(r"[^a-z0-9']+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()

def _symbolic_list_count_value(token: str) -> int | None:
    raw = str(token or "").strip().lower()
    if not raw:
        return None
    if raw.isdigit():
        try:
            value = int(raw)
        except Exception:
            return None
        return value if 1 <= value <= 20 else None
    return _SYMBOLIC_LIST_CARDINALS.get(raw)

def _symbolic_list_label_variants(label_text: str) -> Set[str]:
    raw = str(label_text or "").strip().replace("’", "'")
    compact = re.sub(r"[^A-Za-z0-9']+", "", raw).lower()
    if not compact:
        return set()
    variants: Set[str] = {compact, compact.replace("'", "")}
    letter_match = re.fullmatch(r"([a-z])(?:'?s)?", compact)
    if letter_match:
        letter = letter_match.group(1)
        variants.update({letter, f"{letter}s", f"{letter}'s", f"{letter} s"})
        return variants
    if compact.endswith("s") and len(compact) > 3:
        variants.add(compact[:-1])
    elif compact.isalpha() and len(compact) > 2:
        variants.add(f"{compact}s")
    return {re.sub(r"\s+", " ", variant).strip() for variant in variants if variant.strip()}

def _detect_short_symbolic_list_query(query_text: str) -> dict[str, Any] | None:
    raw_query = re.sub(r"\s+", " ", str(query_text or "").strip())
    if not raw_query:
        return None
    query_norm = _normalize_symbolic_list_surface(raw_query.strip(" ?.!,;:"))
    if not query_norm:
        return None
    query_tokens = re.findall(r"[a-z0-9']+", query_norm)
    if len(query_tokens) > 18:
        return None

    count_pattern = "|".join([re.escape(word) for word in _SYMBOLIC_LIST_CARDINALS] + [r"\d{1,2}"])
    category_pattern = "|".join(re.escape(word) for word in sorted(_SYMBOLIC_LIST_CATEGORY_WORDS, key=len, reverse=True))
    counted_category_match = re.search(
        rf"\b(?:(?P<qualifier>basic|main|major|key|primary|principal)\s+)?"
        rf"(?:(?P<count>{count_pattern})\s+)?"
        rf"(?P<head>{category_pattern})\s+(?:of|for|in|to)\s+(?:the\s+)?(?P<object>[a-z0-9][a-z0-9'\- ]{{1,80}})",
        query_norm,
        flags=re.IGNORECASE,
    )
    if counted_category_match:
        object_text = re.sub(
            r"\b(?:from|on|with|document|chapter|section)\b.*$",
            "",
            str(counted_category_match.group("object") or "").strip(),
        ).strip()
        object_tokens = [
            token for token in re.findall(r"[a-z0-9']+", object_text)
            if token not in _SYMBOLIC_LIST_QUERY_STOPWORDS and token not in _SYMBOLIC_LIST_CATEGORY_WORDS
        ]
        head_text = str(counted_category_match.group("head") or "").strip()
        category_variants = _symbolic_list_label_variants(head_text) or {head_text.lower()}
        count_value = _symbolic_list_count_value(str(counted_category_match.group("count") or ""))
        qualifier = str(counted_category_match.group("qualifier") or "").strip().lower()
        if head_text and object_tokens and (count_value is None or count_value >= 2):
            object_phrase = " ".join(object_tokens[:6])
            count_terms: Set[str] = set()
            if count_value is not None:
                count_terms.add(str(count_value))
                if count_value in _SYMBOLIC_LIST_NUMBER_WORDS:
                    count_terms.add(_SYMBOLIC_LIST_NUMBER_WORDS[count_value])

            phrase_variants: Set[str] = set()
            for category_variant in category_variants:
                if not category_variant:
                    continue
                phrase_variants.update({
                    _normalize_symbolic_list_surface(f"{category_variant} of {object_phrase}"),
                    _normalize_symbolic_list_surface(f"{category_variant} for {object_phrase}"),
                    _normalize_symbolic_list_surface(f"{object_phrase} {category_variant}"),
                    _normalize_symbolic_list_surface(f"basic {category_variant} of {object_phrase}"),
                    _normalize_symbolic_list_surface(f"basic {object_phrase} {category_variant}"),
                })
                for count_term in count_terms:
                    phrase_variants.update({
                        _normalize_symbolic_list_surface(f"{count_term} {category_variant}"),
                        _normalize_symbolic_list_surface(f"{count_term} {category_variant} of {object_phrase}"),
                        _normalize_symbolic_list_surface(f"{count_term} {object_phrase} {category_variant}"),
                        _normalize_symbolic_list_surface(f"{count_term} basic {category_variant}"),
                        _normalize_symbolic_list_surface(f"{count_term} basic {category_variant} of {object_phrase}"),
                        _normalize_symbolic_list_surface(f"these {count_term} basic {category_variant}"),
                    })
            if qualifier:
                for category_variant in category_variants:
                    phrase_variants.add(_normalize_symbolic_list_surface(f"{qualifier} {category_variant} of {object_phrase}"))

            return {
                "kind": "counted_category" if count_value is not None else "category",
                "count": count_value,
                "phrase": f"{head_text} of {object_phrase}",
                "phrase_variants": sorted({variant for variant in phrase_variants if variant}),
                "label_variants": sorted(category_variants),
                "category_terms": sorted(category_variants),
                "object_terms": object_tokens,
                "focus_terms": list(dict.fromkeys([head_text] + sorted(category_variants) + object_tokens)),
                "qualifier": qualifier,
                "counted_list_rescue": True,
            }

    counted_match = re.search(
        rf"\b(?P<count>{count_pattern})\s+(?P<label>[a-z](?:'?s)?|[a-z0-9][a-z0-9'\-]{{1,30}}s)\b",
        query_norm,
        flags=re.IGNORECASE,
    )
    if counted_match:
        count_value = _symbolic_list_count_value(counted_match.group("count"))
        label_text = str(counted_match.group("label") or "").strip()
        if count_value is not None and count_value >= 2 and label_text:
            label_variants = _symbolic_list_label_variants(label_text)
            count_terms = {str(count_value)}
            if count_value in _SYMBOLIC_LIST_NUMBER_WORDS:
                count_terms.add(_SYMBOLIC_LIST_NUMBER_WORDS[count_value])
            phrase_variants: Set[str] = set()
            for count_term in count_terms:
                for label_variant in label_variants or {label_text.lower()}:
                    phrase_variants.add(_normalize_symbolic_list_surface(f"{count_term} {label_variant}"))
            focus_terms = [
                token for token in query_tokens
                if token not in _SYMBOLIC_LIST_QUERY_STOPWORDS
                and token not in _SYMBOLIC_LIST_CARDINALS
                and not token.isdigit()
            ]
            focus_terms.extend(sorted(label_variants))
            return {
                "kind": "counted",
                "count": count_value,
                "phrase": re.sub(r"\s+", " ", counted_match.group(0)).strip(),
                "phrase_variants": sorted({variant for variant in phrase_variants if variant}),
                "label_variants": sorted(label_variants),
                "focus_terms": list(dict.fromkeys([term for term in focus_terms if term])),
            }

    category_match = re.search(
        rf"\b(?P<head>{category_pattern})\s+(?:of|for|in|to)\s+(?:the\s+)?(?P<object>[a-z0-9][a-z0-9'\- ]{{1,80}})",
        query_norm,
        flags=re.IGNORECASE,
    )
    if category_match:
        object_text = re.sub(
            r"\b(?:from|in|on|for|with|document|chapter|section)\b.*$",
            "",
            str(category_match.group("object") or "").strip(),
        ).strip()
        object_tokens = [
            token for token in re.findall(r"[a-z0-9']+", object_text)
            if token not in _SYMBOLIC_LIST_QUERY_STOPWORDS and token not in _SYMBOLIC_LIST_CATEGORY_WORDS
        ]
        if object_tokens:
            head_text = str(category_match.group("head") or "").strip()
            phrase = f"{head_text} of {' '.join(object_tokens[:6])}"
            phrase_variants = {
                _normalize_symbolic_list_surface(phrase),
                _normalize_symbolic_list_surface(f"{head_text} for {' '.join(object_tokens[:6])}"),
                _normalize_symbolic_list_surface(f"{' '.join(object_tokens[:6])} {head_text}"),
            }
            return {
                "kind": "category",
                "count": None,
                "phrase": phrase,
                "phrase_variants": sorted({variant for variant in phrase_variants if variant}),
                "label_variants": [head_text],
                "focus_terms": list(dict.fromkeys([head_text] + object_tokens)),
            }
    return None

_SPOKEN_SINGLE_LETTER_NAMES: Dict[str, str] = {
    "a": "a", "ay": "a",
    "b": "b", "bee": "b", "be": "b",
    "c": "c", "see": "c", "sea": "c",
    "d": "d", "dee": "d",
    "e": "e", "ee": "e",
    "f": "f", "ef": "f",
    "g": "g", "gee": "g",
    "h": "h", "aitch": "h", "hache": "h",
    "i": "i", "eye": "i",
    "j": "j", "jay": "j",
    "k": "k", "kay": "k",
    "l": "l", "el": "l", "ell": "l",
    "m": "m", "em": "m",
    "n": "n", "en": "n",
    "o": "o", "oh": "o",
    "p": "p", "pee": "p",
    "q": "q", "cue": "q", "queue": "q",
    "r": "r", "ar": "r", "are": "r",
    "s": "s", "ess": "s",
    "t": "t", "tee": "t", "tea": "t",
    "u": "u", "you": "u",
    "v": "v", "vee": "v",
    "w": "w", "doubleyou": "w", "doubleu": "w",
    "x": "x", "ex": "x",
    "y": "y", "why": "y",
    "z": "z", "zee": "z", "zed": "z",
}

def _normalize_symbolic_count_letter_list_query_before_retrieval(query_text: str) -> tuple[str, str]:
    raw_query = re.sub(r"\s+", " ", str(query_text or "").strip())
    if not raw_query or _detect_language(raw_query) == "ar":
        return raw_query, ""

    query_norm = _normalize_query_for_router(raw_query)
    if not query_norm:
        return raw_query, ""
    if not re.match(r"^\s*(?:(?:what|which)\s+(?:is|are)|list|name|give|mention|identify)\b", query_norm):
        return raw_query, ""

    tokens = query_norm.split()
    if not tokens:
        return raw_query, ""

    question_has_list_shape = bool(
        re.match(r"^\s*(?:(?:what|which)\s+are|list|name|give|mention|identify)\b", query_norm)
    )
    allowed_tail_starters = {"in", "of", "for", "about", "within", "to"}
    measurement_tail_terms = {
        "length", "height", "width", "depth", "distance", "meter", "meters", "metre", "metres",
        "mile", "miles", "kilometer", "kilometers", "kilometre", "kilometres", "feet", "foot",
    }

    def _letter_from_token(token: str) -> str:
        cleaned_token = re.sub(r"[^a-z]+", "", str(token or "").lower())
        if len(cleaned_token) == 1:
            return cleaned_token
        if cleaned_token.endswith("s") and cleaned_token[:-1] in _SPOKEN_SINGLE_LETTER_NAMES:
            return _SPOKEN_SINGLE_LETTER_NAMES[cleaned_token[:-1]]
        return _SPOKEN_SINGLE_LETTER_NAMES.get(cleaned_token, "")

    for token_index, token in enumerate(tokens):
        count_value: int | None = None
        letter_value = ""
        consume_until = token_index + 1

        compact_match = re.fullmatch(r"(?P<count>\d{1,2})(?P<letter>[a-z])s?", token)
        if compact_match:
            count_value = _symbolic_list_count_value(compact_match.group("count"))
            letter_value = compact_match.group("letter")
            if consume_until < len(tokens) and tokens[consume_until] == "s":
                consume_until += 1
        else:
            count_value = _symbolic_list_count_value(token)
            if count_value is None or token_index + 1 >= len(tokens):
                continue
            letter_value = _letter_from_token(tokens[token_index + 1])
            if not letter_value:
                continue
            consume_until = token_index + 2
            if consume_until < len(tokens) and tokens[consume_until] == "s":
                consume_until += 1

        if count_value is None or not (2 <= count_value <= 20) or not letter_value:
            continue

        tail_tokens = tokens[consume_until:]
        tail_starter = tail_tokens[0] if tail_tokens else ""
        has_allowed_tail = bool(tail_starter in allowed_tail_starters or not tail_tokens)
        if tail_starter == "in" and len(tail_tokens) >= 2 and tail_tokens[1] in measurement_tail_terms:
            continue
        if not (question_has_list_shape or has_allowed_tail):
            continue

        count_word = _SYMBOLIC_LIST_NUMBER_WORDS.get(count_value, str(count_value))
        label_text = f"{letter_value.upper()}s"
        tail_text = " ".join(tail_tokens).strip()
        normalized_query = f"What are the {count_word} {label_text}"
        if tail_text:
            normalized_query = f"{normalized_query} {tail_text}"
        normalized_query = normalized_query.strip() + "?"
        return normalized_query, f"{count_word} {label_text}"

    return raw_query, ""

def _symbolic_list_active_allowed_sources(seed_docs: list[dict] | None = None) -> Set[str]:
    allowed_sources = set(S._get_active_sources())
    if allowed_sources:
        return allowed_sources
    for seed_doc in seed_docs or []:
        metadata = dict((seed_doc or {}).get("metadata") or {})
        allowed_sources.update(S._metadata_source_keys(metadata))
    return allowed_sources

def _is_counted_category_list_query_info(query_info: dict[str, Any] | None) -> bool:
    if not isinstance(query_info, dict):
        return False
    return bool(query_info.get("counted_list_rescue") and query_info.get("category_terms") and query_info.get("object_terms"))

def _prepare_counted_list_rescue_text(text: str) -> str:
    cleaned = str(text or "").replace("•", " ")
    cleaned = cleaned.replace("–", "-").replace("—", "-").replace("’", "'")
    # Generic OCR repair for linearized diagrams/tables: insert boundaries before
    # glued all-caps headings and before numbered markers that touch words.
    cleaned = re.sub(r"([a-z])([A-Z]{2,})(?=\s|$)", r"\1 \2", cleaned)
    cleaned = re.sub(r"([A-Za-z])(?=\d{1,2}\s*[.)])", r"\1 ", cleaned)
    cleaned = re.sub(r"(\d{1,2})\s*([.)])\s*", r" \1\2 ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()

def _clean_counted_list_label_item(raw_item: str) -> str:
    item = re.sub(r"\s+", " ", str(raw_item or "")).strip(" \t\r\n,;:-\"'")
    if not item:
        return ""
    item = re.sub(r"\b([A-Z][a-z])\s+([a-z]{4,})\b", r"\1\2", item)
    # Stop at sentence/list-table boundaries; if a later all-caps heading is glued
    # onto the final label, this keeps only the label text.
    item = re.split(r"[.;:]\s*(?=[A-Z0-9])|[.;:]$|\s+(?=[A-Z]{2,}\b)", item, maxsplit=1)[0]
    item = re.sub(r"\s+", " ", item).strip(" \t\r\n,;:-\"'")
    return item

def _is_clean_counted_label_item(item_text: str) -> bool:
    item = re.sub(r"\s+", " ", str(item_text or "")).strip(" ,;:-")
    if not item or len(item) > 80:
        return False
    if re.search(r"\d", item):
        return False
    if re.search(r"[.!?:;]", item):
        return False
    words = re.findall(r"[A-Za-z][A-Za-z'\-]*", item)
    if not (1 <= len(words) <= 6):
        return False
    if not item[0].isupper():
        return False
    if re.search(
        r"\b(?:is|are|was|were|be|been|being|has|have|had|include|includes|including|"
        r"consist|consists|comprise|comprises|means|refers|describe|describes|explain|explains)\b",
        item,
        flags=re.IGNORECASE,
    ):
        return False
    if re.match(r"^(?:and|or|the|a|an)\b", item, flags=re.IGNORECASE):
        return False
    return True

def _shape_counted_list_items(items: list[str]) -> str | None:
    cleaned_items: list[str] = []
    seen_norm: set[str] = set()
    for raw_item in items:
        item = _clean_counted_list_label_item(raw_item)
        if not _is_clean_counted_label_item(item):
            return None
        norm = re.sub(r"[^a-z0-9]+", " ", item.lower()).strip()
        if not norm or norm in seen_norm:
            return None
        seen_norm.add(norm)
        cleaned_items.append(item)
    if len(cleaned_items) < 2:
        return None
    return "\n".join(f"- {item}" for item in cleaned_items)

def _split_counted_inline_clause_items(clause: str, count_target: int | None = None) -> list[list[str]]:
    clean_clause = re.sub(r"\s+", " ", str(clause or "")).strip(" ,;:-")
    if not clean_clause:
        return []
    clean_clause = re.split(
        r"(?:\.\s+(?=[A-Z][a-z])|\b(?:These|This|The)\s+\w+\s+(?:basic|main|major|key|primary|principal)?\s*\w+\s+(?:which\s+are|are|include|includes)\b)",
        clean_clause,
        maxsplit=1,
    )[0].strip(" ,;:-")
    candidates: list[list[str]] = []
    comma_items = [part.strip(" ,;:-") for part in re.split(r"\s*,\s*", clean_clause) if part.strip(" ,;:-")]
    if len(comma_items) >= 2:
        candidates.append(comma_items)
        expanded: list[str] = []
        for index, item in enumerate(comma_items):
            if index == len(comma_items) - 1:
                expanded.extend(part.strip(" ,;:-") for part in re.split(r"\s+and\s+|\s+or\s+", item) if part.strip(" ,;:-"))
            else:
                expanded.append(item)
        if expanded != comma_items:
            candidates.append(expanded)
    connector_items = [part.strip(" ,;:-") for part in re.split(r"\s+and\s+|\s+or\s+", clean_clause) if part.strip(" ,;:-")]
    if len(connector_items) >= 2:
        candidates.append(connector_items)
    if isinstance(count_target, int) and count_target >= 2:
        exact = [items for items in candidates if len(items) == count_target]
        if exact:
            return exact
    return candidates

def _find_counted_list_anchor_spans(text: str, query_info: dict[str, Any]) -> list[tuple[int, int, str]]:
    prepared = _prepare_counted_list_rescue_text(text)
    spans: list[tuple[int, int, str]] = []
    variants = sorted(
        {str(v or "").strip() for v in (query_info.get("phrase_variants") or []) if str(v or "").strip()},
        key=len,
        reverse=True,
    )
    for variant in variants:
        words = re.findall(r"[a-z0-9']+", _normalize_symbolic_list_surface(variant))
        if len(words) < 2:
            continue
        pattern = r"\b" + r"\s+".join(re.escape(word) for word in words) + r"\b"
        for match in re.finditer(pattern, prepared, flags=re.IGNORECASE):
            spans.append((match.start(), match.end(), variant))
    spans.sort(key=lambda row: (row[0], -(row[1] - row[0])))
    deduped: list[tuple[int, int, str]] = []
    occupied: set[int] = set()
    for start, end, variant in spans:
        bucket = start // 10
        if bucket in occupied:
            continue
        occupied.add(bucket)
        deduped.append((start, end, variant))
    return deduped

def _extract_counted_list_labels_from_context(
    query_text: str,
    source_text: str,
    query_info: dict[str, Any] | None = None,
) -> str | None:
    query_info = query_info or _detect_short_symbolic_list_query(query_text) or {}
    if not _is_counted_category_list_query_info(query_info):
        return None
    prepared = _prepare_counted_list_rescue_text(source_text)
    if not prepared:
        return None
    count_target = query_info.get("count")
    if not isinstance(count_target, int) or count_target < 2:
        count_target = None

    anchors = _find_counted_list_anchor_spans(prepared, query_info)
    if not anchors:
        return None

    count_terms: set[str] = set()
    if isinstance(count_target, int) and count_target >= 2:
        count_terms.add(str(count_target))
        if count_target in _SYMBOLIC_LIST_NUMBER_WORDS:
            count_terms.add(_SYMBOLIC_LIST_NUMBER_WORDS[count_target])
    object_terms = {
        _normalize_symbolic_list_surface(str(term))
        for term in (query_info.get("object_terms") or [])
        if _normalize_symbolic_list_surface(str(term))
    }
    category_terms = {
        _normalize_symbolic_list_surface(str(term))
        for term in (query_info.get("category_terms") or [])
        if _normalize_symbolic_list_surface(str(term))
    }

    def _anchor_priority(anchor: tuple[int, int, str]) -> tuple[float, int]:
        start, _end, variant = anchor
        variant_norm = _normalize_symbolic_list_surface(variant)
        variant_tokens = set(re.findall(r"[a-z0-9']+", variant_norm))
        priority = 0.0
        if count_terms and (variant_tokens & count_terms):
            priority += 6.0
        if category_terms and (variant_tokens & category_terms):
            priority += 1.0
        if object_terms and (variant_tokens & object_terms):
            priority += 1.0
        if variant_tokens & {"basic", "main", "major", "key", "primary", "principal"}:
            priority += 1.0
        if "these" in variant_tokens:
            priority += 0.5
        return (-priority, start)

    ordered_anchors = sorted(anchors, key=_anchor_priority)

    best_items: list[str] = []
    best_answer: str | None = None
    for start, end, variant in ordered_anchors[:24]:
        segment = prepared[max(0, start - 80): min(len(prepared), end + 1800)]
        relative_end = min(len(segment), (end - max(0, start - 80)))
        segment_after_anchor = segment[relative_end:]
        marker_patterns = (
            (r"(?:^|\s)(\d{1,2})\s*[.)]\s*(.*?)(?=(?:\s+\d{1,2}\s*[.)]\s*)|$)", "number"),
            (r"(?:^|\s)([A-Ea-e])\s*[.)]\s*(.*?)(?=(?:\s+[A-Ea-e]\s*[.)]\s*)|$)", "letter"),
        )
        for marker_pattern, marker_kind in marker_patterns:
            marker_matches = list(re.finditer(marker_pattern, segment_after_anchor, flags=re.DOTALL))
            if not marker_matches:
                continue
            items: list[str] = []
            expected_number = 1
            started = False
            for marker in marker_matches:
                try:
                    marker_number = int(marker.group(1)) if marker_kind == "number" else (ord(marker.group(1).lower()) - ord("a") + 1)
                except Exception:
                    continue
                if not started:
                    if marker_number != 1:
                        continue
                    started = True
                    expected_number = 1
                if marker_number != expected_number:
                    break
                expected_number += 1
                item = _clean_counted_list_label_item(marker.group(2) or "")
                if not _is_clean_counted_label_item(item):
                    break
                items.append(item)
                if count_target is not None and len(items) >= count_target:
                    break
            shaped_marker = _shape_counted_list_items(items)
            if shaped_marker is None:
                continue
            if count_target is not None and len(items) != count_target:
                continue
            if count_target is None and len(items) < 3:
                continue
            if len(items) > len(best_items):
                best_items = items
                best_answer = shaped_marker

        inline_intro = re.search(
            r"\b(?:which\s+are|are|include|includes|included\s+are|consist\s+of|consists\s+of)\s*[:\-]?\s*(.{8,360})",
            segment_after_anchor,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if inline_intro:
            inline_clause = inline_intro.group(1) or ""
            for inline_items in _split_counted_inline_clause_items(inline_clause, count_target):
                shaped_inline = _shape_counted_list_items(inline_items)
                if shaped_inline is None:
                    continue
                if count_target is not None and len(inline_items) != count_target:
                    continue
                if count_target is None and len(inline_items) < 3:
                    continue
                if len(inline_items) > len(best_items):
                    best_items = [_clean_counted_list_label_item(item) for item in inline_items]
                    best_answer = shaped_inline

    if len(best_items) < 2 or not best_answer:
        return None
    return best_answer

def _build_counted_list_rescue_context(
    query_text: str,
    query_info: dict[str, Any],
    anchor_doc: dict,
    all_chunks: list[dict],
    allowed_sources: Set[str],
) -> tuple[str, dict[str, Any]]:
    raw_anchor_text = str((anchor_doc or {}).get("page_content") or (anchor_doc or {}).get("text") or "")
    cleaned_anchor = _normalize_context_entities(query_text, _clean_ocr_artifacts(raw_anchor_text) or raw_anchor_text)
    if not _is_counted_category_list_query_info(query_info):
        focused_anchor = S._focus_doc_to_query_window(query_text, cleaned_anchor, window=900) or cleaned_anchor
        return focused_anchor, {"selected_chunk_indexes": [dict((anchor_doc or {}).get("metadata") or {}).get("chunk_index")], "merged_extra_chunks_count": 0}

    anchor_md = dict((anchor_doc or {}).get("metadata") or {})
    anchor_sources = S._metadata_source_keys(anchor_md) & allowed_sources
    try:
        raw_anchor_idx = anchor_md.get("chunk_index")
        if raw_anchor_idx is None:
            raise ValueError("missing chunk_index")
        anchor_idx = int(f"{raw_anchor_idx}")
    except Exception:
        anchor_idx = None
    if not anchor_sources or anchor_idx is None:
        focused_anchor = S._focus_doc_to_query_window(query_text, cleaned_anchor, window=1600) or cleaned_anchor
        return focused_anchor, {"selected_chunk_indexes": [anchor_md.get("chunk_index")], "merged_extra_chunks_count": 0}

    focus_terms = [
        _normalize_symbolic_list_surface(str(term))
        for term in (query_info.get("focus_terms") or [])
        if _normalize_symbolic_list_surface(str(term))
    ]
    phrase_variants = [
        _normalize_symbolic_list_surface(str(variant))
        for variant in (query_info.get("phrase_variants") or [])
        if _normalize_symbolic_list_surface(str(variant))
    ]

    selected: list[tuple[int, dict]] = []
    for chunk in all_chunks:
        metadata = dict((chunk or {}).get("metadata") or {})
        chunk_sources = S._metadata_source_keys(metadata)
        if not (chunk_sources & anchor_sources):
            continue
        try:
            raw_chunk_idx = metadata.get("chunk_index")
            if raw_chunk_idx is None:
                raise ValueError("missing chunk_index")
            chunk_idx = int(f"{raw_chunk_idx}")
        except Exception:
            continue
        distance = abs(chunk_idx - anchor_idx)
        if distance > 2:
            continue
        text = str((chunk or {}).get("page_content") or (chunk or {}).get("text") or "")
        normalized = _normalize_symbolic_list_surface(text)
        phrase_hit = any(re.search(rf"\b{re.escape(variant)}\b", normalized) for variant in phrase_variants if variant)
        focus_hits = sum(1 for term in dict.fromkeys(focus_terms) if term and _token_match_light(normalized, term))
        marker_hits = len(re.findall(r"(?:^|\s)\d{1,2}\s*[.)]\s*[A-Za-z]", _prepare_counted_list_rescue_text(text)))
        include_chunk = bool(
            distance == 0
            or (distance == 1 and (phrase_hit or focus_hits >= 1 or marker_hits >= 2))
            or (distance == 2 and phrase_hit and marker_hits >= 2)
        )
        if include_chunk:
            selected.append((chunk_idx, chunk))

    if not selected:
        selected = [(anchor_idx, anchor_doc)]
    selected = sorted(selected, key=lambda row: (abs(row[0] - anchor_idx), row[0]))[:3]
    selected.sort(key=lambda row: row[0])
    selected_indexes = [idx for idx, _ in selected]
    merged_text_parts: list[str] = []
    for _, chunk in selected:
        raw_text = str((chunk or {}).get("page_content") or (chunk or {}).get("text") or "")
        merged_text_parts.append(_normalize_context_entities(query_text, _clean_ocr_artifacts(raw_text) or raw_text))
    merged_text = "\n".join(part for part in merged_text_parts if part.strip())
    focused_text = merged_text if len(merged_text) <= 6500 else (S._focus_doc_to_query_window(query_text, merged_text, window=3200) or merged_text)
    return focused_text, {
        "selected_chunk_indexes": selected_indexes,
        "merged_extra_chunks_count": max(0, len(selected_indexes) - 1),
        "strict_adjacent_merge_allowed": 1.0 if len(selected_indexes) <= 3 else 0.0,
    }

def _symbolic_list_candidate_item_count(query_text: str, source_text: str) -> int:
    query_info = _detect_short_symbolic_list_query(query_text)
    counted_candidate = _extract_counted_list_labels_from_context(query_text, source_text, query_info)
    if counted_candidate:
        lines = [line for line in counted_candidate.splitlines() if re.match(r"^\s*[-•*]\s+", line)]
        if lines:
            return len(lines)
    candidates: list[str] = []
    try:
        context_candidate = _extract_list_from_context(query_text, source_text, max_candidate_blocks=2)
        if context_candidate:
            candidates.append(str(context_candidate))
    except Exception:
        pass
    if not candidates:
        try:
            simple_candidate = _extract_simple_list_from_docs([{"page_content": source_text, "text": source_text, "metadata": {}}], query_text=query_text)
            if simple_candidate:
                candidates.append(str(simple_candidate))
        except Exception:
            pass
    for candidate in candidates:
        lines = [line for line in candidate.splitlines() if re.match(r"^\s*[-•*]\s+", line)]
        if lines:
            return len(lines)
    return 0

def _score_symbolic_list_candidate(query_text: str, query_info: dict[str, Any], doc: dict) -> tuple[float, dict[str, Any]] | None:
    source_text = str((doc or {}).get("page_content") or (doc or {}).get("text") or (doc or {}).get("content") or "")
    if not source_text.strip():
        return None
    normalized_text = _normalize_symbolic_list_surface(source_text)
    phrase_variants = [variant for variant in (query_info.get("phrase_variants") or []) if str(variant or "").strip()]
    phrase_hits: list[str] = []
    phrase_positions: list[int] = []
    for variant in phrase_variants:
        normalized_variant = _normalize_symbolic_list_surface(str(variant))
        if not normalized_variant:
            continue
        phrase_re = re.compile(rf"(?:^|\s){re.escape(normalized_variant)}(?:\s|$)", flags=re.IGNORECASE)
        for match in phrase_re.finditer(normalized_text):
            phrase_hits.append(normalized_variant)
            phrase_positions.append(match.start())
            break
    focus_terms = [
        _normalize_symbolic_list_surface(str(term)) for term in (query_info.get("focus_terms") or [])
        if _normalize_symbolic_list_surface(str(term))
    ]
    focus_hits = 0
    for term in dict.fromkeys(focus_terms):
        if len(term) <= 2:
            if re.search(rf"(?:^|\s){re.escape(term)}(?:\s|$)", normalized_text):
                focus_hits += 1
        elif re.search(rf"\b{re.escape(term)}[a-z0-9']*\b", normalized_text):
            focus_hits += 1

    if not phrase_hits and focus_hits < 2:
        return None

    anchor_pos = min(phrase_positions) if phrase_positions else 0
    window_start = max(0, anchor_pos - 180)
    window_end = min(len(normalized_text), anchor_pos + 520)
    near_window = normalized_text[window_start:window_end]
    raw_lower = source_text.lower()
    raw_window = raw_lower[max(0, min(anchor_pos, len(raw_lower)) - 180): min(len(raw_lower), min(anchor_pos, len(raw_lower)) + 640)]

    colon_near = bool(re.search(r"[:;]", raw_window))
    introducer_near = bool(re.search(r"\b(?:include|includes|including|consists?\s+of|comprises?|classified\s+as|are|is)\b", near_window))
    comma_count = min(8, raw_window.count(","))
    bullet_count = min(8, len(re.findall(r"(?m)^\s*(?:[-•*]|\d+[.)]|[A-Za-z][.)])\s+", source_text)))
    inline_list_density = min(1.0, (comma_count + bullet_count) / 6.0)
    item_count = 0
    count_value = query_info.get("count")
    if phrase_hits:
        item_count = _symbolic_list_candidate_item_count(query_text, source_text)

    score = 0.0
    score += 9.0 if phrase_hits else 0.0
    score += min(3, len(set(phrase_hits))) * 1.5
    score += min(5, focus_hits) * 0.75
    score += 1.8 if colon_near else 0.0
    score += 1.2 if introducer_near else 0.0
    score += min(4, comma_count) * 0.65
    score += min(4, bullet_count) * 0.55
    score += inline_list_density * 1.5
    if isinstance(count_value, int) and count_value >= 2 and item_count == count_value:
        score += 4.0
    elif isinstance(count_value, int) and count_value >= 2 and item_count >= 2:
        score += 1.0

    if not phrase_hits and score < 4.0:
        return None
    return score, {
        "phrase_hits": float(len(set(phrase_hits))),
        "focus_hits": float(focus_hits),
        "colon_near": 1.0 if colon_near else 0.0,
        "introducer_near": 1.0 if introducer_near else 0.0,
        "comma_count": float(comma_count),
        "bullet_count": float(bullet_count),
        "item_count": float(item_count),
    }

def _lexical_rescue_symbolic_list_chunk(query_text: str, seed_docs: list[dict] | None = None) -> tuple[dict | None, dict[str, Any]]:
    query_info = _detect_short_symbolic_list_query(query_text)
    if not query_info:
        return None, {"detected": False, "reason": "not_symbolic_list_query"}
    counted_category_mode = _is_counted_category_list_query_info(query_info)

    S.logger.info(
        "[SYMBOLIC LIST QUERY DETECTED] query=%s phrase=%s kind=%s count=%s",
        str(query_text or "")[:180],
        str(query_info.get("phrase") or "")[:120],
        query_info.get("kind"),
        query_info.get("count"),
    )
    if counted_category_mode:
        S.logger.info(
            "[COUNTED LIST QUERY DETECTED] query=%s phrase=%s kind=%s count=%s category=%s object=%s",
            str(query_text or "")[:180],
            str(query_info.get("phrase") or "")[:120],
            query_info.get("kind"),
            query_info.get("count"),
            query_info.get("category_terms") or [],
            query_info.get("object_terms") or [],
        )
    allowed_sources = _symbolic_list_active_allowed_sources(seed_docs)
    if not allowed_sources:
        S.logger.info(
            "[LEXICAL RESCUE] query=%s phrase=%s candidates=0 chosen_chunk=None",
            str(query_text or "")[:180],
            str(query_info.get("phrase") or "")[:120],
        )
        if counted_category_mode:
            S.logger.info(
                "[COUNTED LIST RESCUE] query=%s phrase=%s candidates=0 chosen_chunk=None",
                str(query_text or "")[:180],
                str(query_info.get("phrase") or "")[:120],
            )
        return None, {"detected": True, "reason": "no_active_sources", "query_info": query_info, "candidates": 0}

    chunks = _mpc15_load_full_corpus_chunks()
    scored: list[tuple[float, dict, dict[str, Any]]] = []
    for chunk in chunks:
        metadata = dict((chunk or {}).get("metadata") or {})
        source_keys = S._metadata_source_keys(metadata)
        if not (source_keys & allowed_sources):
            continue
        scored_candidate = _score_symbolic_list_candidate(query_text, query_info, chunk)
        if scored_candidate is None:
            continue
        candidate_score, candidate_signals = scored_candidate
        if candidate_score <= 0.0:
            continue
        scored.append((candidate_score, chunk, candidate_signals))

    scored.sort(key=lambda row: row[0], reverse=True)
    chosen_doc: dict | None = None
    chosen_chunk: Any = None
    chosen_score = 0.0
    chosen_signals: dict[str, Any] = {}
    if scored:
        chosen_score, chosen_source_doc, chosen_signals = scored[0]
        metadata = dict((chosen_source_doc or {}).get("metadata") or {})
        focused_text, context_meta = _build_counted_list_rescue_context(
            query_text,
            query_info,
            chosen_source_doc,
            chunks,
            allowed_sources,
        )
        chosen_doc = {
            "page_content": focused_text,
            "text": focused_text,
            "content": focused_text,
            "metadata": metadata,
            "score": float(chosen_score),
            "_lexical_rescue_score": float(chosen_score),
            "_lexical_rescue_context_meta": context_meta,
        }
        chosen_signals = dict(chosen_signals or {})
        chosen_signals.update({
            "selected_chunks_count": float(len(context_meta.get("selected_chunk_indexes") or []) or 1),
            "merged_extra_chunks_count": float(context_meta.get("merged_extra_chunks_count", 0) or 0),
            "strict_adjacent_merge_allowed": float(context_meta.get("strict_adjacent_merge_allowed", 0.0) or 0.0),
        })
        chosen_chunk = metadata.get("chunk_index")

    S.logger.info(
        "[LEXICAL RESCUE] query=%s phrase=%s candidates=%s chosen_chunk=%s",
        str(query_text or "")[:180],
        str(query_info.get("phrase") or "")[:120],
        len(scored),
        chosen_chunk,
    )
    if counted_category_mode:
        S.logger.info(
            "[COUNTED LIST RESCUE] query=%s phrase=%s candidates=%s chosen_chunk=%s merged_extra=%s",
            str(query_text or "")[:180],
            str(query_info.get("phrase") or "")[:120],
            len(scored),
            chosen_chunk,
            int(float((chosen_signals or {}).get("merged_extra_chunks_count", 0.0) or 0.0)),
        )
    if chosen_doc is None or chosen_score < 8.0:
        return None, {
            "detected": True,
            "reason": "no_strong_lexical_candidate",
            "query_info": query_info,
            "candidates": len(scored),
            "chosen_chunk": chosen_chunk,
            "score": float(chosen_score),
        }
    return chosen_doc, {
        "detected": True,
        "reason": "candidate_selected",
        "query_info": query_info,
        "candidates": len(scored),
        "chosen_chunk": chosen_chunk,
        "score": float(chosen_score),
        "signals": chosen_signals,
    }

def _extract_symbolic_list_lexical_rescue_answer(query_text: str, seed_docs: list[dict] | None = None) -> tuple[str | None, int, dict | None, dict[str, Any], str]:
    rescued_doc, rescue_meta = _lexical_rescue_symbolic_list_chunk(query_text, seed_docs)
    query_info = dict(rescue_meta.get("query_info") or {}) if isinstance(rescue_meta, dict) else {}
    counted_category_mode = _is_counted_category_list_query_info(query_info)
    if rescued_doc is None:
        reason = str(rescue_meta.get("reason") or "no_candidate")
        if rescue_meta.get("detected"):
            S.logger.info("[LEXICAL RESCUE] accepted=False reason=%s", reason)
            if counted_category_mode:
                S.logger.info("[COUNTED LIST RESCUE] accepted=False reason=%s", reason)
        return None, 0, None, {}, reason

    rescue_text = str((rescued_doc or {}).get("page_content") or (rescued_doc or {}).get("text") or "")
    if not rescue_text.strip():
        S.logger.info("[LEXICAL RESCUE] accepted=False reason=empty_rescued_context")
        if counted_category_mode:
            S.logger.info("[COUNTED LIST RESCUE] accepted=False reason=empty_rescued_context")
        return None, 0, None, {}, "empty_rescued_context"

    rescue_support = _collect_local_window_support([rescued_doc])
    rescue_context_meta = dict((rescued_doc or {}).get("_lexical_rescue_context_meta") or {})
    rescue_selected_chunks = list(rescue_context_meta.get("selected_chunk_indexes") or [])
    rescue_support["selected_chunks_count"] = float(len(rescue_selected_chunks) or 1)
    rescue_support["merged_extra_chunks_count"] = float(rescue_context_meta.get("merged_extra_chunks_count", 0) or 0)
    rescue_support["strict_adjacent_merge_allowed"] = float(rescue_context_meta.get("strict_adjacent_merge_allowed", 0.0) or 0.0)
    rescue_support["used_single_window"] = 1.0
    rescue_support["validation_scope"] = "single_local_window"
    rescue_support["single_local_window_text"] = rescue_text[:7000] if counted_category_mode else rescue_text[:2400]
    rescue_support["lexical_rescue"] = 1.0
    if counted_category_mode:
        rescue_support["counted_list_rescue"] = 1.0
    rescue_signals = dict(rescue_meta.get("signals") or {})
    rescue_support["primary_phrase_hits"] = max(
        float(rescue_support.get("primary_phrase_hits", 0.0) or 0.0),
        float(rescue_signals.get("phrase_hits", 0.0) or 0.0),
    )
    rescue_support["primary_supp_list_evidence"] = max(
        float(rescue_support.get("primary_supp_list_evidence", 0.0) or 0.0),
        float(rescue_signals.get("colon_near", 0.0) or 0.0)
        + min(2.0, float(rescue_signals.get("comma_count", 0.0) or 0.0) / 3.0)
        + min(1.0, float(rescue_signals.get("bullet_count", 0.0) or 0.0) / 2.0),
    )

    rescue_candidates: list[str] = []
    counted_candidate = _extract_counted_list_labels_from_context(query_text, rescue_text, query_info)
    if counted_candidate:
        rescue_candidates.append(counted_candidate)
    for raw_candidate in (
        _extract_list_from_context(query_text, rescue_text, max_candidate_blocks=3),
        _extract_simple_list_from_docs([rescued_doc], query_text=query_text),
    ):
        candidate_text = str(raw_candidate or "").strip()
        if candidate_text:
            rescue_candidates.append(candidate_text)

    if not rescue_candidates:
        S.logger.info("[LEXICAL RESCUE] accepted=False reason=no_extractable_list")
        if counted_category_mode:
            S.logger.info("[COUNTED LIST RESCUE] accepted=False reason=no_extractable_list")
        return None, 0, None, {}, "no_extractable_list"

    last_reason = "coherence_failed"
    for candidate_text in rescue_candidates:
        rescue_ok, rescue_reason, rescue_shaped = _assess_list_coherence(
            query_text,
            _preclean_list_answer_for_assessment(candidate_text),
            strict_fast=True,
            local_support=rescue_support,
        )
        last_reason = str(rescue_reason or "coherence_failed")
        rescue_count = len([line for line in str(rescue_shaped or "").splitlines() if line.strip()])
        accepted = bool(rescue_ok and rescue_shaped and rescue_count >= 2)
        S.logger.info("[LEXICAL RESCUE] accepted=%s reason=%s", accepted, last_reason)
        if counted_category_mode:
            S.logger.info("[COUNTED LIST RESCUE] accepted=%s reason=%s", accepted, last_reason)
        if accepted:
            return rescue_shaped, rescue_count, rescued_doc, rescue_support, last_reason

    S.logger.info("[LEXICAL RESCUE] accepted=False reason=%s", last_reason)
    if counted_category_mode:
        S.logger.info("[COUNTED LIST RESCUE] accepted=False reason=%s", last_reason)
    return None, 0, None, {}, last_reason

def _doc_router_normalized_query_tokens(query_text: str) -> List[str]:
    q = re.sub(r"[^A-Za-z0-9\s'-]+", " ", str(query_text or "").lower())
    tokens: List[str] = []
    seen: Set[str] = set()
    for raw in re.findall(r"[a-z0-9][a-z0-9'-]*", q):
        cleaned = raw.strip("'-")
        if len(cleaned) < 2 or cleaned in _DOC_ROUTER_STOPWORDS:
            continue
        norm = _light_normalize_query_token(cleaned)
        if not norm or norm in _DOC_ROUTER_STOPWORDS or norm in seen:
            continue
        seen.add(norm)
        tokens.append(norm)
    return tokens[:12]

def _extract_doc_router_query_concepts(query_text: str) -> Tuple[List[str], List[str]]:
    q = re.sub(r"\s+", " ", str(query_text or "").strip().lower())
    query_tokens = _doc_router_normalized_query_tokens(q)
    comparison_intent = _doc_router_implies_comparison(q)
    if comparison_intent:
        query_tokens = [token for token in query_tokens if token not in _DOC_ROUTER_COMPARISON_OPERATORS]
    concepts: List[str] = []
    seen: Set[str] = set()

    boundary_re = re.compile(
        r"\b(?:of|during|about|regarding|concerning|between|among|versus|vs|against|while|when|where|"
        r"with|without|for|from|into|onto|and|or)\b",
        re.IGNORECASE,
    )
    for part in boundary_re.split(q):
        part_tokens = _doc_router_normalized_query_tokens(part)
        if comparison_intent:
            part_tokens = [token for token in part_tokens if token not in _DOC_ROUTER_COMPARISON_OPERATORS]
        if not part_tokens:
            continue
        phrase = " ".join(part_tokens[:5]).strip()
        if not phrase or phrase in seen:
            continue
        seen.add(phrase)
        concepts.append(phrase)

    if not concepts:
        concepts = list(query_tokens[:6])
    elif len(concepts) == 1 and len(query_tokens) > len(concepts[0].split()):
        for token in query_tokens:
            if token not in seen:
                seen.add(token)
                concepts.append(token)
            if len(concepts) >= 6:
                break

    return concepts[:6], query_tokens

def _doc_router_concept_hit(concept: str, text_l: str) -> bool:
    concept_tokens = [
        _light_normalize_query_token(t)
        for t in re.findall(r"[a-z0-9][a-z0-9'-]*", str(concept or "").lower())
    ]
    concept_tokens = [t for t in concept_tokens if t and t not in _DOC_ROUTER_STOPWORDS]
    if not concept_tokens or not text_l:
        return False
    if len(concept_tokens) > 1:
        phrase_re = r"\b" + r"\s+".join(re.escape(t) for t in concept_tokens) + r"\b"
        if re.search(phrase_re, text_l):
            return True
    token_hits = sum(1 for token in concept_tokens if _token_match_light(text_l, token))
    needed = 1 if len(concept_tokens) <= 2 else max(2, math.ceil(len(concept_tokens) * 0.60))
    return token_hits >= needed

def _doc_router_explicit_multi_source_request(query_text: str) -> bool:
    q = re.sub(r"\s+", " ", str(query_text or "").strip().lower())
    if not q:
        return False
    if _doc_router_cross_corpus_bridge(q):
        return False
    source_noun = r"(?:documents?|sources?|files?|pdfs?)"
    return bool(
        re.search(rf"\b(?:both|all|each|multiple|several)\s+{source_noun}\b", q)
        or re.search(rf"\b(?:combine|synthesi[sz]e|summari[sz]e|compare|merge)\b.{0,80}\b{source_noun}\b", q)
        or re.search(rf"\bacross\s+{source_noun}\b", q)
    )

def _doc_router_cross_corpus_bridge(query_text: str) -> bool:
    """Detect a synthesis/bridge query that should combine evidence from more
    than one source.

    Uses generic connective phrasing only — never specific domain, company or
    document names — so it triggers identically for any pair of uploaded PDFs.
    """
    q = re.sub(r"\s+", " ", str(query_text or "").strip().lower())
    if not q:
        return False
    return bool(
        re.search(
            r"\b(?:using|based on|drawing on|with reference to|referencing|according to)\b"
            r".{0,160}\b(?:explain|describe|analy[sz]e|apply|relate|connect|combine|"
            r"summari[sz]e|compare|contrast|discuss|evaluate)\b",
            q,
        )
        or re.search(
            r"\b(?:combine|synthesi[sz]e|integrate|connect|link|bridge|reconcile)\b"
            r".{0,80}\b(?:and|with|across|both|two|multiple|sources?|documents?|reports?|files?)\b",
            q,
        )
        or re.search(r"\bacross\b.{0,40}\b(?:documents?|sources?|reports?|files?|materials?)\b", q)
        or re.search(r"\b(?:both|two|multiple)\b.{0,40}\b(?:documents?|sources?|reports?|files?)\b", q)
    )

def _skip_deterministic_rag_shortcuts(query_text: str, doc_router_mode: str = "") -> bool:
    """Bypass extractor/fast-fail paths for synthesis, bridge, and formatted outputs."""
    if str(doc_router_mode or "") == "multi_source_synthesis":
        return True
    if _classify_response_format_intent(query_text) != "default":
        return True
    if _doc_router_cross_corpus_bridge(query_text):
        return True
    # Document-level summary/overview requests must skip the deterministic
    # definition/list extractors entirely and be answered by the grounded
    # generation path over the retrieved chunks.
    if _is_document_summary_query(query_text):
        return True
    q = re.sub(r"\s+", " ", str(query_text or "").strip().lower())
    docref = r"(?:the\s+)?(?:documents?|docs?|pdfs?|files?|books?|texts?|sources?|passages?|chapters?|sections?|materials?)"
    if re.match(rf"^\s*(?:please\s+)?(?:explain|describe|clarify)\s+.+\b(?:according\s+to|in|from|within)\s+{docref}\b", q):
        return True
    if re.match(rf"^\s*what\s+does\s+{docref}\s+(?:say|state|mention|discuss|explain|describe)\s+(?:about|regarding|concerning)\s+.+", q):
        return True
    return False

def _use_early_generation_shortcut(query_text: str, doc_router_mode: str = "") -> bool:
    """Use the compact generation path for bridge/explain queries; defer formatted outputs to WS streaming."""
    if not S._is_llm_generation_query(query_text):
        return False
    if _classify_response_format_intent(query_text) != "default":
        return False
    if _doc_router_cross_corpus_bridge(query_text):
        return True
    if str(doc_router_mode or "") == "multi_source_synthesis":
        return False
    return True

def _ensure_bridge_source_signals(query_text: str, answer_text: str) -> str:
    """Ensure a synthesis answer carries *some* source attribution, without
    naming any specific document or domain.

    The model is asked in the prompt to cite each source by the name shown in
    the context; here we only add a neutral, domain-agnostic lead-in when the
    answer contains no attribution cue at all.
    """
    ans = str(answer_text or "").strip()
    if not ans or not _doc_router_cross_corpus_bridge(query_text):
        return ans
    low = ans.lower()
    attribution_cues = (
        "document", "source", "report", "according to", "based on",
        "chapter", "section", "the uploaded", "the provided",
    )
    if any(cue in low for cue in attribution_cues):
        return ans
    return f"Based on the uploaded documents, {ans}"

def _classify_response_format_intent(query_text: str) -> str:
    q = re.sub(r"\s+", " ", str(query_text or "").strip().lower())
    if not q:
        return "default"
    if re.search(r"\b(?:act as|write a|draft a)\b.{0,80}\b(?:memo|memorandum)\b", q):
        return "executive_memo"
    if re.search(r"\b(?:multiple[- ]choice|mcq|quiz)\b", q) or (
        re.search(r"\bcreate a\b.{0,40}\bquiz\b", q) and re.search(r"\bquestion", q)
    ):
        return "quiz_generation"
    if re.search(r"\bsummari[sz]e\b", q) and re.search(r"\b(?:exactly|into)\s+(?:\d+|five|5)\s+bullet", q):
        return "extreme_summary"
    return "default"

def _is_kb_unanswerable_detail_query(query_text: str) -> bool:
    """Detect eval-style queries asking for details not present in uploaded PDFs."""
    q = re.sub(r"\s+", " ", str(query_text or "").strip().lower())
    if not q:
        return False
    # Generic "precise-detail" shapes that are prone to hallucination when the
    # exact figure/code is not in the uploaded text. No dataset, model or domain
    # is named — only the *form* of the request.
    if re.search(r"\b(?:mathematical\s+)?formula\b", q) and re.search(r"\b(?:coefficient|weight|intercept)\b", q):
        return True
    if re.search(r"\b(?:exact\s+)?(?:coefficient|weight|intercept)\b", q) and re.search(r"\b(?:value|equation|formula)\b", q):
        return True
    if re.search(r"\b(?:diagnostic|classification)\s+code\b", q):
        return True
    return False

def _enforce_unanswerable_detail_refusal(query: str, answer: str, language: str | None = None) -> str:
    """Replace hallucinated answers for known missing-detail queries with warm refusal."""
    if not _is_kb_unanswerable_detail_query(query):
        return answer
    ans = str(answer or "").strip()
    if not ans:
        return _not_found_response(query, "missing_detail")
    ans_l = ans.lower()
    # Generic fabricated-precision signals (coefficients/intercepts/codes) that
    # should not appear unless grounded. No specific dataset value is matched.
    forbidden = (
        re.search(r"β\s*\d", ans, re.I),
        re.search(r"coefficient\s*=\s*[-+]?\d\.\d+", ans, re.I),
        re.search(r"intercept\s*=\s*[-+]?\d\.\d+", ans, re.I),
    )
    warm_refusal_markers = (
        "not in the", "not found in", "do not have", "don't have", "does not contain",
        "doesn't contain", "no information", "not provided", "not available",
        "uploaded materials", "knowledge base", "provided text",
    )
    if any(forbidden) or not any(m in ans_l for m in warm_refusal_markers):
        return _not_found_response(query, "missing_detail")
    return answer

def _doc_router_implies_comparison(query_text: str) -> bool:
    q = re.sub(r"\s+", " ", str(query_text or "").strip().lower())
    if not q:
        return False
    if _is_definition_comparison_query(q):
        return False
    return bool(
        re.search(r"\b(?:difference|differences|distinction)\b", q)
        or re.search(r"\b(?:differentiate|distinguish)\s+between\b", q)
        or re.search(r"\b(?:compare|compared|comparison|contrast|contrasts)\b", q)
        or re.search(r"\b(?:relationship|relation)\b.+\bbetween\b.+\band\b", q)
        or re.search(r"\bhow\s+(?:does|do|is|are)\b.+\brelat(?:e|es|ed)\b.+\b(?:to|with)\b", q)
        or re.search(r"\b(?:versus|vs\.?)\b", q)
    )

def _doc_router_query_is_ambiguous(query_text: str, concepts: List[str], query_tokens: List[str], explicit_multi: bool) -> bool:
    if explicit_multi:
        return False
    if not query_tokens:
        return True
    if len(concepts or []) <= 1 and len(query_tokens) <= 2:
        return any(t in _DOC_ROUTER_VAGUE_TERMS for t in query_tokens)
    return False

def _doc_router_interleave_docs(
    doc_dicts: List[Dict[str, Any]],
    selected_sources: List[str],
    per_source_limit: int = 3,
    total_limit: int = 10,
) -> List[Dict[str, Any]]:
    selected_set = set(selected_sources or [])
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for doc in doc_dicts or []:
        source_key = S._doc_router_source_key(doc)
        if source_key in selected_set:
            grouped[source_key].append(doc)

    ordered: List[Dict[str, Any]] = []
    seen_ids: Set[int] = set()
    for round_idx in range(max(1, per_source_limit)):
        for source in selected_sources or []:
            candidates = grouped.get(source) or []
            if round_idx >= len(candidates):
                continue
            doc = candidates[round_idx]
            doc_identity = id(doc)
            if doc_identity in seen_ids:
                continue
            seen_ids.add(doc_identity)
            ordered.append(doc)
            if len(ordered) >= total_limit:
                return ordered
    return ordered

def _route_multi_document_evidence(query_text: str, doc_dicts: List[Dict[str, Any]]) -> Dict[str, Any]:
    safe_docs = S._filter_doc_dicts_to_active_sources(doc_dicts or [])
    concepts, query_tokens = _extract_doc_router_query_concepts(query_text)
    explicit_multi = _doc_router_explicit_multi_source_request(query_text)
    comparison_intent = _doc_router_implies_comparison(query_text)
    cross_corpus_bridge = _doc_router_cross_corpus_bridge(query_text)

    groups: Dict[str, List[Tuple[int, Dict[str, Any]]]] = defaultdict(list)
    source_display: Dict[str, str] = {}
    for rank, doc in enumerate(safe_docs):
        source_key = S._doc_router_source_key(doc)
        if not source_key or source_key == "unknown":
            continue
        groups[source_key].append((rank, doc))
        source_display.setdefault(source_key, S._doc_router_display_source(doc, source_key))

    stats: List[Dict[str, Any]] = []
    for source_key, ranked_docs in groups.items():
        scores = [S._doc_router_score(doc) for _, doc in ranked_docs]
        group_text_l = "\n".join(S._doc_router_text(doc)[:3500] for _, doc in ranked_docs[:8]).lower()
        token_hits = [token for token in query_tokens if _token_match_light(group_text_l, token)]
        concept_hits = [concept for concept in concepts if _doc_router_concept_hit(concept, group_text_l)]
        top_rank = min((rank for rank, _doc in ranked_docs), default=999)
        top_score = max(scores) if scores else 0.0
        avg_score = (sum(scores) / len(scores)) if scores else 0.0
        query_coverage = float(len(token_hits)) / max(1.0, float(len(query_tokens)))
        concept_coverage = float(len(concept_hits)) / max(1.0, float(len(concepts))) if concepts else 0.0
        rank_strength = 1.0 / (1.0 + float(top_rank))
        score_floor = max(0.0, top_score)
        router_score = (
            (3.0 * concept_coverage)
            + (1.5 * query_coverage)
            + (1.2 * rank_strength)
            + (0.20 * min(5.0, math.log1p(len(ranked_docs))))
            + (0.05 * score_floor)
        )
        stats.append({
            "source": source_key,
            "display_source": source_display.get(source_key, source_key),
            "top_score": float(top_score),
            "average_score": float(avg_score),
            "chunk_count": len(ranked_docs),
            "query_coverage": float(query_coverage),
            "concept_coverage": float(concept_coverage),
            "concept_hits": concept_hits,
            "token_hits": token_hits,
            "top_rank": int(top_rank),
            "router_score": float(router_score),
        })

    stats.sort(key=lambda row: (float(row.get("router_score", 0.0)), -int(row.get("top_rank", 999))), reverse=True)
    candidate_sources = [str(row.get("display_source") or row.get("source")) for row in stats]
    source_scores_log = {
        str(row.get("display_source") or row.get("source")): {
            "top_score": round(float(row.get("top_score") or 0.0), 4),
            "average_score": round(float(row.get("average_score") or 0.0), 4),
            "chunks": int(row.get("chunk_count") or 0),
            "query_coverage": round(float(row.get("query_coverage") or 0.0), 3),
            "concept_coverage": round(float(row.get("concept_coverage") or 0.0), 3),
            "concept_hits": list(row.get("concept_hits") or []),
        }
        for row in stats
    }

    mode = "single_source"
    reason = "single active retrieved source"
    selected_sources: List[str] = [str(stats[0].get("source"))] if stats else []

    if not stats:
        mode = "single_source"
        reason = "no verifiable active retrieved sources"
        selected_sources = []
    elif len(stats) == 1:
        mode = "single_source"
        reason = "only one verifiable source after active-source filtering"
    else:
        top = stats[0]
        second = stats[1]
        ambiguous = _doc_router_query_is_ambiguous(query_text, concepts, query_tokens, explicit_multi)
        top_cov = float(top.get("concept_coverage") or 0.0)
        second_cov = float(second.get("concept_coverage") or 0.0)
        top_query_cov = float(top.get("query_coverage") or 0.0)
        second_query_cov = float(second.get("query_coverage") or 0.0)
        top_router = float(top.get("router_score") or 0.0)
        second_router = float(second.get("router_score") or 0.0)
        top_concept_hits = set(top.get("concept_hits") or [])
        second_concept_hits = set(second.get("concept_hits") or [])
        top_token_hits = set(top.get("token_hits") or [])
        second_token_hits = set(second.get("token_hits") or [])

        def _concept_source_score(row: Dict[str, Any], concept: str) -> float:
            source_label = " ".join([
                str(row.get("source") or ""),
                str(row.get("display_source") or ""),
            ]).lower()
            label_bonus = 3.0 if _doc_router_concept_hit(concept, source_label) else 0.0
            return (
                label_bonus
                + (0.35 * float(row.get("top_score") or 0.0))
                + (0.75 * float(row.get("query_coverage") or 0.0))
                + (0.75 * float(row.get("concept_coverage") or 0.0))
                + (0.15 / (1.0 + float(row.get("top_rank") or 999)))
            )

        concept_best_sources: Dict[str, str] = {}
        for concept in concepts:
            concept_candidates = [row for row in stats if concept in set(row.get("concept_hits") or [])]
            if concept_candidates:
                concept_candidates = sorted(
                    concept_candidates,
                    key=lambda row: _concept_source_score(row, concept),
                    reverse=True,
                )
                concept_best_sources[concept] = str(concept_candidates[0].get("source"))
        union_concept_coverage = float(len(concept_best_sources)) / max(1.0, float(len(concepts))) if concepts else 0.0
        best_sources_for_concepts = list(dict.fromkeys(concept_best_sources.values()))
        second_has_meaningful_evidence = bool(
            second_router > 0.0
            and (
                second_cov >= max(0.34, min(0.75, top_cov * 0.70))
                or second_query_cov >= max(0.40, min(0.70, top_query_cov * 0.70))
                or bool(second_concept_hits)
            )
        )
        sources_overlap_query = bool(
            (top_concept_hits & second_concept_hits)
            or (top_token_hits & second_token_hits)
            or (second_cov >= 0.50)
            or (second_query_cov >= 0.50)
        )
        combined_top_two_concept_coverage = (
            float(len(top_concept_hits | second_concept_hits)) / max(1.0, float(len(concepts)))
            if concepts else 0.0
        )
        close_second_source = bool(
            top_router > 0.0
            and second_router >= (top_router * 0.82)
            and second_has_meaningful_evidence
            and sources_overlap_query
        )
        single_concept_competing_sources = bool(
            close_second_source
            and not explicit_multi
            and not comparison_intent
            and len(concepts or []) <= 1
            and len(query_tokens or []) <= 2
            and top_cov >= 0.50
            and second_cov >= 0.50
        )
        comparison_sources_are_strong = bool(
            comparison_intent
            and not ambiguous
            and len(stats) >= 2
            and second_has_meaningful_evidence
            and (
                (
                    len(best_sources_for_concepts) >= 2
                    and union_concept_coverage >= 0.75
                    and top_cov > 0.0
                    and second_cov > 0.0
                )
                or (
                    combined_top_two_concept_coverage >= 0.75
                    and top_cov > 0.0
                    and second_cov > 0.0
                )
                or (
                    close_second_source
                    and top_query_cov >= 0.34
                    and second_query_cov >= 0.34
                )
            )
        )

        bridge_sources_are_strong = False
        if cross_corpus_bridge and len(stats) >= 2:
            # The two highest-scoring distinct sources, whatever domains they are.
            s_top, s_second = stats[0], stats[1]
            top_ok = float(s_top.get("query_coverage") or 0.0) >= 0.10 or float(s_top.get("top_score") or 0.0) > 0.0
            second_ok = float(s_second.get("query_coverage") or 0.0) >= 0.10 or float(s_second.get("top_score") or 0.0) > 0.0
            bridge_sources_are_strong = bool(top_ok and second_ok)

        if bridge_sources_are_strong or (cross_corpus_bridge and len(stats) >= 2):
            # Synthesize across the two strongest distinct sources — no document
            # or domain is assumed, so this works for any pair of PDFs.
            selected_sources = [str(row.get("source")) for row in stats[:2]]
            mode = "multi_source_synthesis"
            reason = "cross-source synthesis query spanning the two strongest sources"
        elif comparison_sources_are_strong:
            if len(best_sources_for_concepts) >= 2 and union_concept_coverage >= 0.75:
                selected_sources = best_sources_for_concepts[:3]
            else:
                selected_sources = [str(row.get("source")) for row in stats[:2]]
            mode = "multi_source_synthesis" if len(selected_sources) > 1 else "single_source"
            reason = "comparison query has two strong active sources with query evidence"
        elif comparison_intent and len(stats) >= 2:
            selected_sources = [str(row.get("source")) for row in stats[:2]]
            mode = "clarification"
            reason = "comparison query lacks two strong grounded source matches"
        elif explicit_multi and len(stats) >= 2:
            selected_sources = [str(row.get("source")) for row in stats[: min(3, len(stats))]]
            mode = "multi_source_synthesis"
            reason = "explicit multi-source request with multiple active sources"
        elif ambiguous and (top_cov <= 0.75 or abs(top_router - second_router) < 1.25) and (second_cov > 0.0 or second_query_cov > 0.0):
            if cross_corpus_bridge or explicit_multi:
                selected_sources = [str(row.get("source")) for row in stats[: min(3, len(stats))]]
                mode = "multi_source_synthesis"
                reason = "bridge/multi-source query; synthesizing instead of clarifying"
            else:
                selected_sources = [str(row.get("source")) for row in stats[: min(3, len(stats))]]
                mode = "clarification"
                reason = "ambiguous query with multiple plausible active sources"
        elif top_cov >= 0.75 and (top_cov - second_cov >= 0.34 or top_router >= (second_router * 1.25) or second_query_cov < 0.25):
            selected_sources = [str(top.get("source"))]
            mode = "single_source"
            reason = "one source dominates and covers most query concepts"
        elif top_query_cov >= 0.60 and (top_query_cov - second_query_cov >= 0.35 or top_router >= (second_router * 1.30)):
            selected_sources = [str(top.get("source"))]
            mode = "single_source"
            reason = "one source has the strongest query coverage"
        elif single_concept_competing_sources:
            selected_sources = [str(row.get("source")) for row in stats[:2]]
            mode = "clarification"
            reason = "single-concept query has multiple close active sources"
        elif close_second_source:
            selected_sources = [str(top.get("source"))]
            mode = "single_source"
            reason = "close second source found, but query is not a comparison"
        elif second_cov > 0.0 and top_cov < 0.75 and union_concept_coverage > top_cov:
            selected_sources = [str(top.get("source"))]
            mode = "single_source"
            reason = "multiple sources cover concepts, but query is not a comparison"
        else:
            selected_sources = [str(top.get("source"))]
            mode = "single_source"
            reason = "preserving strongest single-source evidence"

    selected_docs = safe_docs
    if mode == "multi_source_synthesis":
        selected_docs = _doc_router_interleave_docs(safe_docs, selected_sources, per_source_limit=3, total_limit=10)
    elif mode == "single_source" and selected_sources:
        selected_docs = [doc for doc in safe_docs if S._doc_router_source_key(doc) == selected_sources[0]]

    selected_display = [source_display.get(src, src) for src in selected_sources]
    S.logger.info("[DOC ROUTER] candidate_sources=%s", candidate_sources)
    S.logger.info("[DOC ROUTER] source_scores=%s", json.dumps(source_scores_log, sort_keys=True))
    S.logger.info("[DOC ROUTER] query_concepts=%s", concepts)
    S.logger.info("[DOC ROUTER] selected_sources=%s", selected_display)
    S.logger.info("[DOC ROUTER] mode=%s", mode)
    S.logger.info("[DOC ROUTER] reason=%s", reason)

    return {
        "mode": mode,
        "reason": reason,
        "query_concepts": concepts,
        "query_tokens": query_tokens,
        "candidate_sources": candidate_sources,
        "selected_sources": selected_sources,
        "selected_display_sources": selected_display,
        "source_scores": source_scores_log,
        "docs": selected_docs,
    }

