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
from backend.retrieval.routing import _is_attribute_lookup_query
from backend.retrieval.routing import _is_support_procedural_query
from backend.retrieval.routing import _AR_EXPLANATION_QUERY_RE
from backend.retrieval.followup import _classify_memory_rewrite_intent
from backend.retrieval.routing import _classify_query_family_v2
from backend.retrieval.lists import _classify_response_format_intent
from backend.retrieval.routing import _compare_terms_from_query
from backend.retrieval.routing import _detect_fact_query_type
from backend.retrieval.lists import _doc_router_cross_corpus_bridge
from backend.retrieval.lists import _doc_router_implies_comparison
from backend.retrieval.routing import _has_english_keyword_overlap
from backend.retrieval.routing import _has_meaningful_context
from backend.retrieval.routing import _has_paragraph_prose_shape
from backend.utils.text import _is_arabic_text
from backend.retrieval.routing import _is_compare_query
from backend.retrieval.routing import _is_definition_comparison_query
from backend.retrieval.routing import _is_document_summary_query
from backend.retrieval.routing import _is_targeted_list_question
from backend.retrieval.routing import _is_weak_retrieval_evidence
from backend.rag_chunk_heuristics import looks_table_or_heading_like_chunk as _looks_table_or_heading_like_chunk
from backend.retrieval.routing import _normalize_query_for_router
from backend.retrieval.routing import _passes_hybrid_relevance_gate
from backend.retrieval.routing import _query_requires_structure
from backend.retrieval.routing import _query_tokens_for_evidence
import re as _re_mod
from backend.retrieval.routing import _retrieval_evidence_metrics
from backend.retrieval.routing import _strip_query_instruction_modifiers
import os
import re
import time

S = None


def bind_server(server) -> None:
    """Bind the live server module so extracted helpers can reach shared state."""
    global S
    S = server

os.environ['ANONYMIZED_TELEMETRY'] = 'False'

RAG_DOC_MODE: str = str(globals().get('RAG_DOC_MODE') or os.environ.get('RAG_DOC_MODE', 'multi'))

ARABIC_GENERAL_TOPICS = frozenset([
    'مرحبا', 'مرحباً', 'أهلاً', 'اهلا', 'السلام عليكم', 'كيف حالك', 'شكراً', 'شكرا',
    'وداعاً', 'مع السلامة', 'صباح الخير', 'مساء الخير'
])

def _is_arabic_small_talk(text: str) -> bool:
    """Return True if the Arabic text is a greeting/farewell/small talk."""
    t = text.strip().lower()
    if not t:
        return False

    # Normalize common punctuation for reliable matching.
    t_norm = _re_mod.sub(r"[?؟!.,،؛:\-\"']+", ' ', t)
    t_norm = _re_mod.sub(r'\s+', ' ', t_norm).strip()

    # Interrogative starters are likely real questions, not greetings.
    if any(t_norm.startswith(prefix) for prefix in ("مين", "من", "ما", "ماذا", "كيف", "ليش", "لماذا", "وين", "متى")):
        return False

    # Keep only pure courtesy/greeting tokens as small talk; mixed queries
    # like "مرحبا ما هو ..." must continue to the document router.
    return t_norm in {str(p).strip().lower() for p in ARABIC_GENERAL_TOPICS} | {"تمام"}

_AR_EN_CACHE_MAX = 512

_AR_NON_LLM_QUERY_CACHE_MAX = 512

_SIMPLE_RAG_CACHE_MAX = 256

_SIMPLE_RAG_CACHE_TTL_S = 120.0

def _current_doc_context_key() -> str:
    try:
        mode = str(S._active_doc_registry.get("mode", RAG_DOC_MODE))
    except Exception:
        mode = str(RAG_DOC_MODE)
    try:
        active_sources = sorted(S._get_active_sources())
    except Exception:
        active_sources = []
    return f"mode={mode}|sources={','.join(active_sources[:12])}"

def _set_last_latency_breakdown(
    connection_id: str,
    retrieval_ms: float,
    extraction_ms: float,
    validation_ms: float,
    llm_ms: float,
    total_ms: float,
    cache_hit: bool = False,
) -> None:
    if not connection_id:
        return
    S._LAST_LATENCY_BREAKDOWN[connection_id] = {
        "retrieval_ms": float(retrieval_ms),
        "extraction_ms": float(extraction_ms),
        "validation_ms": float(validation_ms),
        "llm_ms": float(llm_ms),
        "total_ms": float(total_ms),
        "cache_hit": bool(cache_hit),
    }

def _simple_rag_cache_get(query_text: str) -> "str | None":
    key = re.sub(r"\s+", " ", str(query_text or "")).strip().lower()
    if not key:
        return None
    cache_key = f"{key}||{_current_doc_context_key()}"
    row = S._SIMPLE_RAG_CACHE.get(cache_key)
    if row:
        ts = float(row.get("ts", 0.0) or 0.0)
        if (time.time() - ts) <= _SIMPLE_RAG_CACHE_TTL_S:
            S._SIMPLE_RAG_CACHE.move_to_end(cache_key)
            return str(row.get("answer") or "")
        S._SIMPLE_RAG_CACHE.pop(cache_key, None)
    return None

def _simple_rag_cache_put(query_text: str, answer_text: str) -> None:
    key = re.sub(r"\s+", " ", str(query_text or "")).strip().lower()
    if not key or not answer_text:
        return
    cache_key = f"{key}||{_current_doc_context_key()}"
    S._SIMPLE_RAG_CACHE[cache_key] = {"answer": str(answer_text), "ts": time.time()}
    S._SIMPLE_RAG_CACHE.move_to_end(cache_key)
    while len(S._SIMPLE_RAG_CACHE) > _SIMPLE_RAG_CACHE_MAX:
        S._SIMPLE_RAG_CACHE.popitem(last=False)

def _has_exact_phrase_and_grounding(query_text: str, docs: list[dict]) -> bool:
    if not query_text or not docs:
        return False
    q_low = re.sub(r"\s+", " ", str(query_text).strip().lower())
    if len(q_low) < 6:
        return False
    top_text = "\n".join(str((d or {}).get("text") or (d or {}).get("page_content") or "") for d in docs[:2]).lower()
    phrase_hit = q_low in re.sub(r"\s+", " ", top_text)
    if not phrase_hit:
        return False
    return _has_english_keyword_overlap(query_text, docs) and _passes_hybrid_relevance_gate(query_text, docs)

_PROTECTED_QUOTED_TERM_RE = re.compile(r"[\"'`“”‘’«»]\s*([^\"'`“”‘’«»]{2,80}?)\s*[\"'`“”‘’«»]")

_LATIN_PROPER_NAME_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:[A-Z][A-Za-z]+|[A-Z]{2,})(?:[\s\-]+(?:[A-Z][A-Za-z]+|[A-Z]{2,})){1,5}(?![A-Za-z0-9])"
)

def _looks_like_arabic_list_query(query_text: str) -> bool:
    if not _is_arabic_text(query_text):
        return False
    try:
        q = _normalize_query_for_router(query_text)
    except Exception:
        q = re.sub(r"\s+", " ", str(query_text or "").strip().lower())
    if not q:
        return False
    if re.match(r"^\s*(?:اذكر|عدد|استخرج|اعط|اعطني|قدم|هات)\b", q):
        return True
    if re.search(r"\b(?:قائمه|قائمة|عدد|تعداد|انواع|خطوات|عناصر|نقاط|اسباب|اهداف|وظائف|مراحل|اقسام|اجزاء)\b", q):
        return True
    if re.match(r"^\s*(?:ما|ماذا)\s+(?:هي|هى|هم|تكون)\b", q):
        return True
    return False

def _normalize_arabic_query_surface(query_text: str) -> str:
    text = re.sub(r"[\u064b-\u065f\u0670]", "", str(query_text or ""))
    text = text.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
    text = text.replace("ى", "ي").replace("ة", "ه")
    text = re.sub(r"[؟?.!،,؛;:\s]+", " ", text)
    return text.strip().lower()

def _classify_arabic_query_type(query_text: str) -> str:
    """Classify Arabic user intent before retrieval/translation.

    Returns one of: memory, explanation, direct. The labels are routing-only;
    answers still require retrieved evidence unless the user is explicitly
    asking to rewrite the previous grounded answer.
    """
    if not _is_arabic_text(query_text):
        return ""
    if _classify_memory_rewrite_intent(query_text):
        return "memory"
    normalized = _normalize_arabic_query_surface(query_text)
    if not normalized:
        return "direct"
    if _AR_EXPLANATION_QUERY_RE.search(normalized):
        return "explanation"
    if _looks_like_arabic_list_query(query_text) or _AR_DEFINITION_QUERY_RE.search(normalized):
        return "direct"
    return "direct"

def _native_arabic_retrieval_queries(query_text: str) -> list[str]:
    original = re.sub(r"\s+", " ", str(query_text or "").strip())
    if not original:
        return []
    queries: list[str] = [original]
    tokens = [tok for tok in _query_tokens_for_evidence(original) if _is_arabic_text(tok) and len(tok) >= 3]
    if tokens:
        unique_tokens: list[str] = []
        seen_tokens: set[str] = set()
        for token in tokens:
            key = token.casefold()
            if key and key not in seen_tokens:
                seen_tokens.add(key)
                unique_tokens.append(token)
        if len(unique_tokens) >= 2:
            queries.append(" ".join(unique_tokens[:4]))
            for idx in range(len(unique_tokens) - 1):
                queries.append(" ".join(unique_tokens[idx:idx + 2]))
        queries.extend(unique_tokens[:4])

    ordered: list[str] = []
    seen_queries: set[str] = set()
    for query in queries:
        cleaned = re.sub(r"\s+", " ", str(query or "").strip())
        key = cleaned.casefold()
        if cleaned and key not in seen_queries:
            seen_queries.add(key)
            ordered.append(cleaned)
        if len(ordered) >= 7:
            break
    return ordered

def _extract_protected_exact_query_terms(query_text: str) -> list[str]:
    raw = str(query_text or "")
    if not raw.strip():
        return []
    terms: list[str] = []

    def _add(value: str) -> None:
        term = re.sub(r"\s+", " ", str(value or "").strip(" \t\r\n.,;:!?؟،؛-"))
        if len(term) < 2:
            return
        if not re.search(r"[A-Za-z\u0600-\u06FF]", term):
            return
        key = term.casefold()
        if key not in {existing.casefold() for existing in terms}:
            terms.append(term)

    for match in _PROTECTED_QUOTED_TERM_RE.finditer(raw):
        _add(match.group(1))

    for match in _LATIN_PROPER_NAME_RE.finditer(raw):
        term = match.group(0)
        parts = re.findall(r"[A-Za-z][A-Za-z'.-]*", term)
        if len(parts) >= 2 or any(part.isupper() and len(part) > 1 for part in parts):
            _add(term)

    return terms[:4]

def _doc_text_for_exact_match(doc: dict) -> str:
    if not doc:
        return ""
    md = (doc or {}).get("metadata") or {}
    parts = [
        str((doc or {}).get("text") or ""),
        str((doc or {}).get("page_content") or ""),
        str((doc or {}).get("content") or ""),
        str(md.get("title") or ""),
        str(md.get("section") or ""),
        str(md.get("chapter") or ""),
    ]
    return "\n".join(part for part in parts if part)

def _doc_contains_exact_query_term(doc: dict, term: str) -> bool:
    haystack = _doc_text_for_exact_match(doc)
    needle = re.sub(r"\s+", " ", str(term or "").strip())
    if not haystack or not needle:
        return False
    if re.search(r"[A-Za-z]", needle):
        pattern = re.escape(needle).replace(r"\ ", r"\s+")
        return bool(re.search(rf"(?<![A-Za-z0-9]){pattern}(?![A-Za-z0-9])", haystack, flags=re.IGNORECASE))
    return needle.casefold() in haystack.casefold()

def _docs_contain_all_protected_terms(docs: list[dict], protected_terms: list[str]) -> bool:
    if not protected_terms:
        return True
    if not docs:
        return False
    return all(any(_doc_contains_exact_query_term(doc, term) for doc in docs) for term in protected_terms)

def _filter_docs_by_protected_terms(docs: list[dict], protected_terms: list[str]) -> list[dict]:
    if not protected_terms:
        return list(docs or [])
    return [doc for doc in (docs or []) if all(_doc_contains_exact_query_term(doc, term) for term in protected_terms)]

def _best_doc_rank_score(docs: list[dict]) -> float:
    scores: list[float] = []
    for doc in docs or []:
        for key in ("final_score", "score", "rerank_score"):
            if key not in (doc or {}):
                continue
            try:
                scores.append(float((doc or {}).get(key) or 0.0))
            except Exception:
                pass
            break
    return max(scores) if scores else 0.0

def _assess_native_arabic_retrieval(query_text: str, retrieved_docs: list[dict]) -> tuple[bool, str, dict]:
    docs = list(retrieved_docs or [])
    if not docs:
        return False, "weak_evidence", {
            "docs": 0.0,
            "best_score": 0.0,
            "coverage": 0.0,
            "focus_ratio": 0.0,
            "semantic_density": 0.0,
        }

    metrics = _retrieval_evidence_metrics(query_text, docs)
    docs_count = len(docs)
    best_score = float(metrics.get("max_similarity", 0.0) or 0.0)
    best_rank_score = _best_doc_rank_score(docs)
    coverage = float(metrics.get("coverage", 0.0) or 0.0)
    focus_ratio = float(metrics.get("focus_ratio", 0.0) or 0.0)
    semantic_density = 1.0 if _has_meaningful_context(docs) else 0.0
    has_positive_rerank = any(
        float((doc or {}).get("rerank_score", -999.0) or -999.0) > 0.0
        for doc in docs[:4]
    )
    protected_terms = _extract_protected_exact_query_terms(query_text)
    exact_protected_hit = _docs_contain_all_protected_terms(docs, protected_terms) if protected_terms else False
    family_v2 = _classify_query_family_v2(query_text)
    structure_query = _query_requires_structure(query_text) or family_v2 in {"list_entity", "toc_structure"} or _looks_like_arabic_list_query(query_text)
    weak_by_existing_gate = _is_weak_retrieval_evidence(query_text, family_v2, docs)

    rank_supported = bool(best_rank_score >= 0.0 or has_positive_rerank)
    strong_semantic = bool((best_score >= 0.22 and rank_supported) or has_positive_rerank)
    focused_lexical = bool(coverage >= 0.40 and focus_ratio > 0.0)
    structured_semantic = bool(
        structure_query
        and docs_count >= 3
        and semantic_density > 0.0
        and best_score >= 0.15
        and rank_supported
    )
    accepted = bool(
        (exact_protected_hit and semantic_density > 0.0)
        or (docs_count >= 2 and semantic_density > 0.0 and strong_semantic)
        or (semantic_density > 0.0 and focused_lexical)
        or structured_semantic
    )

    if weak_by_existing_gate and not (strong_semantic and semantic_density > 0.0) and not exact_protected_hit:
        accepted = False

    metrics.update({
        "docs": float(docs_count),
        "best_score": best_score,
        "best_rank_score": best_rank_score,
        "semantic_density": semantic_density,
        "positive_rerank": 1.0 if has_positive_rerank else 0.0,
        "protected_exact_hit": 1.0 if exact_protected_hit else 0.0,
    })
    return accepted, ("strong_evidence" if accepted else "weak_evidence"), metrics

def _translation_cache_get(ar_text: str) -> "str | None":
    key = ar_text.strip()
    if key in S._AR_EN_CACHE:
        S._AR_EN_CACHE.move_to_end(key)   # LRU: mark as recently used
        return S._AR_EN_CACHE[key]
    return None

def _translation_cache_put(ar_text: str, en_text: str) -> None:
    key = ar_text.strip()
    S._AR_EN_CACHE[key] = en_text
    S._AR_EN_CACHE.move_to_end(key)
    while len(S._AR_EN_CACHE) > _AR_EN_CACHE_MAX:
        S._AR_EN_CACHE.popitem(last=False)  # evict oldest

def _ar_non_llm_query_cache_key(query_text: str) -> str:
    return re.sub(r"\s+", " ", str(query_text or "").strip())

def _ar_non_llm_query_cache_get(query_text: str) -> Dict[str, Any] | None:
    key = _ar_non_llm_query_cache_key(query_text)
    if not key or key not in S._AR_NON_LLM_QUERY_CACHE:
        return None
    S._AR_NON_LLM_QUERY_CACHE.move_to_end(key)
    return dict(S._AR_NON_LLM_QUERY_CACHE[key])

def _ar_non_llm_query_cache_put(query_text: str, entry: Dict[str, Any]) -> None:
    key = _ar_non_llm_query_cache_key(query_text)
    if not key:
        return
    cached_entry = dict(entry or {})
    cached_entry["original_query"] = key
    S._AR_NON_LLM_QUERY_CACHE[key] = cached_entry
    S._AR_NON_LLM_QUERY_CACHE.move_to_end(key)
    while len(S._AR_NON_LLM_QUERY_CACHE) > _AR_NON_LLM_QUERY_CACHE_MAX:
        S._AR_NON_LLM_QUERY_CACHE.popitem(last=False)

def _ar_non_llm_query_cache_update_strength(
    original_query: str,
    retrieval_query: str,
    accepted: bool,
    reason: str,
    metrics: Dict[str, Any] | None,
) -> None:
    entry = _ar_non_llm_query_cache_get(original_query) or {
        "normalized_query": re.sub(r"\s+", " ", str(retrieval_query or "").strip()),
    }
    entry.update({
        "normalized_query": re.sub(r"\s+", " ", str(retrieval_query or "").strip()),
        "retrieval_accepted": bool(accepted),
        "retrieval_reason": str(reason or ""),
        "retrieval_metrics": dict(metrics or {}),
        "retrieval_strength_cached": True,
    })
    _ar_non_llm_query_cache_put(original_query, entry)

def _has_arabic_latin_token_mix(value: str) -> bool:
    s = str(value or "")
    if not s or not any("\u0600" <= ch <= "\u06FF" for ch in s):
        return False
    for token in re.findall(r"\S+", s):
        has_arabic = any("\u0600" <= ch <= "\u06FF" for ch in token)
        has_latin = any("a" <= ch.lower() <= "z" for ch in token)
        if has_arabic and has_latin:
            return True
    return False

def _is_clean_cached_arabic_translation(value: str, *, min_ar_chars: int = 3) -> bool:
    text = str(value or "").strip()
    if not text or text == "Not found in the document.":
        return False
    if "\ufffd" in text or re.search(r"[\ud800-\udfff]", text):
        return False
    if re.search(r"[\u2e80-\u2fff\u3000-\u9fff\uf900-\ufaff\ufe30-\ufe4f\uff00-\uffef]", text):
        return False
    if re.search(r"[A-Za-z]", text) or _has_arabic_latin_token_mix(text):
        return False
    arabic_chars = sum(1 for ch in text if "\u0600" <= ch <= "\u06FF")
    return arabic_chars >= int(min_ar_chars)

def _is_llm_generation_query(q: str) -> bool:
    q = re.sub(r"\s+", " ", str(q or "").strip().lower())
    if not q:
        return False

    # Document-level summary/overview questions are grounded generation
    # requests even when phrased as "what is this document about?". They
    # must short-circuit before the definition-style guard below so they
    # engage the summarization context/prompt instead of the definition path.
    if _is_document_summary_query(q):
        return True

    if re.match(r"^\s*(?:what\s+is|define|who\s+is|who\s+was)\b", q):
        return False

    if _classify_response_format_intent(q) != "default":
        return True
    if _doc_router_cross_corpus_bridge(q):
        return True

    generation_patterns = (
        r"\bsummarize\b",
        r"\bsummary\b",
        r"\bexplain\b",
        r"\bcompare\b",
        r"\bdifference\s+between\b",
        r"\bdescribe\b",
        r"\bin\s+simple\s+words\b",
        r"\bexplain\s+simply\b",
        r"\bmake\s+it\s+simple\b",
        r"\bsimplify\b",
        r"\bmake\s+it\s+easier\s+to\s+understand\b",
        r"\beasy\s+to\s+understand\b",
        r"\bhow would\b",
        r"\bhow should\b",
        r"\bimagine\b",
        r"\bact as\b",
        r"\bwrite a\b",
        r"\bcreate a\b.{0,40}\bquiz\b",
        r"\b(?:referencing|according to)\b.{0,80}\bchapter\b",
        r"\bcategorize\b",
        r"\bwhy must\b",
    )
    return any(re.search(pat, q) for pat in generation_patterns)

def _select_generation_context_docs(query_text: str, docs: list[dict], max_docs: int = 3) -> list[dict]:
    if not docs:
        return []

    q = re.sub(r"\s+", " ", str(query_text or "").strip().lower())
    stop = {
        "what", "is", "are", "the", "a", "an", "of", "in", "to", "for", "and", "or", "with", "on", "at",
        "summarize", "summary", "explain", "compare", "describe", "difference", "between", "simple", "simply",
        "sentence", "sentences", "document", "about", "tell",
    }
    query_tokens = [
        t for t in re.findall(r"[a-z0-9]{3,}", q)
        if t not in stop and not t.isdigit()
    ]
    is_document_summary = _is_document_summary_query(query_text)

    scored: list[tuple[float, dict]] = []
    for idx, d in enumerate(docs or []):
        txt_raw = str((d or {}).get("page_content") or (d or {}).get("text") or "")
        txt = txt_raw.lower().strip()
        if not txt:
            continue

        head = txt_raw[:1800]
        table_like_penalty = 0.35 if _looks_table_or_heading_like_chunk(head) else 0.0
        toc_like = bool(re.search(r"\b(table\s+of\s+contents|contents?|lesson\s+\d+|chapter\s+\d+)\b", txt[:1200]))
        toc_like_penalty = 0.0 if is_document_summary else (0.25 if toc_like else 0.0)
        structural_bonus = 0.0
        if is_document_summary:
            md = (d or {}).get("metadata") or {}
            role = str(md.get("chunk_role") or "").strip().lower()
            section_blob = " ".join(str(md.get(k) or "") for k in ("section", "title", "chapter")).lower()
            if role in {"toc", "introduction", "summary", "chapter_intro", "chapter_heading", "section_heading"}:
                structural_bonus += 0.9
            if "table of contents" in section_blob or "contents" in section_blob:
                structural_bonus += 0.8
            if "introduction" in section_blob or "overview" in section_blob or "learning objectives" in section_blob:
                structural_bonus += 0.6
            try:
                page_val = md.get("page")
                if page_val is not None and 0 < int(page_val) <= 5:
                    structural_bonus += 0.5
            except Exception:
                pass

        token_hits = sum(1 for t in query_tokens if re.search(rf"\b{re.escape(t)}\b", txt))
        overlap_ratio = (token_hits / max(1, len(query_tokens))) if query_tokens else 0.0
        def_signal = 1.0 if re.search(r"\b(is|refers\s+to|defined\s+as|means|includes|involves|focuses\s+on)\b", txt) else 0.0
        base_score = float((d or {}).get("score", 0.0) or 0.0)
        rank_penalty = 0.02 * idx
        final_score = (2.6 * overlap_ratio) + def_signal + structural_bonus + (0.4 * base_score) - rank_penalty - table_like_penalty - toc_like_penalty
        scored.append((final_score, d))

    if scored:
        scored.sort(key=lambda x: x[0], reverse=True)
        return [x[1] for x in scored[: max(1, int(max_docs or 3))]]

    return list((docs or [])[: max(1, int(max_docs or 3))])

def _select_list_context_docs(query_text: str, docs: list[dict], max_docs: int = 4, scan_limit: int = 12) -> list[dict]:
    if not docs:
        return []

    q = re.sub(r"\s+", " ", str(query_text or "").strip().lower())
    stop = {
        "what", "which", "who", "when", "where", "why", "how", "the", "this", "that", "these", "those",
        "is", "are", "was", "were", "be", "to", "of", "in", "on", "for", "and", "or", "with", "from",
        "a", "an", "do", "does", "did", "can", "could", "should", "would", "about", "main", "major", "only",
        "list", "name", "give", "mention", "identify", "describe", "explain", "document", "chapter",
        "section", "topics", "covered", "difference", "between", "compared", "compare",
    }
    query_tokens = [t for t in re.findall(r"[a-z0-9]{3,}", q) if t not in stop and not t.isdigit()]
    scan_docs = list((docs or [])[: max(1, min(int(scan_limit or 12), len(docs)))])

    def _structure_score(text: str) -> float:
        src = str(text or "")
        if not src.strip():
            return 0.0
        lines = [ln.strip() for ln in src.splitlines() if ln.strip()][:32]
        if not lines:
            return 0.0
        short_lines = sum(1 for ln in lines if len(re.findall(r"[A-Za-z][A-Za-z\-']*", ln)) <= 6)
        bullet_lines = sum(1 for ln in lines if re.match(r"^(?:[-•*]|\d+[.)])\s+", ln))
        repeated_sep_lines = sum(1 for ln in lines if re.search(r"\s{2,}|\b(?:and|or|,|;|:)\b", ln))
        comma_lists = sum(1 for ln in lines if ln.count(",") >= 2 or ln.count(";") >= 2)
        title_lines = sum(1 for ln in lines if re.match(r"^[A-Z][A-Za-z0-9\s\-]{3,120}$", ln))
        paragraph_penalty = 0.45 if _has_paragraph_prose_shape(src) else 0.0
        return (0.75 * bullet_lines) + (0.45 * short_lines) + (0.35 * repeated_sep_lines) + (0.35 * comma_lists) + (0.20 * title_lines) - paragraph_penalty

    scored: list[tuple[float, dict]] = []
    for idx, d in enumerate(scan_docs):
        txt_raw = str((d or {}).get("page_content") or (d or {}).get("text") or "")
        if not txt_raw.strip():
            continue
        txt = txt_raw.lower()
        md = dict((d or {}).get("metadata") or {})
        heading_blob = " ".join(str(md.get(k) or "") for k in ("heading", "section", "title", "chapter", "role")).lower()
        query_hits = sum(1 for tok in query_tokens if re.search(rf"\b{re.escape(tok)}\b", f"{heading_blob} {txt[:1600]}"))
        repeated_query_hits = sum(1 for tok in query_tokens if re.search(rf"\b{re.escape(tok)}\b.*\b{re.escape(tok)}\b", txt[:1600]))
        structure_score = _structure_score(txt_raw)
        base_score = float((d or {}).get("score", 0.0) or 0.0)
        score = (1.45 * query_hits) + (0.25 * repeated_query_hits) + structure_score + (0.35 * base_score) - (0.03 * idx)
        if _looks_table_or_heading_like_chunk(txt_raw[:1800]):
            score -= 0.20
        scored.append((score, d))

    if scored:
        scored.sort(key=lambda x: x[0], reverse=True)
        return [x[1] for x in scored[: max(1, int(max_docs or 4))]]

    return list(scan_docs[: max(1, int(max_docs or 4))])

def _rewrite_generation_query_for_grounded_llm(query_text: str) -> str:
    q = re.sub(r"\s+", " ", str(query_text or "").strip())
    q_low = q.lower()
    if not q:
        return q

    if re.search(r"\b(summarize|summary)\b", q_low):
        sentence_count_match = re.search(r"\bin\s+(\d+)\s+sentences?\b", q_low)
        sentence_count = sentence_count_match.group(1) if sentence_count_match else None
        topic = re.sub(r"\b(summarize|summary)\b", "", q, flags=re.IGNORECASE)
        topic = re.sub(r"\bin\s+\d+\s+sentences?\b", "", topic, flags=re.IGNORECASE)
        topic = _strip_query_instruction_modifiers(topic)
        topic = re.sub(r"\s+", " ", topic).strip(" .,:;!?-")
        if topic:
            if sentence_count:
                return f"Summarize {topic} in exactly {sentence_count} full sentences."
            return f"Summarize {topic} in 2-5 full sentences."

    if _is_compare_query(q):
        left, right = _compare_terms_from_query(q)
        if left and right:
            return (
                f"Compare {left} and {right} using bullet points only. "
                "Include clear points for each concept and one key difference."
            )
        return "Compare the concepts in the question using bullet points only."

    if re.search(r"\b(explain|describe)\b", q_low):
        topic = re.sub(r"\b(explain|describe)\b", "", q, flags=re.IGNORECASE)
        topic = _strip_query_instruction_modifiers(topic)
        topic = re.sub(r"\s+", " ", topic).strip(" .,:;!?-")
        if topic:
            return f"Explain {topic} in one short paragraph using full sentences."
    return q

def _is_generation_bypass_query(query_text: str) -> bool:
    q = re.sub(r"\s+", " ", str(query_text or "").strip().lower())
    if not q:
        return False
    return bool(
        re.search(
            r"\b(explain|describe|summarize|summary|in\s+simple\s+words|explain\s+simply|simplify|easy\s+to\s+understand|make\s+it\s+simple)\b",
            q,
        )
    )

def _format_generation_answer_by_query(query_text: str, answer_text: str) -> str:
    ans = str(answer_text or "").strip()
    if not ans:
        return RAG_NO_MATCH_RESPONSE
    if ans.lower() == RAG_NO_MATCH_RESPONSE.lower():
        return RAG_NO_MATCH_RESPONSE

    q_low = re.sub(r"\s+", " ", str(query_text or "").strip().lower())
    format_intent = _classify_response_format_intent(q_low)
    if format_intent == "extreme_summary":
        bullet_lines = [
            re.sub(r"^\s*(?:[-*•]+|\d+[.)])\s*", "", ln).strip()
            for ln in ans.splitlines()
            if ln.strip()
        ]
        if len(bullet_lines) < 5:
            sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", ans) if s.strip()]
            bullet_lines = [s for s in (bullet_lines or sents) if s]
        bullet_lines = bullet_lines[:5]
        while len(bullet_lines) < 5 and bullet_lines:
            bullet_lines.append(bullet_lines[-1])
        if bullet_lines:
            normalized: list[str] = []
            for item in bullet_lines[:5]:
                item = re.sub(r"\s+", " ", item).strip(" ,;:-")
                if item and not re.search(r"[.!?]\s*$", item):
                    item += "."
                if item:
                    normalized.append(f"- {item}")
            if len(normalized) >= 5:
                return "\n".join(normalized[:5])
    is_compare = _is_compare_query(q_low)
    is_summary = bool(re.search(r"\b(summarize|summary)\b", q_low)) and format_intent != "extreme_summary"
    is_explain = (not is_compare) and (not is_summary) and bool(re.search(r"\b(explain|describe)\b", q_low))

    def _sentences(text: str) -> list[str]:
        items = [s.strip() for s in re.split(r"(?<=[.!?])\s+", str(text or "").strip()) if s.strip()]
        if items:
            return items
        flat = re.sub(r"\s+", " ", str(text or "").strip())
        return [flat] if flat else []

    if is_compare:
        compare_text = str(ans)
        compare_text = re.sub(r"\s+-\s+", "\n- ", compare_text)
        raw_lines = [ln.strip() for ln in compare_text.splitlines() if ln.strip()]
        bullet_items: list[str] = []
        for ln in raw_lines:
            ln_clean = re.sub(r"^\s*(?:[-*•]+|\d+[.)])\s*", "", ln).strip()
            if not ln_clean:
                continue
            bullet_items.append(ln_clean)

        if len(bullet_items) < 2:
            bullet_items = _sentences(ans)

        if bullet_items:
            out_lines = []
            for item in bullet_items[:8]:
                item = re.sub(r"\s+", " ", item).strip()
                if not re.search(r"[.!?]\s*$", item):
                    item = item.rstrip(" ,;:-") + "."
                out_lines.append(f"- {item}")
            return "\n".join(out_lines)
        return ans

    if is_summary:
        sents = _sentences(ans)
        if len(sents) < 2:
            clauses = [c.strip() for c in re.split(r"\s*[;:]\s+", ans) if c.strip()]
            if len(clauses) >= 2:
                sents = clauses[:2]
        if len(sents) < 2:
            clauses = [c.strip() for c in re.split(r"\s*,\s+", ans) if c.strip()]
            if len(clauses) >= 2:
                sents = clauses[:2]
        if len(sents) < 2:
            m = re.search(r"\b(where|which|that|because)\b", ans, flags=re.IGNORECASE)
            if m and m.start() > 20:
                left = ans[: m.start()].strip(" ,;:-")
                right = ans[m.start():].strip(" ,;:-")
                if left and right:
                    sents = [left, right]
        if len(sents) > 5:
            sents = sents[:5]
        if not sents:
            return ans
        normalized_sents: list[str] = []
        for sentence in sents:
            sentence = re.sub(r"\s+", " ", sentence).strip()
            if not sentence:
                continue
            if not re.search(r"[.!?]\s*$", sentence):
                sentence = sentence.rstrip(" ,;:-") + "."
            normalized_sents.append(sentence)
        return " ".join(normalized_sents).strip() if normalized_sents else ans

    if is_explain:
        lines = [re.sub(r"^\s*(?:[-*•]+|\d+[.)])\s*", "", ln).strip() for ln in str(ans).splitlines() if ln.strip()]
        paragraph = " ".join(lines).strip() if lines else ans
        paragraph = re.split(r"\b(Copyright|Table of Contents)\b", paragraph, maxsplit=1, flags=re.IGNORECASE)[0]
        paragraph = re.sub(r"\s+", " ", paragraph).strip()
        exp_sents = _sentences(paragraph)
        if len(exp_sents) > 3:
            exp_sents = exp_sents[:3]
        if exp_sents:
            normalized_sents: list[str] = []
            for sentence in exp_sents:
                sentence = re.sub(r"\s+", " ", sentence).strip()
                if not sentence:
                    continue
                if not re.search(r"[.!?]\s*$", sentence):
                    sentence = sentence.rstrip(" ,;:-") + "."
                normalized_sents.append(sentence)
            if normalized_sents:
                return " ".join(normalized_sents)
        return paragraph

    return ans

def _resolve_grounded_answer_route(query_text: str) -> str:
    q = re.sub(r"\s+", " ", str(query_text or "").strip().lower())
    if not q:
        return "generic"
    if _is_attribute_lookup_query(query_text):
        return "attribute"
    if _detect_fact_query_type(query_text):
        return "fact"
    if _is_definition_comparison_query(query_text):
        return "definition"
    if _doc_router_implies_comparison(query_text):
        return "generic"
    if _is_targeted_list_question(q) or re.match(r"^\s*(?:what|which)\s+are\b", q):
        return "list"
    if _is_support_procedural_query(query_text):
        return "generic"
    if re.match(r"^\s*what\s+is\s+(?:the|your)\s+\w+(?:\s+\w+){0,3}\s+policy\b", q):
        return "generic"
    if q.startswith(("what is", "define", "who is", "who was", "who introduced", "meaning of")):
        return "definition"
    return "generic"

