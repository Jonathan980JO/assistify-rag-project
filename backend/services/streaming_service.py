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
from backend.core.config import FACT_CONTEXT_MAX_CHARS
from backend.core.config import FACT_CONTEXT_MAX_SNIPPETS
from backend.core.config import FACT_MAX_TOP_K
from backend.core.config import LLM_URL
from typing import List
from backend.core.config import MAX_FACT_RETRIES
from backend.core.config import OLLAMA_API_URL
from typing import Optional
from fastapi import WebSocket
from backend.services.rag_service import _ROUTER_DIRECT_ROUTES
from backend.retrieval.routing import _active_rag_search_async
from backend.retrieval.followup import _append_conversation_turn
from backend.retrieval.routing import _apply_concept_filter_to_docs
from backend.retrieval.routing import _apply_not_found_ux
from backend.retrieval.arabic import _ar_item_translation_cache_get
from backend.retrieval.arabic import _ar_item_translation_cache_put
from backend.retrieval.routing import _assess_list_coherence
from backend.retrieval.routing import _build_compact_fact_context_docs
from backend.retrieval.routing import _build_controlled_explanation_answer
from backend.retrieval.routing import _build_definition_entity_rescue_queries
from backend.retrieval.arabic import _build_external_arabic_explanation_query
from backend.retrieval.routing import _build_fact_rescue_queries
from backend.retrieval.arabic import _build_fast_arabic_explanation_query
from backend.retrieval.routing import _build_generation_context
from backend.retrieval.arabic import _build_llm_arabic_explanation_query
from backend.retrieval.routing import _build_strict_fact_system_prompt
from backend.retrieval.routing import _classify_query_family
from backend.retrieval.routing import _classify_query_family_v2
from backend.retrieval.routing import _classify_simple_recovery_query_type
from backend.retrieval.routing import _cleanup_definition_comparison_answer_text
from backend.retrieval.routing import _cleanup_final_answer_text
from backend.voice_audio.tts.streaming import client_tts_allowed as _client_tts_allowed
from backend.retrieval.routing import _collect_local_window_support
from backend.retrieval.routing import _compare_answer_from_docs
from backend.retrieval.routing import _compare_terms_from_query
from backend.retrieval.routing import _compose_grounded_generation_answer
from backend.core.tenant_context import _current_user_query
from backend.retrieval.routing import _customer_service_no_match_response
from backend.retrieval.routing import _dedup_docs_exact_text
from backend.retrieval.routing import _detect_fact_query_type
from backend.services.language_service import _detect_language
from backend.retrieval.routing import _direct_route_answer
from backend.retrieval.routing import _distance_threshold_for_query
from backend.retrieval.routing import _doc_has_explanation_for_entity
from backend.retrieval.routing import _enforce_definition_doc_contamination_guard
from backend.retrieval.routing import _enforce_runtime_answer_acceptance
from backend.retrieval.routing import _ensure_user_visible_support_answer
from backend.retrieval.routing import _evidence_concept_tokens
from backend.retrieval.routing import _extract_entity_from_definition_query
from backend.retrieval.routing import _extract_metric_fact_answer
from backend.retrieval.routing import _extract_strict_same_line_person_identity_from_retrieved_docs
from backend.retrieval.arabic import _final_ar_translation_cache_get
from backend.retrieval.arabic import _final_ar_translation_cache_put
from backend.retrieval.followup import _handle_followup_query
from backend.retrieval.followup import _handle_memory_rewrite_query
from backend.retrieval.routing import _has_english_keyword_overlap
from backend.retrieval.routing import _has_sufficient_context
from backend.retrieval.routing import _indirect_evidence_pool_is_weak
from backend.retrieval.routing import _infer_fact_context_mode_from_docs
from backend.retrieval.routing import _is_answer_grounded_in_docs
from backend.utils.text import _is_arabic_text
from backend.retrieval.arabic import _is_compact_arabic_item_translation
from backend.retrieval.routing import _is_compare_query
from backend.retrieval.routing import _is_controlled_definition_entity_query
from backend.retrieval.routing import _is_definition_style_query
from backend.retrieval.routing import _is_explanation_intent_query
from backend.retrieval.followup import _is_followup_query
from backend.retrieval.followup import _is_marked_arabic_resolved_followup
from backend.retrieval.followup import _is_memory_rewrite_query
from backend.retrieval.routing import _is_metric_fact_query, _is_attribute_lookup_query
from backend.retrieval.routing import _is_overview_query
from backend.retrieval.routing import _is_pure_smalltalk_query
from backend.retrieval.routing import _is_rag_no_match_sentinel
from backend.retrieval.routing import _is_safe_definition_fast_path_query
from backend.retrieval.routing import _is_simple_factual_text_query
from backend.retrieval.routing import _is_smalltalk
from backend.retrieval.routing import _is_structured_bullet_answer
from backend.retrieval.routing import _is_table_or_classification_sentence
from backend.retrieval.routing import _is_targeted_list_question
from backend.retrieval.routing import _is_wrong_concept_definition_chunk
from backend.retrieval.routing import _log_answer_mode_markers
from backend.retrieval.routing import _log_direct_route_handled
from backend.retrieval.routing import _log_selected_doc_markers
from backend.retrieval.routing import _looks_like_rag_no_match_stream
from backend.retrieval.routing import _max_doc_similarity
from backend.retrieval.arabic import _maybe_improve_arabic_translation_retrieval
from backend.retrieval.followup import _maybe_resolve_arabic_followup_reference
from backend.retrieval.followup import _maybe_rewrite_about_entity_question
from backend.retrieval.routing import _merge_rescue_docs_and_rerank
from backend.retrieval.routing import _normalize_definition_query_before_retrieval
from backend.retrieval.routing import _overview_seed_query
from backend.retrieval.arabic import _parse_bullet_list_items
from backend.retrieval.routing import _passes_hybrid_relevance_gate
from backend.retrieval.routing import _polish_final_response_text
from backend.retrieval.routing import _prepare_rag_doc_dicts_shared
from backend.retrieval.arabic import _preprocess_for_tts
from backend.retrieval.routing import _query_main_entity_tokens
from backend.retrieval.routing import _query_requires_structure
from backend.retrieval.routing import _rank_explanation_docs_for_query
import re as _re
import re as _re_mod
from backend.pdf_ingestion_rag import _repair_split_words
from backend.retrieval.routing import _rerank_document_summary_for_coverage
from backend.retrieval.routing import _rerank_docs_for_query_intent
from backend.services.language_service import _resolve_user_language
from backend.retrieval.routing import _retrieval_context_is_reliable
from backend.retrieval.routing import _retrieve_with_section_bias
from backend.retrieval.followup import _rewrite_bare_comparison_query_from_history
from backend.retrieval.routing import _route_response_language
from backend.retrieval.routing import _safe_grounded_concise_explanation_extraction
from backend.retrieval.arabic import _sanitize_arabic_text
from backend.retrieval.followup import _save_last_answer_state
from backend.retrieval.routing import _search_fast_definition_minimal_async
from backend.retrieval.routing import _select_document_summary_coverage_docs
from backend.retrieval.routing import _search_fast_minimal_async
from backend.retrieval.routing import _search_with_query_expansion
from backend.retrieval.routing import _select_fact_anchor_docs
from backend.retrieval.routing import _shared_rag_final_answer_decision
from backend.retrieval.routing import _shorten_arabic_spoken_answer
from backend.retrieval.routing import _smalltalk_response
from backend.retrieval.routing import _token_match_light
from backend.retrieval.arabic import _translation_retrieval_is_weak
from backend.retrieval.routing import _ws_fix_explanation_answer
from backend.adaptive_chunk_manager import adaptive_manager
import aiohttp
import asyncio
from backend.retrieval.routing import call_llm_with_context
from backend.voice_audio.tts.streaming import cancel_active_ws_tts
from backend.retrieval.routing import classify_query_route
from backend.retrieval.routing import collect_indirect_entity_evidence
from backend.retrieval.routing import count_token_matches
from backend.retrieval.routing import extract_keywords
from backend.retrieval.routing import is_entity_definition_like
import json
from backend.core.tenant_context import log_usage
import re
from backend.voice_audio.tts.streaming import remember_ws_tts_task
import time
import torch
from backend.retrieval.arabic import translate_with_llm
from backend.voice_audio.tts.streaming import tts_progressive_response
import uuid
from backend.voice_audio import state as voice_state

S = None


def bind_server(server) -> None:
    """Bind the live server module so extracted helpers can reach shared state."""
    global S
    S = server


def _phase14_trace_enabled(t_meta: Optional[dict]) -> bool:
    return bool(isinstance(t_meta, dict) and t_meta.get("phase14_trace"))


def _phase14_doc_text(doc: dict) -> str:
    if not isinstance(doc, dict):
        return ""
    return str(doc.get("text") or doc.get("page_content") or doc.get("content") or "")






def _should_apply_query_intent_rerank(family_v2: str) -> bool:
    return str(family_v2 or "") not in {
        "document_summary",
        "definition_entity",
        "definition_comparison",
        "list_entity",
        "explanatory_compare",
        "fact_entity",
        "attribute_lookup",
    }

def _retrieval_query_for_family(query_text: str, family_v2: str) -> str:
    if str(family_v2 or "") == "document_summary":
        return _overview_seed_query()
    return str(query_text or "")

def _phase14_doc_trace_rows(docs: list[dict] | None, *, limit: int = 8, preview_chars: int = 320) -> list[dict[str, Any]]:
    """Build bounded, evidence-only trace rows for Phase 14 validation.

    The rows intentionally include only source identity, page/section metadata,
    score, and a short text preview. They are used for diagnostics and do not
    influence retrieval, reranking, context selection, or generation.
    """
    rows: list[dict[str, Any]] = []
    for index, doc in enumerate(list(docs or [])[: max(0, int(limit or 0))], start=1):
        metadata = (doc or {}).get("metadata") or {}
        score = (doc or {}).get("rerank_score", (doc or {}).get("similarity", (doc or {}).get("score")))
        rows.append(
            {
                "rank": index,
                "id": (doc or {}).get("id"),
                "score": score,
                "source": metadata.get("source") or metadata.get("source_filename") or metadata.get("source_doc_id"),
                "filename": metadata.get("filename") or metadata.get("normalized_filename") or metadata.get("stored_filename"),
                "page": metadata.get("page"),
                "section": metadata.get("section"),
                "preview": _phase14_doc_text(doc)[: max(0, int(preview_chars or 0))],
            }
        )
    return rows

LLM_FALLBACK_TOTAL_TIMEOUT_S = 15.0

STREAM_TOTAL_TIMEOUT_S = 30.0

WS_FINALIZE_TIMEOUT_S = 10.0

_ARABIC_OPENER_PHRASES: List[str] = [
    "بناءً على المعلومات المتاحة،",
    "وفقاً لما لديّ من معلومات،",
    "استناداً إلى ما هو متاح،",
    "من خلال ما يتوفر لديّ،",
    "بحسب البيانات الموجودة،",
    "وفق ما أعرفه عن هذا،",
    "بناءً على السياق المتوفر،",
    "استناداً لما تم جمعه،",
    "من واقع المعلومات المتاحة،",
    "نظراً لما هو موجود من بيانات،",
]

_ARABIC_OPENER_PHRASE = _ARABIC_OPENER_PHRASES[0]  # backward-compat alias

ARABIC_OFF_TOPIC_RESPONSE = (
"عذراً، لا أستطيع الإجابة على هذا السؤال. أنا مساعد Assistify ومتخصص فقط في الخدمات "
"والمعلومات المتعلقة بالنظام. يمكنني مساعدتك في الأسئلة المتعلقة بالخدمات والمنتجات الموجودة "
"في قاعدة المعرفة."
)

_DETERMINISTIC_LIST_ANSWER_TYPES = frozenset({
    "deterministic_list",
    "list_deterministic_context",
    "list_fast_simple",
    "list_extractor",
    "list_extractor_override",
    "list_route_deterministic",
    "list_lexical_rescue",
    "controlled_explanation",
})

_DETERMINISTIC_DEFINITION_ANSWER_TYPES = frozenset({
    "definition_route_deterministic",
    "definition_fast_simple",
    "definition_fast_rescue_scored",
    "definition_extractor",
    "definition_extractor_override",
})

def _normalize_digits_for_tts(text: str) -> str:
    """Merge space-separated single-digit tokens into whole numbers,
    reassemble spaced decimal points, and attach currency symbols.

    Examples::

        "4 6 7 goals"     → "467 goals"
        "$ 3 9 . 9 9"     → "$39.99"
        "$ 0 . 9 9"       → "$0.99"
        "3 9 . 9 9 /month" → "39.99 /month"
        "2 1 3"           → "213"

    Applied only to text sent to XTTS — NOT to the displayed chat response.
    """
    import re as _re
    # 1) Merge isolated single-digit sequences: "3 9" → "39"
    text = _re.sub(
        r'\b(\d)\b(?: \b(\d)\b)+',
        lambda m: m.group(0).replace(' ', ''),
        text,
    )
    # 2) Merge spaced decimal points: "39 . 99" → "39.99"
    text = _re.sub(r'(\d) ?\. ?(\d)', r'\1.\2', text)
    # 3) Attach currency symbol to following number: "$ 39.99" → "$39.99"
    text = _re.sub(r'\$\s+(\d)', r'$\1', text)
    return text


def _phase14_trace_docs_for_fallback(timing: Optional[dict]) -> list[dict]:
    if not isinstance(timing, dict):
        return []
    rows = timing.get("phase14_selected_context") or timing.get("phase14_active_filtered_chunks") or timing.get("phase14_retrieved_chunks")
    if not isinstance(rows, list):
        return []
    docs: list[dict] = []
    for row in rows[:10]:
        if not isinstance(row, dict):
            continue
        preview = re.sub(r"\s+", " ", str(row.get("preview") or "").strip())
        if not preview:
            continue
        metadata = {
            "source": row.get("source"),
            "filename": row.get("filename"),
            "page": row.get("page"),
            "section": row.get("section"),
        }
        docs.append({"page_content": preview, "metadata": metadata})
    return docs


def _ws_generated_not_found_like(text: str) -> bool:
    low = str(text or "").strip().lower()
    if not low:
        return False
    return bool(
        "couldn't find" in low
        or "could not find" in low
        or "not found in the document" in low
        or re.search(r"\bnot\b.{0,100}\b(?:uploaded|help)\s+materials\b", low)
        or "request timed out" in low
    )

def _strip_mixed_not_found_preface(text: str) -> str:
    """Remove a false not-found preface while preserving generated evidence content."""
    raw = str(text or "").strip()
    if not raw or not _ws_generated_not_found_like(raw):
        return raw
    match = re.search(
        r"\b(?:however|but),?\s+(?=(?:based|here|the|this|retrieved|from)\b)",
        raw,
        flags=re.IGNORECASE,
    )
    if not match:
        return raw
    cleaned = raw[match.end():].strip(" \t\r\n:,-")
    if not cleaned:
        return raw
    if cleaned.lower().startswith("based"):
        cleaned = cleaned[:1].upper() + cleaned[1:]
    return cleaned

async def send_final_response(
    connection_id: str,
    text: str,
    language: str,
    tts_enabled: bool,
    *,
    websocket: Optional[WebSocket] = None,
    sources: int = 0,
    arabic_mode: bool = False,
    t_meta: Optional[dict] = None,
    branch: str = "unknown",
    send_chunk: bool = True,
    replace: bool = False,
    extra_payload: Optional[dict] = None,
    user_query: Optional[str] = None,
) -> None:
    """Send the final WS response and consistently attach TTS when enabled."""
    response_text = _repair_split_words(str(text or ""))
    response_text = _ensure_user_visible_support_answer(
        str(text or ""),
        user_query=user_query,
        language=language,
        arabic_mode=arabic_mode,
    )
    timing = t_meta if isinstance(t_meta, dict) else {}
    if user_query and _ws_generated_not_found_like(response_text):
        fallback_docs = _phase14_trace_docs_for_fallback(timing)
        if fallback_docs:
            repaired = _apply_not_found_ux(str(user_query or ""), response_text, fallback_docs, language)
            if repaired and not _ws_generated_not_found_like(repaired):
                response_text = repaired
        if _ws_generated_not_found_like(response_text):
            stripped = _strip_mixed_not_found_preface(response_text)
            if stripped and not _ws_generated_not_found_like(stripped):
                response_text = stripped
    ws = websocket or S._active_ws_connections.get(connection_id)
    if ws is None:
        S.logger.warning(
            "[TTS DECISION] branch=%s tts_enabled=%s triggered=False reason=no_websocket",
            branch,
            bool(tts_enabled),
        )
        return

    clean_text = response_text.strip()
    _raw_text_for_translation = clean_text

    def _has_arabic_latin_contamination(value: str) -> bool:
        s = str(value or "")
        if not s or not any("\u0600" <= ch <= "\u06FF" for ch in s):
            return False
        for token in re.findall(r"\S+", s):
            has_ar = any("\u0600" <= ch <= "\u06FF" for ch in token)
            has_latin = any(("a" <= ch.lower() <= "z") for ch in token)
            if has_ar and has_latin:
                return True
        return False

    def _has_non_arabic_script_contamination(value: str) -> bool:
        return bool(re.search(r"[\u0400-\u04FF\u3040-\u30FF\u3400-\u4DBF\u4E00-\u9FFF\uAC00-\uD7AF]", str(value or "")))

    def _pre_language_clean(value: str) -> tuple[str, bool]:
        s = str(value or "").strip()
        if not s:
            return "", False
        had_contamination = _has_arabic_latin_contamination(s)
        s = s.replace("\ufffd", " ")
        s = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", " ", s)
        s = re.sub(r"[\ud800-\udfff]", " ", s)
        s = re.sub(r"[\u2e80-\u2fff\u3000-\u9fff\uf900-\ufaff\ufe30-\ufe4f\uff00-\uffef]+", " ", s)
        if any("\u0600" <= ch <= "\u06FF" for ch in s):
            s = re.sub(r"(?<=[\u0600-\u06FF])[A-Za-z]+|[A-Za-z]+(?=[\u0600-\u06FF])", "", s)
            try:
                if branch == "controlled_explanation":
                    ar_lines = []
                    for line in re.split(r"\n+", s):
                        cleaned_line = _sanitize_arabic_text(line.strip())
                        cleaned_line = re.sub(r"\s+", " ", cleaned_line).strip()
                        if cleaned_line:
                            ar_lines.append(cleaned_line)
                    s = "\n".join(ar_lines)
                else:
                    s = _sanitize_arabic_text(s)
            except Exception:
                pass
        else:
            if branch == "controlled_explanation":
                lines = [line.strip() for line in re.split(r"\n+", s) if line.strip()]
                cleaned_lines: list[str] = []
                for line in lines:
                    try:
                        cleaned_line = _cleanup_final_answer_text(line)
                    except Exception:
                        cleaned_line = re.sub(r"\s+", " ", line).strip()
                    if cleaned_line:
                        cleaned_lines.append(cleaned_line)
                s = "\n".join(cleaned_lines) if cleaned_lines else re.sub(r"\s+", " ", s).strip()
            elif "definition_comparison" in str(branch or ""):
                try:
                    s = _cleanup_definition_comparison_answer_text(s)
                except Exception:
                    s = re.sub(r"\s+", " ", s).strip()
            else:
                try:
                    s = _cleanup_final_answer_text(s)
                except Exception:
                    s = re.sub(r"\s+", " ", s).strip()
        s = re.sub(r"[ \t]+", " ", s)
        s = re.sub(r" *\n *", "\n", s).strip()
        return s, bool(had_contamination)

    def _finalize_arabic_only(value: str) -> str:
        s = str(value or "").strip()
        if not s:
            return s
        try:
            if branch == "controlled_explanation":
                ar_lines = []
                for line in re.split(r"\n+", s):
                    cleaned_line = _sanitize_arabic_text(line.strip())
                    cleaned_line = re.sub(r"\s+", " ", cleaned_line).strip()
                    if cleaned_line:
                        ar_lines.append(cleaned_line)
                s = "\n".join(ar_lines)
            else:
                if _is_structured_bullet_answer(s):
                    ar_lines = []
                    for line in re.split(r"\n+", s):
                        prefix = "- " if re.match(r"^\s*(?:[-*\u2022]|\d+[.)])\s+", line) else ""
                        body = re.sub(r"^\s*(?:[-*\u2022]|\d+[.)])\s+", "", line).strip()
                        cleaned_line = _sanitize_arabic_text(body)
                        cleaned_line = re.sub(r"\s+", " ", cleaned_line).strip(" \t\r\n-،,.;:")
                        if cleaned_line:
                            ar_lines.append(f"{prefix}{cleaned_line}".strip())
                    s = "\n".join(ar_lines) if ar_lines else _sanitize_arabic_text(s)
                else:
                    s = _sanitize_arabic_text(s)
        except Exception:
            pass
        s = re.sub(r"[A-Za-z]+", " ", s)
        s = re.sub(r"\s+([،؛؟.!?,;:])", r"\1", s)
        s = re.sub(r"([،؛؟.!?,;:])\s*([،؛؟.!?,;:])", r"\1", s)
        s = re.sub(r"[ \t]+", " ", s)
        s = re.sub(r" *\n *", "\n", s)
        if _is_structured_bullet_answer(s):
            s = s.strip(" \t\r\n،,.;:")
        else:
            s = s.strip(" \t\r\n-،,.;:")
        if branch == "controlled_explanation" and "\n" not in s and len(s) > 180:
            parts = [part.strip() for part in re.split(r"(?<=[.!?\u061f])\s+", s) if part.strip()]
            if len(parts) >= 2:
                s = "\n".join(parts[:4])
        if _is_arabic_text(s):
            s = _shorten_arabic_spoken_answer("", s)
        return s

    async def _translate_to_arabic_external(value: str, source_lang: str) -> str:
        source_text = str(value or "").strip()
        if not source_text:
            return ""
        try:
            translator_cls = __import__("deep_translator", fromlist=["GoogleTranslator"]).GoogleTranslator
            source_code = "ar" if str(source_lang or "").lower() == "ar" else "en"
            translated = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: translator_cls(source=source_code, target="ar").translate(source_text),
            )
            translated = str(translated or "").strip()
            if not translated:
                return ""
            if (
                re.search(r"[A-Za-z]", translated)
                or _has_arabic_latin_contamination(translated)
                or _has_non_arabic_script_contamination(translated)
            ):
                return ""
            if sum(1 for c in translated if "\u0600" <= c <= "\u06FF") < 3:
                return ""
            return translated
        except Exception as exc:
            S.logger.info("[FINAL ANSWER TRANSLATION] external_fallback_failed err=%s branch=%s", exc, branch)
            return ""

    clean_text, _mixed_alpha_contamination = _pre_language_clean(clean_text)
    response_text = clean_text
    if _raw_text_for_translation and clean_text != _raw_text_for_translation:
        S.logger.info(
            "[OCR CLEANUP APPLIED] branch=%s before=%s | after=%s",
            branch,
            _raw_text_for_translation[:180],
            clean_text[:180],
        )

    # ---- FINAL ANSWER TRANSLATION GATE (Phase 7C — TASK 4) ----------------
    # Centralized post-processing: every final answer destined for an Arabic
    # user (`language == "ar"` or `arabic_mode=True`) must be in Arabic before
    # it is sent or spoken. Deterministic routes (definition / list /
    # comparison / follow-up / generation extractor) often produce English
    # text from English-translated retrieval queries; without this gate they
    # reach the WS as English even though the user typed Arabic.
    #
    # Rules (do not change):
    # - Translate ONLY when target language is "ar" and detected text is
    #   non-Arabic.
    # - Never translate the canonical sentinel "Not found in the document.";
    #   the existing Arabic fallback path handles its localized form.
    # - Translation runs through the existing `translate_with_llm` helper
    #   (no new model, no new prompt). Failure leaves the original text and
    #   logs `applied=False`.
    # - When translation succeeds, the WS chunk is sent with `replace=True`
    #   so any previously streamed English fragments from the LLM streaming
    #   branch are overwritten on the frontend.
    _translation_target = "ar" if (arabic_mode or str(language or "").lower() == "ar") else None
    _translation_applied = False
    _final_translation_t0 = time.perf_counter() if (_translation_target == "ar" and clean_text) else None
    _final_translation_cache_hit = False
    _ar_list_fast_path_applied = False
    _answer_type_for_cache = str(branch or "final").strip().lower() or "final"
    try:
        _grounded_source_count = int(sources or 0)
    except Exception:
        _grounded_source_count = 0
    _cache_eligible_for_final_answer = bool(_grounded_source_count > 0)

    # ---- Phase 10 — DETERMINISTIC ARABIC FAST PATH (lists) ----
    # If the already-grounded final answer is a bullet list and the target
    # language is Arabic, translate items individually with per-item caching
    # and rebuild Arabic bullets. This both:
    #   (a) preserves bullet formatting that the full-text LLM translation
    #       sometimes collapses into a single line, and
    #   (b) avoids a slow full-answer LLM round-trip on repeat asks because
    #       per-item Arabic translations are cached.
    # Generic — no topic, no domain dictionaries. Item text is whatever the
    # extractor already produced from real retrieved evidence.
    if (
        _translation_target == "ar"
        and clean_text
        and clean_text != "Not found in the document."
        and _cache_eligible_for_final_answer
        and _answer_type_for_cache in _DETERMINISTIC_LIST_ANSWER_TYPES
    ):
        _bullet_items = _parse_bullet_list_items(clean_text)
        if _bullet_items:
            _source_list_for_cache = _raw_text_for_translation or clean_text
            _cached_ar_list = _final_ar_translation_cache_get(
                _source_list_for_cache,
                "ar",
                _answer_type_for_cache,
            )
            _final_translation_cache_hit = _cached_ar_list is not None
            S.logger.info(
                "[AR TRANSLATION CACHE] hit=%s eligible=%s branch=%s list_fast_path=True",
                bool(_final_translation_cache_hit),
                bool(_cache_eligible_for_final_answer),
                branch,
            )
            if _cached_ar_list and _parse_bullet_list_items(_cached_ar_list):
                _cached_ar_list = _polish_final_response_text("", _cached_ar_list)
                response_text = _cached_ar_list
                clean_text = _cached_ar_list
                replace = True
                send_chunk = True
                _translation_applied = True
                _ar_list_fast_path_applied = True
                S.logger.info(
                    "[AR LIST FORMAT] applied=True items=%s branch=%s cache_hit=True",
                    len(_parse_bullet_list_items(_cached_ar_list)),
                    branch,
                )

            try:
                _pre_lang_for_list = _detect_language(clean_text)
            except Exception:
                _pre_lang_for_list = "en"
            # Only run the fast path when the source items contain Latin
            # letters (i.e. need translation). Already-Arabic bullet items
            # fall through to the existing finalize step.
            _needs_item_translation = any(
                re.search(r"[A-Za-z]", it) for it in _bullet_items
            ) or _pre_lang_for_list != "ar"
            if _needs_item_translation and not _ar_list_fast_path_applied:
                S.logger.info(
                    "[AR FAST PATH] deterministic=true items=%s branch=%s",
                    len(_bullet_items),
                    branch,
                )
                _translated_items: list[str] = []
                _all_items_ok = True
                _all_items_cached = True

                def _clean_ar_item_candidate(candidate: str) -> str:
                    cleaned = str(candidate or "").strip()
                    if not cleaned:
                        return ""
                    try:
                        cleaned = _sanitize_arabic_text(cleaned)
                    except Exception:
                        pass
                    cleaned = re.sub(r"[A-Za-z]+", " ", cleaned)
                    cleaned = re.sub(r"\s+", " ", cleaned).strip(" \t\r\n-،,.;:")
                    return cleaned

                def _is_clean_ar_item_translation(source_item: str, candidate: str) -> bool:
                    if branch == "controlled_explanation":
                        cleaned_candidate = str(candidate or "").strip()
                        return bool(
                            cleaned_candidate
                            and sum(1 for char in cleaned_candidate if "\u0600" <= char <= "\u06FF") >= 3
                            and not re.search(r"[A-Za-z]", cleaned_candidate)
                            and not _has_arabic_latin_contamination(cleaned_candidate)
                            and not _has_non_arabic_script_contamination(cleaned_candidate)
                        )
                    return _is_compact_arabic_item_translation(source_item, candidate)

                for _item in _bullet_items:
                    _cached_item = _ar_item_translation_cache_get(_item, "ar", "deterministic_list")
                    _item_hit = _cached_item is not None
                    S.logger.info(
                        "[AR ITEM TRANSLATION CACHE] hit=%s item_len=%s",
                        bool(_item_hit),
                        len(_item),
                    )
                    if _cached_item is not None:
                        _translated_items.append(_cached_item)
                        continue
                    _all_items_cached = False
                    _ar_item = await _translate_to_arabic_external(_item, "en")
                    _ar_item = _clean_ar_item_candidate(_ar_item)
                    if _is_clean_ar_item_translation(_item, _ar_item):
                        S.logger.info("[AR ITEM TRANSLATION] provider=external item_len=%s", len(_item))
                    else:
                        _ar_item = ""
                    try:
                        if not _ar_item:
                            _ar_item = await asyncio.wait_for(
                                translate_with_llm(_item, "en", "ar"),
                                timeout=12.0,
                            )
                    except Exception as _ex_item:
                        S.logger.info(
                            "[AR FAST PATH] item_translation_error err=%s item_len=%s",
                            _ex_item,
                            len(_item),
                        )
                        _all_items_ok = False
                        break
                    _ar_item = _clean_ar_item_candidate(_ar_item)
                    if not _is_clean_ar_item_translation(_item, _ar_item):
                        S.logger.info("[AR ITEM TRANSLATION] rejected_verbose_or_invalid=True item_len=%s", len(_item))
                    if not _is_clean_ar_item_translation(_item, _ar_item):
                        _all_items_ok = False
                        break
                    _translated_items.append(_ar_item)
                    _ar_item_translation_cache_put(_item, _ar_item, "ar", "deterministic_list")
                if _all_items_ok and _translated_items:
                    _ar_bullets = "\n".join(f"- {it}" for it in _translated_items)
                    _ar_bullets = _polish_final_response_text("", _ar_bullets)
                    response_text = _ar_bullets
                    clean_text = _ar_bullets
                    replace = True
                    send_chunk = True
                    _translation_applied = True
                    _ar_list_fast_path_applied = True
                    _final_translation_cache_hit = bool(_all_items_cached)
                    if _cache_eligible_for_final_answer:
                        _final_ar_translation_cache_put(
                            _source_list_for_cache,
                            _ar_bullets,
                            "ar",
                            _answer_type_for_cache,
                        )
                    S.logger.info(
                        "[AR LIST FORMAT] applied=True items=%s branch=%s",
                        len(_translated_items),
                        branch,
                    )

    if (
        _translation_target == "ar"
        and not _ar_list_fast_path_applied
        and clean_text
    ):
        try:
            _pre_lang = _detect_language(clean_text)
        except Exception:
            _pre_lang = "en"
        _is_sentinel = clean_text == "Not found in the document."
        _needs_arabic_rewrite = bool(
            _pre_lang != "ar"
            or _mixed_alpha_contamination
            or _has_arabic_latin_contamination(clean_text)
        )
        if _needs_arabic_rewrite and not _is_sentinel:
            try:
                _translation_input = _raw_text_for_translation or clean_text
                _cache_eligible = _cache_eligible_for_final_answer
                if _answer_type_for_cache in _DETERMINISTIC_DEFINITION_ANSWER_TYPES:
                    S.logger.info("[AR FAST PATH] deterministic=true branch=%s", branch)
                _cached_ar_translation = _final_ar_translation_cache_get(
                    _translation_input,
                    "ar",
                    _answer_type_for_cache,
                ) if _cache_eligible else None
                _final_translation_cache_hit = _cached_ar_translation is not None
                S.logger.info(
                    "[AR TRANSLATION CACHE] hit=%s eligible=%s branch=%s",
                    bool(_final_translation_cache_hit),
                    bool(_cache_eligible),
                    branch,
                )
                if _cached_ar_translation is not None:
                    _translated = _cached_ar_translation
                else:
                    _translated = await translate_with_llm(_translation_input, _pre_lang, "ar")
                _translated = (_translated or "").strip()
                _local_mixed_translation = bool(
                    re.search(r"[A-Za-z]", _translated)
                    or _has_arabic_latin_contamination(_translated)
                    or _has_non_arabic_script_contamination(_translated)
                )
                if _local_mixed_translation and not _final_translation_cache_hit:
                    _external_translated = await _translate_to_arabic_external(_translation_input, _pre_lang)
                    if _external_translated:
                        _translated = _external_translated
                        S.logger.info("[FINAL ANSWER TRANSLATION] external_fallback_applied=True branch=%s", branch)
                _ar_chars = sum(1 for c in _translated if "\u0600" <= c <= "\u06FF")
                if (
                    _translated
                    and _ar_chars >= 3
                    and _translated != clean_text
                    and not re.search(r"[A-Za-z]", _translated)
                    and not _has_arabic_latin_contamination(_translated)
                    and not _has_non_arabic_script_contamination(_translated)
                ):
                    try:
                        _translated = _sanitize_arabic_text(_translated)
                    except Exception:
                        pass
                    _translated = _finalize_arabic_only(_translated)
                    _ar_chars = sum(1 for c in _translated if "\u0600" <= c <= "\u06FF")
                    if _ar_chars < 3:
                        raise ValueError("arabic_translation_cleaned_empty")
                    _translated = _polish_final_response_text("", _translated)
                    response_text = _translated
                    clean_text = _translated.strip()
                    replace = True  # overwrite any prior streamed English
                    # Force chunk emission so the LLM-streaming path
                    # (which calls us with send_chunk=False because it
                    # streams its own English chunks live) still gets the
                    # corrected Arabic text on the frontend.
                    send_chunk = True
                    _translation_applied = True
                    if not _final_translation_cache_hit and _cache_eligible:
                        _final_ar_translation_cache_put(
                            _translation_input,
                            _translated,
                            "ar",
                            _answer_type_for_cache,
                        )
                    S.logger.info(
                        "[FINAL ANSWER TRANSLATION] source=%s target=ar applied=True branch=%s",
                        _pre_lang, branch,
                    )
                else:
                    S.logger.info(
                        "[FINAL ANSWER TRANSLATION] source=%s target=ar applied=False reason=invalid_translation branch=%s",
                        _pre_lang, branch,
                    )
            except Exception as _tx_err:
                S.logger.info(
                    "[FINAL ANSWER TRANSLATION] source=%s target=ar applied=False reason=exception err=%s branch=%s",
                    _pre_lang, _tx_err, branch,
                )
        else:
            S.logger.info(
                "[FINAL ANSWER TRANSLATION] source=%s target=ar applied=False reason=%s branch=%s",
                _pre_lang,
                ("sentinel" if _is_sentinel else "already_arabic"),
                branch,
            )

    if _translation_target == "ar" and clean_text and _final_translation_t0 is not None:
        final_translation_ms = int(round((time.perf_counter() - _final_translation_t0) * 1000))
        timing["final_translation_ms"] = final_translation_ms
        timing["final_translation_cache_hit"] = bool(_final_translation_cache_hit)
        S.logger.info(
            "[AR PERF] final_translation_ms=%s cache_hit=%s branch=%s",
            final_translation_ms,
            bool(_final_translation_cache_hit),
            branch,
        )

    if (
        _translation_target == "ar"
        and clean_text
        and clean_text != "Not found in the document."
        and any("\u0600" <= ch <= "\u06FF" for ch in clean_text)
    ):
        _arabic_only = _finalize_arabic_only(clean_text)
        if _arabic_only and _arabic_only != clean_text:
            response_text = _arabic_only
            clean_text = _arabic_only
            replace = True
            send_chunk = True
            S.logger.info("[ARABIC FINAL CLEAN] applied=True branch=%s", branch)

    already_triggered = bool(timing.get("xtts_send"))
    should_trigger = bool(tts_enabled and clean_text and not already_triggered)
    if should_trigger:
        reason = "enabled"
    elif already_triggered:
        reason = "already_triggered"
    elif not tts_enabled:
        reason = "disabled"
    else:
        reason = "empty_text"
    S.logger.info(
        "[TTS DECISION] branch=%s tts_enabled=%s triggered=%s reason=%s",
        branch,
        bool(tts_enabled),
        should_trigger,
        reason,
    )

    if send_chunk:
        chunk_payload = {
            "type": "aiResponseChunk",
            "text": response_text,
            "index": 0,
            "done": True,
            "timing": timing,
        }
        if replace:
            chunk_payload["replace"] = True
        await ws.send_json(chunk_payload)

    _tts_voice_language = language
    _tts_response_id = ""
    if should_trigger:
        timing.setdefault("xtts_send", time.perf_counter())
        timing["answer_chars"] = len(response_text or "")
        timing["async_tts_pending"] = True
        # ---- TTS LANGUAGE GATE (Phase 7C — TASK 3) ----
        # The voice used to read the answer must follow the actual answer-text
        # script, never the UI flag. Otherwise the Arabic Piper voice ends up
        # reading English (or vice versa). Generic — no domain content.
        try:
            _detected_answer_lang = _detect_language(clean_text)
        except Exception:
            _detected_answer_lang = language
        _tts_voice_language = language
        if _detected_answer_lang in ("ar", "en") and _detected_answer_lang != language:
            _tts_voice_language = _detected_answer_lang
            S.logger.info(
                "[TTS LANG CHECK] answer_language=%s requested_voice=%s selected_voice=%s overridden=True branch=%s",
                _detected_answer_lang, language, _tts_voice_language, branch,
            )
        else:
            S.logger.info(
                "[TTS LANG CHECK] answer_language=%s selected_voice=%s overridden=False branch=%s",
                _detected_answer_lang, _tts_voice_language, branch,
            )
        _tts_response_id = f"tts_{uuid.uuid4().hex[:10]}"

    if _translation_target == "ar":
        _request_start = timing.get("request_start")
        if _request_start:
            try:
                total_ar_ms = int(round((time.perf_counter() - float(_request_start)) * 1000))
                timing["total_arabic_backend_ms"] = total_ar_ms
                final_cache_hit = bool(timing.get("final_translation_cache_hit"))
                tts_cache_hit = bool(timing.get("tts_cache_hit"))
                query_cache_hit = bool(timing.get("query_translation_cache_hit"))
                S.logger.info("[AR PERF] total_ms=%s branch=%s", total_ar_ms, branch)
                S.logger.info(
                    "[AR PERF] cache_hit=%s final_translation_cache=%s tts_cache=%s query_translation_cache=%s branch=%s",
                    bool(final_cache_hit or tts_cache_hit or query_cache_hit),
                    final_cache_hit,
                    tts_cache_hit,
                    query_cache_hit,
                    branch,
                )
                timing["frontend_done_ms"] = total_ar_ms

                def _detail_ms(*keys, fallback=None):
                    for key in keys:
                        value = timing.get(key)
                        if value is None:
                            continue
                        try:
                            return int(round(float(value)))
                        except Exception:
                            continue
                    return fallback

                classification_ms = _detail_ms("ar_query_classification_ms")
                fast_query_ms = _detail_ms(
                    "ar_fast_query_ms",
                    "query_translation_ms",
                    fallback=0 if timing.get("query_translation_skipped") else None,
                )
                retrieval_ms = _detail_ms(
                    "ar_fast_retrieval_ms",
                    "retrieval_after_translation_ms",
                    "ar_native_retrieval_ms",
                    fallback=None,
                )
                answer_generation_ms = _detail_ms(
                    "answer_generation_ms",
                    "comparison_synthesis_ms",
                    "llm_generation_ms",
                )
                final_translation_ms = _detail_ms("final_translation_ms", fallback=0)
                tts_wait_ms = _detail_ms("tts_wait_ms", fallback=0)
                tts_synthesis_ms = _detail_ms("tts_synthesis_ms", "tts_ms", fallback=0)
                audio_bytes = int(timing.get("audio_bytes") or 0)
                answer_chars = len(response_text or "")
                timing["answer_chars"] = answer_chars
                S.logger.info(
                    "[PERF AR DETAIL] classification_ms=%s fast_query_ms=%s retrieval_ms=%s "
                    "answer_generation_ms=%s final_translation_ms=%s tts_wait_ms=%s "
                    "tts_synthesis_ms=%s audio_bytes=%s answer_chars=%s total_ms=%s "
                    "frontend_done_ms=%s query_cache_hit=%s final_translation_cache_hit=%s "
                    "tts_cache_hit=%s branch=%s",
                    classification_ms,
                    fast_query_ms,
                    retrieval_ms,
                    answer_generation_ms,
                    final_translation_ms,
                    tts_wait_ms,
                    tts_synthesis_ms,
                    audio_bytes,
                    answer_chars,
                    total_ar_ms,
                    total_ar_ms,
                    query_cache_hit,
                    final_cache_hit,
                    tts_cache_hit,
                    branch,
                )
            except Exception:
                pass

    done_payload = {
        "type": "aiResponseDone",
        "fullText": response_text,
        "sources": sources,
        "arabic_mode": arabic_mode,
        "timing": timing,
    }
    if should_trigger:
        done_payload["server_tts_pending"] = True
        done_payload["tts_response_id"] = _tts_response_id
    if extra_payload:
        done_payload.update(extra_payload)
    S.logger.info("[WS FINAL ANSWER BEFORE SEND] %s", response_text[:320])
    if should_trigger:
        S.logger.info(
            "[ASYNC TTS] aiResponseDone_before_tts_complete=True response_id=%s branch=%s",
            _tts_response_id,
            branch,
        )
    await ws.send_json(done_payload)

    if should_trigger:
        try:
            cancel_active_ws_tts(connection_id, "new_response")
            voice_state.ws_tts_active_response_ids[connection_id] = _tts_response_id
            cancel_event = interrupt_events.get(connection_id)
            task = asyncio.create_task(
                tts_progressive_response(
                    response_text,
                    ws,
                    connection_id,
                    _tts_voice_language,
                    _tts_response_id,
                    t_meta=timing,
                    cancel_event=cancel_event,
                )
            )
            remember_ws_tts_task(connection_id, _tts_response_id, task)
        except Exception as tts_err:
            S.logger.warning(
                "[TTS DECISION] branch=%s tts_enabled=%s triggered=True reason=async_tts_start_error error=%s",
                branch,
                bool(tts_enabled),
                tts_err,
            )

def _emit_perf_report(t_meta: dict, perf_start: float, query_text: str, answer_text: str, connection_id: str = "") -> None:
    """Print PERFORMANCE TIMING REPORT for any non-LLM answer path.

    The LLM streaming path has its own inline table; this helper covers every
    deterministic / extractor / not-found return that bypasses that inline table.
    Safe to call: wrapped entirely in try/except.
    """
    try:
        import time as _t
        t_now = _t.perf_counter()

        _req_start = t_meta.get("request_start") or perf_start
        _rt_start  = t_meta.get("routing_start") or perf_start
        _rt_end    = t_meta.get("routing_end")
        _rv_start  = t_meta.get("retrieval_start")
        _rv_end    = t_meta.get("retrieval_end")
        _rk_start  = t_meta.get("rerank_start")
        _rk_end    = t_meta.get("rerank_end")
        _cf_start  = t_meta.get("context_focus_start")
        _cf_end    = t_meta.get("context_focus_end")
        _xs_send   = t_meta.get("xtts_send")
        _xs_first  = t_meta.get("first_tts_chunk")
        _xs_last   = t_meta.get("xtts_last_chunk")

        def _ms(a, b, label="?"):
            """Compute (b-a) ms. Negative or invalid intervals → None + guard log."""
            if a is None or b is None:
                return None
            try:
                delta = (b - a) * 1000
            except Exception:
                return None
            if delta < 0:
                S.logger.warning(
                    "[PERF TIMER GUARD] corrected_negative_metric=%s value_ms=%.1f reason=end_before_start",
                    label, delta,
                )
                return None
            return int(round(delta))

        _p_routing   = _ms(_rt_start, _rt_end, "routing")
        _p_retrieval = _ms(_rv_start, _rv_end, "retrieval")
        _p_rerank    = _ms(_rk_start, _rk_end, "rerank")
        _p_focus     = _ms(_cf_start, _cf_end, "context_focus")
        _p_llm_ft    = None   # no LLM streaming on this path
        _p_llm_tot   = None   # no LLM streaming on this path
        _p_xtts_ft   = _ms(_req_start, _xs_first, "xtts_first") if _xs_first else None
        _p_xtts_tot  = _ms(_req_start, _xs_last, "xtts_total") if _xs_last else None
        _p_total_be  = _ms(_req_start, t_now, "total_backend")
        _p_total_au  = _ms(_req_start, _xs_last, "total_audio") if _xs_last else None

        def _fmt(v):
            return f"{v} ms" if v is not None else "N/A"

        _REQ_ID    = f"{connection_id} / msg_{abs(hash(query_text)) % 100000:05d}"
        _q_preview = (query_text or "")[:60]
        _ans_chars = len(answer_text or "")
        _audio_on  = bool(_xs_send)

        S.logger.info("=" * 60)
        S.logger.info("PERFORMANCE TIMING REPORT")
        S.logger.info(f"Request ID: {_REQ_ID}")
        S.logger.info(f'Query: "{_q_preview}"')
        S.logger.info(f"Answer chars: {_ans_chars}  |  Audio enabled: {_audio_on}")
        S.logger.info("=" * 60)
        S.logger.info(f"{'Stage':<30} {'Time':>10}")
        S.logger.info("-" * 60)
        S.logger.info(f"{'Routing':<30} {_fmt(_p_routing):>10}")
        S.logger.info(f"{'Retrieval':<30} {_fmt(_p_retrieval):>10}")
        S.logger.info(f"{'Reranking':<30} {_fmt(_p_rerank):>10}")
        S.logger.info(f"{'Context focus':<30} {_fmt(_p_focus):>10}")
        S.logger.info(f"{'LLM first token':<30} {_fmt(_p_llm_ft):>10}")
        S.logger.info(f"{'LLM total generation':<30} {_fmt(_p_llm_tot):>10}")
        S.logger.info(f"{'XTTS first audio':<30} {_fmt(_p_xtts_ft):>10}")
        S.logger.info(f"{'XTTS total audio':<30} {_fmt(_p_xtts_tot):>10}")
        S.logger.info(f"{'Frontend playback start':<30} {'N/A':>10}")
        S.logger.info("-" * 60)
        S.logger.info(f"{'Total backend response':<30} {_fmt(_p_total_be):>10}")
        S.logger.info(f"{'Total with audio':<30} {_fmt(_p_total_au):>10}")
        S.logger.info("=" * 60)

        def _c(v):
            return f"{v}ms" if v is not None else "N/A"
        S.logger.info(
            f"[PERF SUMMARY] query=\"{_q_preview}\" "
            f"routing={_c(_p_routing)} retrieval={_c(_p_retrieval)} rerank={_c(_p_rerank)} "
            f"focus={_c(_p_focus)} llm_first={_c(_p_llm_ft)} llm_total={_c(_p_llm_tot)} "
            f"xtts_first={_c(_p_xtts_ft)} xtts_total={_c(_p_xtts_tot)} "
            f"total_backend={_c(_p_total_be)} total_audio={_c(_p_total_au)}"
        )
        if t_meta.get("ar_query_type") or _is_arabic_text(query_text):
            def _meta_ms(*keys, fallback=None):
                for key in keys:
                    value = t_meta.get(key)
                    if value is None:
                        continue
                    try:
                        return int(round(float(value)))
                    except Exception:
                        continue
                return fallback

            _ar_class_ms = _meta_ms("ar_query_classification_ms")
            _ar_query_ms = _meta_ms("ar_fast_query_ms", "query_translation_ms", fallback=0 if t_meta.get("query_translation_skipped") else None)
            _ar_retrieval_ms = _meta_ms("ar_fast_retrieval_ms", "retrieval_after_translation_ms", "ar_native_retrieval_ms", fallback=_p_retrieval)
            _ar_final_translation_ms = _meta_ms("final_translation_ms", fallback=0 if answer_text == RAG_NO_MATCH_RESPONSE else None)
            _ar_tts_ms = _meta_ms("tts_ms", fallback=_p_xtts_tot)
            _ar_total_ms = _meta_ms("total_arabic_backend_ms", fallback=_p_total_be)
            S.logger.info(
                "[AR PERF SUMMARY] type=%s classification_ms=%s query_translation_or_search_ms=%s retrieval_ms=%s final_translation_ms=%s tts_ms=%s total_ms=%s",
                t_meta.get("ar_query_type") or "unknown",
                _c(_ar_class_ms),
                _c(_ar_query_ms),
                _c(_ar_retrieval_ms),
                _c(_ar_final_translation_ms),
                _c(_ar_tts_ms),
                _c(_ar_total_ms),
            )
    except Exception:
        S.logger.exception("[PERF REPORT] _emit_perf_report failed")

async def call_llm_streaming(websocket: WebSocket, text: str, connection_id: str, user, cancel_event: Optional[asyncio.Event] = None, t_meta=None, language: str = "en", client_tts_enabled: bool = True): # type: ignore
    """Stream LLM response with overlapping TTS via producer-consumer pipeline.

    Architecture:
    - LLM Producer: Streams tokens from Ollama, detects sentence boundaries,
      sends text chunks to browser for display, pushes sentences to TTS queue.
    - TTS Consumer: Reads sentences from queue, sends to XTTS microservice,
      streams PCM audio chunks back to browser via WebSocket binary frames.
    - Both run concurrently via asyncio.gather for maximum overlap.

    This eliminates the delay by starting TTS generation as soon as
    the first sentence is ready, while LLM continues generating more text.
    """
    import time
    _current_user_query.set(str(text or ""))
    effective_query_tts = _client_tts_allowed(client_tts_enabled)
    # ---- ABOUT-ENTITY STANDALONE REWRITE (run BEFORE the direct router) --
    # The direct router can mis-classify shapes like "وماذا عن X" or
    # "What about X?" as `unsupported_unclear` and short-circuit them. We
    # rewrite first so a real-entity question reaches the direct router (and
    # the follow-up router below) in canonical "What is X?" / "ما هي X؟" form.
    if not _is_memory_rewrite_query(text) and not _is_marked_arabic_resolved_followup(connection_id, text):
        text = _maybe_rewrite_about_entity_question(text)
    # ---- P12C-1: ARABIC FOLLOW-UP REFERENCE RESOLUTION (call_llm_streaming) ----
    try:
        if not _is_memory_rewrite_query(text):
            ar_resolved_s, ar_reason_s = _maybe_resolve_arabic_followup_reference(text, connection_id)
            if ar_resolved_s and ar_resolved_s != text:
                S.logger.info(
                    "[AR FOLLOWUP MEMORY] resolved_query=%s reason=%s original=%s",
                    ar_resolved_s[:200],
                    ar_reason_s,
                    (text or "")[:200],
                )
                text = ar_resolved_s
    except Exception:
        S.logger.exception("[AR FOLLOWUP MEMORY] call_llm_streaming resolution failed; continuing")
    # ---- MEMORY REWRITE ROUTE (highest priority) -----------------------
    # Summary/rephrase/simplify requests operate only on the last grounded
    # answer and must not enter translation, retrieval, reranking, or LLM gen.
    try:
        if _is_memory_rewrite_query(text) and _classify_query_family_v2(text) != "document_summary":
            mem_t0 = time.perf_counter()
            mem_t_meta = t_meta if isinstance(t_meta, dict) else {}
            mem_t_meta.setdefault("request_start", mem_t0)
            mem_t_meta["query_translation_ms"] = 0
            mem_t_meta["query_translation_skipped"] = True
            mem_t_meta["retrieval_after_translation_ms"] = 0
            mem_lang = _resolve_user_language(text, language)
            if mem_lang == "ar":
                mem_class_t0 = time.perf_counter()
                mem_type = S._classify_arabic_query_type(text)
                mem_t_meta["ar_query_type"] = mem_type
                mem_t_meta["ar_query_classification_ms"] = int(round((time.perf_counter() - mem_class_t0) * 1000))
                S.logger.info("[AR QUERY TYPE] type=%s", mem_type)
            mem_text, _mem_docs = await _handle_memory_rewrite_query(text, connection_id)
            mem_text = (mem_text or "").strip() or RAG_NO_MATCH_RESPONSE
            try:
                history = S.conversation_history[connection_id]
                history.append({"role": "user", "content": (text or "").strip()})
                history.append({"role": "assistant", "content": mem_text})
            except Exception:
                pass
            await send_final_response(
                connection_id,
                mem_text,
                "ar" if mem_lang == "ar" else XTTS_LANGUAGE,
                effective_query_tts,
                websocket=websocket,
                sources=0,
                arabic_mode=(mem_lang == "ar"),
                t_meta=mem_t_meta,
                branch="memory_rewrite_defensive",
            )
            _emit_perf_report(mem_t_meta, mem_t0, text, mem_text, connection_id)
            return
    except Exception:
        S.logger.exception("[MEMORY SUMMARY MODE] defensive route failed; continuing")
    # ---- PRE-RAG ROUTER (defensive for voice / non-typed callers) --------
    try:
        if text and len(str(text).strip()) >= 2:
            direct_route = classify_query_route(text)
            if direct_route in _ROUTER_DIRECT_ROUTES:
                route_t0 = time.perf_counter()
                route_lang = _route_response_language(text, language)
                direct_answer = _direct_route_answer(text, direct_route, route_lang)
                _log_direct_route_handled(direct_route, text, route_lang)
                if direct_answer == RAG_NO_MATCH_RESPONSE:
                    try:
                        _save_last_answer_state(connection_id, text, direct_answer, [])
                    except Exception:
                        S.logger.exception("[FOLLOWUP] save state failed (WS defensive direct not-found)")
                try:
                    _append_conversation_turn(connection_id, text, direct_answer)
                except Exception:
                    pass
                route_t_meta = t_meta if isinstance(t_meta, dict) else {}
                route_t_meta.setdefault("request_start", route_t0)
                response_tts_lang = "ar" if (route_lang == "ar" and direct_route != "unsupported_unclear") else XTTS_LANGUAGE
                await send_final_response(
                    connection_id,
                    direct_answer,
                    response_tts_lang,
                    effective_query_tts,
                    websocket=websocket,
                    sources=0,
                    arabic_mode=(route_lang == "ar" and direct_route != "unsupported_unclear"),
                    t_meta=route_t_meta,
                    branch=f"router_{direct_route}",
                )
                try:
                    log_usage(
                        username=(user or {}).get("username", "unknown"),
                        user_role=(user or {}).get("role", "unknown"),
                        query_text=text,
                        response_status="success",
                        error_message=None,
                        response_time_ms=int((time.perf_counter() - route_t0) * 1000),
                        rag_docs_found=0,
                        query_length=len(str(text or "").strip()),
                        response_length=len(direct_answer or ""),
                    )
                except Exception:
                    pass
                _emit_perf_report(route_t_meta, route_t0, text, direct_answer, connection_id)
                return
    except Exception:
        S.logger.exception("[ROUTER] defensive direct route failed; continuing")

    if S._is_kb_unanswerable_detail_query(text):
        refusal = _customer_service_no_match_response(text, language)
        try:
            await send_final_response(
                connection_id,
                refusal,
                "ar" if language == "ar" else XTTS_LANGUAGE,
                effective_query_tts,
                websocket=websocket,
                sources=0,
                arabic_mode=(language == "ar"),
                t_meta=t_meta,
                branch="unanswerable_detail_refusal",
                user_query=text,
            )
        except Exception:
            pass
        return

    # ---- DEFENSIVE FOLLOW-UP GUARD (after direct router) -----------------
    # If a follow-up query somehow reached call_llm_streaming despite the
    # WS entrypoint routing, intercept here BEFORE the [FLOW] entering log
    # is emitted, so the log can never falsely indicate that a follow-up
    # entered the heavy RAG path.
    try:
        if _is_followup_query(text, connection_id) and not _is_marked_arabic_resolved_followup(connection_id, text):
            S.logger.error("🔥 FOLLOWUP ROUTE TRIGGERED (defensive in call_llm_streaming)")
            S.logger.info("[FOLLOWUP] WS follow-up detected (defensive): '%s'", (text or "")[:80])
            fu_t0 = time.perf_counter()
            fu_text, _fu_docs = await _handle_followup_query(text, connection_id)
            fu_text = (fu_text or "").strip() or RAG_NO_MATCH_RESPONSE
            try:
                history = S.conversation_history[connection_id]
                history.append({"role": "user", "content": (text or "").strip()})
                history.append({"role": "assistant", "content": fu_text})
            except Exception:
                pass
            try:
                fu_t_meta = t_meta or {"request_start": fu_t0}
                await send_final_response(
                    connection_id,
                    fu_text,
                    "ar" if language == "ar" else XTTS_LANGUAGE,
                    effective_query_tts,
                    websocket=websocket,
                    sources=0,
                    arabic_mode=(language == "ar"),
                    t_meta=fu_t_meta,
                    branch="followup_defensive",
                )
                _emit_perf_report(fu_t_meta, fu_t0, text, fu_text, connection_id)
            except Exception:
                pass
            S.logger.info("[FOLLOWUP] WS follow-up answered (defensive) in %.0fms", (time.perf_counter() - fu_t0) * 1000.0)
            S.logger.error("🔥 FOLLOWUP ROUTE COMPLETE (defensive in call_llm_streaming)")
            return
    except Exception:
        S.logger.exception("[FOLLOWUP] defensive guard in call_llm_streaming failed; continuing")

    start_time = time.time()
    S.logger.info("[FLOW] entering call_llm_streaming")
    S.logger.info("[UI PATH ENTER] connection_id=%s", connection_id)
    S.logger.info("[FLOW] query_before = %s", (text or "")[:400])
    perf_start = time.perf_counter()
    vram_llm_before = 0
    if torch.cuda.is_available():
        vram_llm_before = torch.cuda.memory_reserved(0) / 1024**2
    
    t_meta = t_meta or {}
    _forced_final_language = str(t_meta.get("force_final_language") or "").strip().lower()
    t_meta["routing_start"] = perf_start  # routing starts at function entry
    t_meta["llm_send"] = perf_start
    t_meta["vram_llm_before"] = vram_llm_before
    if not text or len(text.strip()) < 2:
        try:
            await send_final_response(
                connection_id,
                "I didn't catch that. Could you repeat?",
                XTTS_LANGUAGE,
                effective_query_tts,
                websocket=websocket,
                sources=0,
                arabic_mode=False,
                t_meta=t_meta,
                branch="empty_query",
            )
        except Exception:
            pass
        return

    if _is_smalltalk(text):
        short_answer = _smalltalk_response(text)
        try:
            await send_final_response(
                connection_id,
                short_answer,
                XTTS_LANGUAGE,
                effective_query_tts,
                websocket=websocket,
                sources=0,
                arabic_mode=False,
                t_meta=t_meta,
                branch="smalltalk",
            )
        except Exception:
            pass
        return

    # NOTE: Follow-up / explanation routing happens in the DEFENSIVE GUARD
    # at the very top of this function (before [FLOW] entering log) and at
    # the WS entrypoint. Do NOT add another follow-up branch here — it
    # would be unreachable code.

    history_snapshot = list(S.conversation_history.get(connection_id, []) or [])
    rewritten_comparison_query = _rewrite_bare_comparison_query_from_history(text, history_snapshot, connection_id)
    if rewritten_comparison_query and rewritten_comparison_query != text:
        S.logger.info(
            "[COMPARE FOLLOWUP REWRITE] original=%r rewritten=%r",
            (text or "")[:160],
            rewritten_comparison_query[:160],
        )
        text = rewritten_comparison_query

    original_query_text = text
    is_generation_query_requested = S._is_llm_generation_query(original_query_text)
    is_fact_query_early = _classify_query_family_v2(text) in {"fact_entity", "attribute_lookup"}
    if not is_fact_query_early:
        normalized_query, corrected_concept = _normalize_definition_query_before_retrieval(text)
        if normalized_query and normalized_query.strip().lower() != (text or "").strip().lower():
            S.logger.info(
                "WS pre-retrieval normalization applied | original='%s' normalized='%s' concept='%s'",
                (text or "")[:120],
                normalized_query[:120],
                (corrected_concept or "")[:80],
            )
            S.logger.info("[FLOW] query_after = %s", (normalized_query or "")[:400])
            text = normalized_query

    # Update conversation timestamp
    S.conversation_timestamps[connection_id] = time.time()
    if len(S.conversation_history) % 100 == 0:
        S.cleanup_old_conversations()
    
    history = S.conversation_history[connection_id]
    doc_dicts: List[Dict[str, Any]] = []

    def _ws_counted_list_context_rescue(current_docs: Optional[List[Dict[str, Any]]] = None) -> Optional[str]:
        return None

    # ===== ARABIC LANGUAGE HANDLING =====
    # Source-of-truth for answer/TTS language is the script of the actual user
    # query. UI language is only a hint — it must never force an Arabic answer
    # for an English question or vice versa. (Phase 7C — TASK 1)
    _ui_language_in = language
    language = _resolve_user_language(text, language)
    if _forced_final_language in {"ar", "en"}:
        S.logger.info(
            "[LANG ROUTE] forced_final_language=%s original_resolved=%s branch=ws_rewrite",
            _forced_final_language,
            language,
        )
        language = _forced_final_language
    arabic_mode = (language == "ar")
    xtts_lang = "ar" if arabic_mode else XTTS_LANGUAGE
    original_arabic_text = text  # preserve for later use
    ar_query_type = ""
    if arabic_mode:
        ar_classify_t0 = time.perf_counter()
        ar_query_type = S._classify_arabic_query_type(original_arabic_text)
        t_meta["ar_query_type"] = ar_query_type
        t_meta["ar_query_classification_ms"] = int(round((time.perf_counter() - ar_classify_t0) * 1000))
        S.logger.info("[AR QUERY TYPE] type=%s", ar_query_type)
    S.logger.info(
        "[LANG ROUTE] original_language=%s ui_language=%s retrieval_query_language=%s final_language=%s",
        language, _ui_language_in, ("en_fast_hybrid" if ar_query_type == "explanation" else ("ar_native_first" if arabic_mode else language)), language,
    )
    _prefetched_rag_docs = None  # cached from Arabic guard check to avoid double RAG search

    # Track translation time separately so it does not inflate LLM latency
    t_translate_done: float | None = None
    _translate_was_cached: bool = False
    _request_ar_query_cache: Dict[str, str] = {}

    if arabic_mode:
        # Register the per-connection ws-write lock early (before any concurrent
        # task can race on the socket).
        if connection_id not in voice_state.ws_write_locks:
            voice_state.ws_write_locks[connection_id] = asyncio.Lock()
        _ack_lock = voice_state.ws_write_locks[connection_id]

        # 1. Allow small talk in Arabic (greetings, thanks, etc.)
        if S._is_arabic_small_talk(text):
            S.logger.info(f"{connection_id} Arabic small-talk detected — routing through normally")
            text_for_rag = text  # will be handled as greeting below
            arabic_small_talk = True

            # For small-talk just fire the ack and continue (no translation needed)
            if S._arabic_ack_pcm:
                try:
                    async with _ack_lock:
                        await websocket.send_json({"type": "ttsAudioStart", "sampleRate": 24000})
                        await websocket.send_bytes(S._arabic_ack_pcm)
                        await websocket.send_json({"type": "ttsAudioEnd"})
                    t_meta["first_ack_sent"] = time.perf_counter()
                except Exception:
                    pass
        else:
            arabic_small_talk = False

            async def _send_ack_coro():
                if S._arabic_ack_pcm:
                    try:
                        async with _ack_lock:
                            await websocket.send_json({"type": "ttsAudioStart", "sampleRate": 24000})
                            await websocket.send_bytes(S._arabic_ack_pcm)
                            await websocket.send_json({"type": "ttsAudioEnd"})
                        t_meta["first_ack_sent"] = time.perf_counter()
                    except Exception:
                        pass

            async def _native_retrieval_coro():
                if ar_query_type == "explanation":
                    S.logger.info("[AR NATIVE RETRIEVAL] skipped=True reason=explanation_fast_hybrid")
                    t_native_skip = time.perf_counter()
                    t_meta["ar_native_retrieval_start"] = t_native_skip
                    t_meta["ar_native_retrieval_end"] = t_native_skip
                    t_meta["ar_native_retrieval_ms"] = 0
                    return False, "explanation_fast_hybrid", [], {}
                S.logger.info("[AR NATIVE RETRIEVAL] start original_query=%s", str(original_arabic_text or text)[:240])
                t_native_start = time.perf_counter()
                t_meta["ar_native_retrieval_start"] = t_native_start
                native_docs: list[dict] = []
                try:
                    merged_docs: list[dict] = []
                    seen_docs: set[tuple[str, str, str]] = set()
                    native_queries = S._native_arabic_retrieval_queries(original_arabic_text)
                    for idx, native_query in enumerate(native_queries):
                        found_docs = await _active_rag_search_async(
                            native_query,
                            top_k=10 if idx == 0 else 6,
                            distance_threshold=_distance_threshold_for_query(native_query),
                            return_dicts=True,
                            enable_rerank=True,
                        ) or []
                        S.logger.info(
                            "[AR NATIVE RETRIEVAL] probe=%s docs=%s query=%s",
                            idx + 1,
                            len(found_docs or []),
                            str(native_query or "")[:160],
                        )
                        for doc in S._filter_results_to_active_sources(found_docs):
                            metadata = (doc or {}).get("metadata") or {}
                            key = (
                                str((doc or {}).get("source") or metadata.get("source") or metadata.get("file") or ""),
                                str((doc or {}).get("page") or metadata.get("page") or ""),
                                str((doc or {}).get("text") or (doc or {}).get("page_content") or (doc or {}).get("content") or "")[:220],
                            )
                            if key in seen_docs:
                                continue
                            seen_docs.add(key)
                            merged_docs.append(doc)
                    native_docs = merged_docs[:12]
                    S.logger.info("[RERANK ACTIVE]")
                except Exception:
                    S.logger.exception("[AR NATIVE RETRIEVAL] search_failed=True")
                    native_docs = []
                native_docs = S._filter_results_to_active_sources(native_docs)
                accepted, reason, native_metrics = S._assess_native_arabic_retrieval(original_arabic_text, native_docs)
                t_native_end = time.perf_counter()
                t_meta["ar_native_retrieval_end"] = t_native_end
                t_meta["ar_native_retrieval_ms"] = int(round((t_native_end - t_native_start) * 1000))
                best_score = float(native_metrics.get("best_score", 0.0) or 0.0)
                S.logger.info(
                    "[AR NATIVE RETRIEVAL] docs=%s best_score=%.4f best_rank_score=%.4f coverage=%.3f focus=%.3f semantic_density=%.3f",
                    len(native_docs or []),
                    best_score,
                    float(native_metrics.get("best_rank_score", 0.0) or 0.0),
                    float(native_metrics.get("coverage", 0.0) or 0.0),
                    float(native_metrics.get("focus_ratio", 0.0) or 0.0),
                    float(native_metrics.get("semantic_density", 0.0) or 0.0),
                )
                S.logger.info("[AR NATIVE RETRIEVAL] accepted=%s reason=%s", bool(accepted), reason)
                return accepted, reason, native_docs, native_metrics

            _, native_result = await asyncio.gather(_send_ack_coro(), _native_retrieval_coro())
            native_accepted, native_reason, native_docs, native_metrics = native_result
            protected_terms = S._extract_protected_exact_query_terms(original_arabic_text)
            if ar_query_type == "explanation":
                t_fast_query_start = time.perf_counter()
                t_meta["query_translation_start"] = t_fast_query_start
                text_for_rag, fast_query_provider = await _build_fast_arabic_explanation_query(original_arabic_text, t_meta)
                t_translate_done = time.perf_counter()
                t_meta["translate_done"] = t_translate_done
                t_meta["query_translation_end"] = t_translate_done
                if not text_for_rag:
                    fallback_text = RAG_NO_MATCH_RESPONSE
                    S.logger.info("[AR FAST RETRIEVAL] skipped=True reason=empty_fast_query returning_not_found=True")
                    t_meta.setdefault("routing_end", time.perf_counter())
                    try:
                        _save_last_answer_state(connection_id, original_arabic_text, fallback_text, [])
                        _append_conversation_turn(connection_id, original_arabic_text, fallback_text)
                    except Exception:
                        S.logger.exception("[FOLLOWUP] save state failed (AR fast query empty)")
                    try:
                        await send_final_response(
                            connection_id,
                            fallback_text,
                            XTTS_LANGUAGE,
                            effective_query_tts,
                            websocket=websocket,
                            sources=0,
                            arabic_mode=False,
                            t_meta=t_meta,
                            branch="arabic_fast_explanation_empty_query",
                        )
                    except Exception:
                        pass
                    _emit_perf_report(t_meta, perf_start, original_arabic_text, fallback_text, connection_id)
                    return

                t_ar_retrieval_start = time.perf_counter()
                t_meta["retrieval_after_translation_start"] = t_ar_retrieval_start
                rag_docs_check = await _search_fast_minimal_async(text_for_rag, top_k=10) or []
                if protected_terms:
                    rag_docs_check = S._filter_docs_by_protected_terms(rag_docs_check or [], protected_terms)
                t_ar_retrieval_end = time.perf_counter()
                t_meta["retrieval_after_translation_end"] = t_ar_retrieval_end
                retrieval_after_translation_ms = int(round((t_ar_retrieval_end - t_ar_retrieval_start) * 1000))
                t_meta["retrieval_after_translation_ms"] = retrieval_after_translation_ms
                t_meta["ar_fast_retrieval_ms"] = retrieval_after_translation_ms
                t_meta["ar_fast_explanation_single_retrieval"] = True
                non_llm_accepted, non_llm_reason, non_llm_metrics = S._assess_native_arabic_retrieval(text_for_rag, rag_docs_check)
                fast_retrieval_weak = not non_llm_accepted
                S._ar_non_llm_query_cache_update_strength(
                    original_arabic_text,
                    text_for_rag,
                    non_llm_accepted,
                    non_llm_reason,
                    non_llm_metrics,
                )
                S.logger.info(
                    "[AR FAST RETRIEVAL] query=%s provider=%s docs=%s weak=%s time_ms=%s",
                    text_for_rag[:180],
                    fast_query_provider,
                    len(rag_docs_check or []),
                    bool(fast_retrieval_weak),
                    retrieval_after_translation_ms,
                )
                if fast_retrieval_weak:
                    S.logger.info("[AR FAST RETRIEVAL] accepted=False reason=weak_non_llm_evidence")
                    t_meta["ar_fast_explanation_single_retrieval"] = False
                    external_text_for_rag, external_query_provider = await _build_external_arabic_explanation_query(original_arabic_text, t_meta)
                    external_rag_docs_check: list[dict] = []
                    external_retrieval_weak = True
                    if external_text_for_rag:
                        t_external_retrieval_start = time.perf_counter()
                        external_rag_docs_check = await _search_fast_minimal_async(external_text_for_rag, top_k=10) or []
                        if protected_terms:
                            external_rag_docs_check = S._filter_docs_by_protected_terms(external_rag_docs_check or [], protected_terms)
                        t_external_retrieval_end = time.perf_counter()
                        external_retrieval_ms = int(round((t_external_retrieval_end - t_external_retrieval_start) * 1000))
                        t_meta["ar_external_fallback_retrieval_ms"] = external_retrieval_ms
                        external_retrieval_weak = _translation_retrieval_is_weak(external_text_for_rag, external_rag_docs_check)
                        S.logger.info(
                            "[AR FAST RETRIEVAL] query=%s provider=%s docs=%s weak=%s time_ms=%s",
                            external_text_for_rag[:180],
                            external_query_provider,
                            len(external_rag_docs_check or []),
                            bool(external_retrieval_weak),
                            external_retrieval_ms,
                        )
                    else:
                        S.logger.info("[AR NON-LLM QUERY FALLBACK] skipped=True reason=empty_external_query")

                    if external_text_for_rag and not external_retrieval_weak:
                        S.logger.info("[AR LLM QUERY FALLBACK] used=False reason=external_non_llm_evidence_strong")
                        t_meta["ar_llm_query_fallback_used"] = False
                        t_meta["ar_llm_query_fallback_logged"] = True
                        text_for_rag = external_text_for_rag
                        fast_query_provider = external_query_provider
                        rag_docs_check = external_rag_docs_check
                    else:
                        if external_text_for_rag:
                            S.logger.info("[AR FAST RETRIEVAL] accepted=False reason=weak_external_non_llm_evidence")
                        S.logger.info("[AR LLM QUERY FALLBACK] used=True reason=weak_non_llm_evidence")
                        t_meta["ar_llm_query_fallback_used"] = True
                        t_meta["ar_llm_query_fallback_logged"] = True
                        llm_text_for_rag, llm_query_provider = await _build_llm_arabic_explanation_query(original_arabic_text, t_meta)
                        t_translate_done = time.perf_counter()
                        t_meta["translate_done"] = t_translate_done
                        t_meta["query_translation_end"] = t_translate_done
                        if not llm_text_for_rag:
                            fallback_text = RAG_NO_MATCH_RESPONSE
                            S.logger.info("[AR FAST RETRIEVAL] skipped=True reason=empty_llm_fallback_query returning_not_found=True")
                            t_meta.setdefault("routing_end", time.perf_counter())
                            try:
                                _save_last_answer_state(connection_id, original_arabic_text, fallback_text, [])
                                _append_conversation_turn(connection_id, original_arabic_text, fallback_text)
                            except Exception:
                                S.logger.exception("[FOLLOWUP] save state failed (AR llm fallback query empty)")
                            try:
                                await send_final_response(
                                    connection_id,
                                    fallback_text,
                                    XTTS_LANGUAGE,
                                    effective_query_tts,
                                    websocket=websocket,
                                    sources=0,
                                    arabic_mode=False,
                                    t_meta=t_meta,
                                    branch="arabic_fast_explanation_empty_llm_fallback_query",
                                )
                            except Exception:
                                pass
                            _emit_perf_report(t_meta, perf_start, original_arabic_text, fallback_text, connection_id)
                            return

                        t_llm_retrieval_start = time.perf_counter()
                        t_meta["retrieval_after_translation_start"] = t_llm_retrieval_start
                        llm_rag_docs_check = await _search_fast_minimal_async(llm_text_for_rag, top_k=10) or []
                        if protected_terms:
                            llm_rag_docs_check = S._filter_docs_by_protected_terms(llm_rag_docs_check or [], protected_terms)
                        t_llm_retrieval_end = time.perf_counter()
                        t_meta["retrieval_after_translation_end"] = t_llm_retrieval_end
                        llm_retrieval_ms = int(round((t_llm_retrieval_end - t_llm_retrieval_start) * 1000))
                        t_meta["retrieval_after_translation_ms"] = llm_retrieval_ms
                        t_meta["ar_llm_fallback_retrieval_ms"] = llm_retrieval_ms
                        fallback_retrieval_weak = _translation_retrieval_is_weak(llm_text_for_rag, llm_rag_docs_check)
                        S.logger.info(
                            "[AR FAST RETRIEVAL] query=%s provider=%s docs=%s weak=%s time_ms=%s",
                            llm_text_for_rag[:180],
                            llm_query_provider,
                            len(llm_rag_docs_check or []),
                            bool(fallback_retrieval_weak),
                            llm_retrieval_ms,
                        )
                        if fallback_retrieval_weak:
                            fallback_text = RAG_NO_MATCH_RESPONSE
                            S.logger.info("[AR FAST RETRIEVAL] accepted=False reason=weak_llm_fallback_evidence returning_not_found=True")
                            t_meta.setdefault("routing_end", time.perf_counter())
                            try:
                                _save_last_answer_state(connection_id, original_arabic_text, fallback_text, [])
                                _append_conversation_turn(connection_id, original_arabic_text, fallback_text)
                            except Exception:
                                S.logger.exception("[FOLLOWUP] save state failed (AR fast explanation weak)")
                            try:
                                await send_final_response(
                                    connection_id,
                                    fallback_text,
                                    XTTS_LANGUAGE,
                                    effective_query_tts,
                                    websocket=websocket,
                                    sources=0,
                                    arabic_mode=False,
                                    t_meta=t_meta,
                                    branch="arabic_fast_explanation_not_found",
                                )
                            except Exception:
                                pass
                            _emit_perf_report(t_meta, perf_start, original_arabic_text, fallback_text, connection_id)
                            return
                        text_for_rag = llm_text_for_rag
                        fast_query_provider = llm_query_provider
                        rag_docs_check = llm_rag_docs_check
                else:
                    S.logger.info("[AR LLM QUERY FALLBACK] used=False")
                    t_meta["ar_llm_query_fallback_used"] = False
                    t_meta["ar_llm_query_fallback_logged"] = True
                native_docs = rag_docs_check
                native_accepted = True
                native_reason = "explanation_fast_hybrid"
                native_metrics = {}
                protected_terms = []
                text = text_for_rag
            if protected_terms and not S._docs_contain_all_protected_terms(native_docs, protected_terms):
                exact_query = " ".join(protected_terms)
                exact_docs: list[dict] = []
                try:
                    exact_docs = await _active_rag_search_async(
                        exact_query,
                        top_k=5,
                        distance_threshold=max(_distance_threshold_for_query(exact_query), 1.10),
                        return_dicts=True,
                        enable_rerank=True,
                    ) or []
                    S.logger.info("[RERANK ACTIVE]")
                except Exception:
                    S.logger.exception("[AR EXACT ENTITY GUARD] exact_retrieval_failed=True terms=%s", protected_terms)
                    exact_docs = []
                exact_docs = S._filter_docs_by_protected_terms(S._filter_results_to_active_sources(exact_docs), protected_terms)
                S.logger.info(
                    "[AR EXACT ENTITY GUARD] protected_terms=%s exact_docs=%s",
                    protected_terms,
                    len(exact_docs or []),
                )
                if exact_docs:
                    native_docs = exact_docs
                    native_accepted = True
                    native_reason = "strong_evidence"
                    native_metrics = dict(native_metrics or {})
                    native_metrics["protected_exact_hit"] = 1.0
                    S.logger.info("[AR NATIVE RETRIEVAL] accepted=True reason=strong_evidence")
                else:
                    fallback_text = RAG_NO_MATCH_RESPONSE
                    S.logger.info("[AR EXACT ENTITY GUARD] exact_evidence_found=False returning_not_found=True")
                    try:
                        _save_last_answer_state(connection_id, original_arabic_text, fallback_text, [])
                        _append_conversation_turn(connection_id, original_arabic_text, fallback_text)
                    except Exception:
                        S.logger.exception("[FOLLOWUP] save state failed (AR exact entity not-found)")
                    try:
                        await send_final_response(
                            connection_id,
                            fallback_text,
                            XTTS_LANGUAGE,
                            effective_query_tts,
                            websocket=websocket,
                            sources=0,
                            arabic_mode=False,
                            t_meta=t_meta,
                            branch="arabic_exact_entity_not_found",
                        )
                    except Exception:
                        pass
                    _emit_perf_report(t_meta, perf_start, original_arabic_text, fallback_text, connection_id)
                    return

            if native_accepted:
                if ar_query_type == "explanation":
                    fallback_used = bool(t_meta.get("ar_llm_query_fallback_used"))
                    t_meta["query_translation_skipped"] = not fallback_used
                    if not t_meta.get("ar_llm_query_fallback_logged"):
                        S.logger.info("[AR LLM QUERY FALLBACK] used=%s", fallback_used)
                else:
                    t_meta["query_translation_ms"] = 0
                    t_meta["query_translation_skipped"] = True
                    t_meta["query_translation_cache_hit"] = False
                    S.logger.info("[AR TRANSLATION FALLBACK] used=False")
                _prefetched_rag_docs = native_docs
            else:
                S.logger.info("[AR TRANSLATION FALLBACK] used=True")
                S.logger.info(f"{connection_id} Arabic mode: native retrieval weak; translating query to English…")

            async def _translate_coro():
                nonlocal _translate_was_cached
                query_cache_key = re.sub(r"\s+", " ", str(text or "")).strip()
                if query_cache_key in _request_ar_query_cache:
                    S.logger.info("[AR QUERY CACHE] reused=True scope=request")
                    _translate_was_cached = True
                    t_meta["query_translation_cache_hit"] = True
                    return _request_ar_query_cache[query_cache_key]
                # --- Cache check: skip Google API for repeated/identical queries ---
                cached = S._translation_cache_get(text)
                if cached:
                    S.logger.info(f"Translation (cache hit): '{text[:60]}' → '{cached[:60]}'")
                    S.logger.info("[AR QUERY CACHE] reused=True scope=global")
                    _translate_was_cached = True
                    t_meta["query_translation_cache_hit"] = True
                    if query_cache_key:
                        _request_ar_query_cache[query_cache_key] = cached
                    return cached
                S.logger.info("[AR QUERY CACHE] reused=False")
                t_meta["query_translation_cache_hit"] = False
                # --- Live translation via deep_translator (Google) ---
                try:
                    result = await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: __import__('deep_translator', fromlist=['GoogleTranslator'])
                                   .GoogleTranslator(source='ar', target='en').translate(text)
                    )
                    translated = result if result else text
                    S._translation_cache_put(text, translated)
                    if query_cache_key:
                        _request_ar_query_cache[query_cache_key] = translated
                    return translated
                except Exception as _te:
                    S.logger.warning(f"deep_translator AR→EN failed ({_te}) — falling back to LLM translation")
                    try:
                        fallback = await asyncio.wait_for(
                            translate_with_llm(text, "ar", "en"), timeout=20.0
                        )
                        S._translation_cache_put(text, fallback)
                        if query_cache_key:
                            _request_ar_query_cache[query_cache_key] = fallback
                        return fallback
                    except Exception:
                        return text

            if not native_accepted:
                t_query_translation_start = time.perf_counter()
                t_meta["query_translation_start"] = t_query_translation_start
                text_for_rag = await _translate_coro()
                t_translate_done = time.perf_counter()
                t_meta["translate_done"] = t_translate_done
                t_meta["query_translation_end"] = t_translate_done
                query_translation_ms = int(round((t_translate_done - t_query_translation_start) * 1000))
                t_meta["query_translation_ms"] = query_translation_ms
                S.logger.info(
                    "[AR PERF] query_translation_ms=%s cache_hit=%s",
                    query_translation_ms,
                    bool(_translate_was_cached),
                )
                S.logger.info(f"Translation (Arabic→English): '{text[:60]}' → '{text_for_rag[:60]}'")

                rag_docs_check = None
                t_ar_retrieval_start = time.perf_counter()
                t_meta["retrieval_after_translation_start"] = t_ar_retrieval_start
                rag_docs_check = _search_with_query_expansion(
                    text_for_rag,
                    top_k=10,
                    distance_threshold=_distance_threshold_for_query(text_for_rag),
                    return_dicts=True,
                )
                if protected_terms:
                    rag_docs_check = S._filter_docs_by_protected_terms(rag_docs_check or [], protected_terms)
                if (not rag_docs_check) and _is_overview_query(text_for_rag):
                    rag_docs_check = await _active_rag_search_async(
                        _overview_seed_query(),
                        top_k=5,
                        distance_threshold=max(_distance_threshold_for_query(text_for_rag), 1.50),
                        return_dicts=True,
                        enable_rerank=True,
                    )
                    S.logger.info("[RERANK ACTIVE]")
                    S.logger.info("%s Arabic overview fallback retrieval used | docs=%s", connection_id, len(rag_docs_check))
                text_for_rag, rag_docs_check = await _maybe_improve_arabic_translation_retrieval(
                    original_arabic_text,
                    text_for_rag,
                    rag_docs_check,
                    protected_terms,
                    t_meta,
                )
                t_ar_retrieval_end = time.perf_counter()
                t_meta["retrieval_after_translation_end"] = t_ar_retrieval_end
                retrieval_after_translation_ms = int(round((t_ar_retrieval_end - t_ar_retrieval_start) * 1000))
                t_meta["retrieval_after_translation_ms"] = retrieval_after_translation_ms
                S.logger.info(
                    "[AR PERF] retrieval_after_translation_ms=%s docs=%s",
                    retrieval_after_translation_ms,
                    len(rag_docs_check or []),
                )
                _prefetched_rag_docs = rag_docs_check
                if not rag_docs_check:
                    S.logger.info(f"{connection_id} Arabic off-topic guard triggered — no RAG docs found for: {text_for_rag[:60]}")
                    try:
                        fallback_text = RAG_NO_MATCH_RESPONSE if protected_terms else ARABIC_OFF_TOPIC_RESPONSE
                        await send_final_response(
                            connection_id,
                            fallback_text,
                            XTTS_LANGUAGE if protected_terms else "ar",
                            effective_query_tts,
                            websocket=websocket,
                            sources=0,
                            arabic_mode=False if protected_terms else True,
                            t_meta=t_meta,
                            branch="arabic_translation_fallback_no_docs",
                        )
                    except Exception:
                        pass
                    return
                text = text_for_rag
    else:
        arabic_small_talk = False

    # RAG search (same as non-streaming)
    # In Arabic small-talk mode, treat as greeting
    is_greeting = arabic_small_talk or _is_pure_smalltalk_query(text)

    is_simple_factual_query = _is_simple_factual_text_query(text)
    t_meta["routing_end"] = time.perf_counter()  # routing decision complete
    if is_greeting:
        relevant_docs = []
    elif _prefetched_rag_docs is not None:
        # Arabic path: reuse result from guard check — avoids a second identical RAG search
        relevant_docs = _prefetched_rag_docs
        if t_meta.get("ar_fast_explanation_single_retrieval"):
            t_meta["retrieval_start"] = t_meta.get("retrieval_after_translation_start") or t_meta.get("routing_end")
            t_meta["retrieval_end"] = t_meta.get("retrieval_after_translation_end") or t_meta.get("routing_end")
        else:
            t_meta["retrieval_start"] = (
                t_meta.get("ar_native_retrieval_start")
                or t_meta.get("retrieval_after_translation_start")
                or t_meta.get("routing_end")
            )
            t_meta["retrieval_end"] = (
                t_meta.get("ar_native_retrieval_end")
                or t_meta.get("retrieval_after_translation_end")
                or t_meta.get("routing_end")
            )
    else:
        retrieval_start = time.perf_counter()
        t_meta["retrieval_start"] = retrieval_start
        text_l = (text or "").strip().lower()
        family = _classify_query_family(text)
        family_v2 = _classify_query_family_v2(text)
        if _phase14_trace_enabled(t_meta):
            t_meta["phase14_query_family"] = family
            t_meta["phase14_query_family_v2"] = family_v2
            t_meta["query_family_v2"] = family_v2
        if family_v2 in {"fact_entity", "attribute_lookup"}:
            top_k_req = FACT_MAX_TOP_K
        elif _is_controlled_definition_entity_query(text) or family_v2 == "definition_comparison":
            top_k_req = 12
        elif is_generation_query_requested:
            top_k_req = 12
        elif family_v2 == "list_entity" or family == "list_structure":
            top_k_req = 10
        elif family_v2 in {"explanatory_compare"} or family == "overview_chapter_compare":
            top_k_req = 10
        else:
            top_k_req = 6
        retrieval_query = _retrieval_query_for_family(text, family_v2)
        if _phase14_trace_enabled(t_meta):
            t_meta["phase14_retrieval_query"] = retrieval_query
        if family_v2 not in {"fact_entity", "attribute_lookup"} and _is_safe_definition_fast_path_query(text):
            relevant_docs = await _search_fast_definition_minimal_async(text)
        else:
            relevant_docs = await _search_fast_minimal_async(retrieval_query, top_k=top_k_req)
        if (not relevant_docs) and _is_overview_query(text):
            relevant_docs = await _active_rag_search_async(
                _overview_seed_query(),
                top_k=5,
                distance_threshold=max(_distance_threshold_for_query(text), 1.50),
                return_dicts=True,
                enable_rerank=True,
            )
            S.logger.info("[RERANK ACTIVE]")
            S.logger.info("%s overview fallback retrieval used | docs=%s query='%s'", connection_id, len(relevant_docs), text[:80])
        if family_v2 == "document_summary":
            relevant_docs = _rerank_document_summary_for_coverage(relevant_docs or [])
        # Reranker is active in retrieval path
        retrieval_ms = (time.perf_counter() - retrieval_start) * 1000
        t_meta["retrieval_end"] = time.perf_counter()
        if _phase14_trace_enabled(t_meta):
            t_meta["phase14_retrieved_chunks"] = _phase14_doc_trace_rows(relevant_docs, limit=10)
            t_meta["phase14_retrieved_count"] = len(relevant_docs or [])
        S.logger.info(
            "%s retrieval_done | fast_path=%s top_k=%s docs=%s retrieval_ms=%.0f",
            connection_id,
            is_simple_factual_query,
            top_k_req,
            len(relevant_docs),
            retrieval_ms,
        )

    if _should_apply_query_intent_rerank(_classify_query_family_v2(text)):
        t_meta["rerank_start"] = time.perf_counter()
        relevant_docs = _rerank_docs_for_query_intent(text, relevant_docs)
        relevant_docs = _retrieve_with_section_bias(text, relevant_docs, top_k=top_k_req if 'top_k_req' in locals() else 10)
        t_meta["rerank_end"] = time.perf_counter()
        if _phase14_trace_enabled(t_meta):
            t_meta["phase14_reranked_chunks"] = _phase14_doc_trace_rows(relevant_docs, limit=10)
            t_meta["phase14_reranked_count"] = len(relevant_docs or [])

    if (not is_greeting) and (_classify_query_family_v2(text) == "fact_entity") and relevant_docs:
        try:
            fact_rescue_queries = _build_fact_rescue_queries(text, history)
            rescue_collected: list[dict] = []
            for retry_count, rq in enumerate((fact_rescue_queries or [])[:MAX_FACT_RETRIES], start=1):
                S.logger.info("[FACT RETRY] count=%s", retry_count)
                S.logger.info("[FACT RESCUE QUERY] %s", rq)
                rescue_collected.extend(await _search_fast_minimal_async(rq, top_k=8) or [])
            if len(fact_rescue_queries or []) >= MAX_FACT_RETRIES:
                S.logger.info("[FACT RETRY] max_reached=True")
            if rescue_collected:
                base_doc_dicts = _prepare_rag_doc_dicts_shared(relevant_docs or [], text)
                merged_fact_docs = _merge_rescue_docs_and_rerank(
                    text,
                    base_doc_dicts,
                    rescue_collected,
                    top_k=min(FACT_MAX_TOP_K, max(8, (top_k_req if 'top_k_req' in locals() else 5) + 4)),
                )
                if merged_fact_docs:
                    relevant_docs = merged_fact_docs
                    S.logger.info("[DOC COUNT TRACE] stage=call_llm_streaming.fact_rescue_merged count=%s", len(relevant_docs or []))
        except Exception:
            S.logger.exception("FACT rescue retrieval skipped due to internal error (ws)")

    if (not is_greeting) and relevant_docs and (not arabic_mode) and _is_simple_factual_text_query(text):
        if not _passes_hybrid_relevance_gate(text, relevant_docs):
            max_sim = _max_doc_similarity(relevant_docs)
            S.logger.info(
                "%s hybrid_gate_reject | sim=%.4f lexical_ok=%s query='%s'",
                connection_id,
                max_sim,
                _has_english_keyword_overlap(text, relevant_docs),
                text[:80],
            )
            # Relaxed: Do not clear relevant_docs to allow LLM to judge fuzzy matches
            pass
            # relevant_docs = []

    if (not is_greeting) and relevant_docs and (not arabic_mode) and not _retrieval_context_is_reliable(text, relevant_docs):
        ql = text.lower()
        keep_for_structure = _query_requires_structure(text)
        family_v2_guard = _classify_query_family_v2(text)
        if family_v2_guard in {"definition_entity", "definition_comparison", "list_entity", "toc_structure"}:
            keep_for_structure = True
        if keep_for_structure:
            S.logger.info("%s context_reliability_bypass | query='%s'", connection_id, text[:80])
        else:
            # Check for name/entity signals — these deserve a chance even if reliability markers are low
            has_names = any(w[0].isupper() and w[0].isalpha() for w in text.split()[1:]) if len(text.split()) > 1 else False
            if has_names:
                S.logger.info("%s context_reliability_softened | query='%s'", connection_id, text[:80])
            else:
                S.logger.info("%s context_reliability_reject | query='%s'", connection_id, text[:80])
                relevant_docs = []

        # (Factual shortcut removed to favor pure RAG pipeline)

    if (not is_greeting) and (not relevant_docs):
        rescue_family = _classify_query_family_v2(text)
        if rescue_family in {"definition_entity", "definition_comparison"}:
            relevant_docs = await _search_fast_definition_minimal_async(text) or []

    if (not is_greeting) and (not relevant_docs) and not S._skip_deterministic_rag_shortcuts(text):
        S.logger.info(
            f"{connection_id} RAG strict guard: no sufficiently relevant docs for query='{text[:80]}' "
            f"(threshold={RAG_STRICT_DISTANCE_THRESHOLD:.2f})"
        )
        fallback_text = ARABIC_OFF_TOPIC_RESPONSE if arabic_mode else _apply_not_found_ux(text, RAG_NO_MATCH_RESPONSE, [])
        try:
            _save_last_answer_state(connection_id, text, fallback_text, [])
            _append_conversation_turn(connection_id, text, fallback_text)
        except Exception:
            S.logger.exception("[FOLLOWUP] save state failed (WS no docs)")
        try:
            await send_final_response(
                connection_id,
                fallback_text,
                "ar" if arabic_mode else xtts_lang,
                effective_query_tts,
                websocket=websocket,
                sources=0,
                arabic_mode=arabic_mode,
                t_meta=t_meta,
                branch="not_found_no_docs",
            )
        except Exception:
            pass

        response_time = int((time.time() - start_time) * 1000)
        log_usage(
            username=user.get("username", "unknown"),
            user_role=user.get("role", "unknown"),
            query_text=text,
            response_status="success",
            error_message=None,
            response_time_ms=response_time,
            rag_docs_found=0,
            query_length=len(text.strip()),
            response_length=len(fallback_text),
        )
        _emit_perf_report(t_meta, perf_start, text, fallback_text, connection_id)
        return
    
    context_block = ""
    if relevant_docs:
        q_early = (text or "").strip().lower()
        early_identity = None
        if (
            q_early.startswith("who is")
            or q_early.startswith("who was")
            or q_early.startswith("who introduced")
            or bool(re.match(r"^who\s+is\s+considered\s+the\s+father\s+of\b", q_early))
        ):
            early_identity = _extract_strict_same_line_person_identity_from_retrieved_docs(text, relevant_docs)
        if early_identity and re.search(r"\bscholar\s+known\s+for\b", early_identity, flags=re.IGNORECASE):
            early_identity = None
        if early_identity:
            try:
                _save_last_answer_state(connection_id, text, early_identity, relevant_docs)
                _append_conversation_turn(connection_id, text, early_identity)
            except Exception:
                S.logger.exception("[FOLLOWUP] save state failed (WS early_identity)")
            try:
                await send_final_response(
                    connection_id,
                    early_identity,
                    "ar" if arabic_mode else xtts_lang,
                    effective_query_tts,
                    websocket=websocket,
                    sources=len(relevant_docs),
                    arabic_mode=arabic_mode,
                    t_meta=t_meta,
                    branch="early_identity",
                )
            except Exception:
                pass
            response_time = int((time.time() - start_time) * 1000)
            log_usage(
                user.get("username", "unknown"),
                user.get("role", "unknown"),
                text,
                "success",
                None,
                response_time,
                len(relevant_docs),
                len((text or "").strip()),
                len(early_identity),
            )
            _emit_perf_report(t_meta, perf_start, text, early_identity, connection_id)
            return

        try:
            for i, d in enumerate((relevant_docs or [])[:5]):
                score = None
                for k in ("final_score", "score", "similarity"):
                    if k in (d or {}):
                        try:
                            score = float((d or {}).get(k) or 0.0)
                        except Exception:
                            score = 0.0
                        break
                preview = str((d or {}).get("text") or (d or {}).get("page_content") or (d or {}).get("content") or "")[:160]
                S.logger.info("[RAG PRE-CONTEXT] top5 idx=%s score=%s preview=%s", i, score, preview)
        except Exception:
            S.logger.exception("RAG PRE-CONTEXT logging failed (ws)")

        # Anti-leak source filter: discard any retrieved chunks that do not
        # belong to the currently active document before building doc_dicts.
        # This prevents old-PDF content from surfacing after a hot-swap.
        if _phase14_trace_enabled(t_meta):
            t_meta["phase14_active_filter_input_count"] = len(relevant_docs or [])
        relevant_docs = S._filter_results_to_active_sources(relevant_docs)
        if _phase14_trace_enabled(t_meta):
            t_meta["phase14_active_filter_output_count"] = len(relevant_docs or [])
            t_meta["phase14_active_sources"] = sorted(S._get_active_sources())[:20]
            t_meta["phase14_active_filtered_chunks"] = _phase14_doc_trace_rows(relevant_docs, limit=10)
        S.logger.info(
            "[KB ANTI-LEAK] post-filter | active_sources=%s remaining_docs=%s",
            sorted(S._get_active_sources()),
            len(relevant_docs),
        )

        # Keep UI path doc preparation consistent with direct HTTP/helper path.
        doc_dicts = _prepare_rag_doc_dicts_shared(relevant_docs, text)
        explanation_candidate_doc_dicts = list(doc_dicts or [])

        def is_definition_like(text: str) -> bool:
            t = (text or "").lower()
            return any(x in t for x in [
                " is ",
                " refers to ",
                " defined as ",
                " means ",
                " can be defined as "
            ])

        query_l = (text or "").lower()
        family_v2_current = _classify_query_family_v2(text)
        is_compare_query = (family_v2_current != "definition_comparison") and (_is_compare_query(text) or bool(all(_compare_terms_from_query(text))))
        is_definition_query = (
            (family_v2_current == "definition_comparison" or _is_definition_style_query(text))
            and (not is_compare_query)
            and (family_v2_current != "document_summary")
            and (family_v2_current != "fact_entity")
        )
        if family_v2_current != "document_summary":
            _has_entity, _query_entity = _extract_entity_from_definition_query(text)
        else:
            _has_entity, _query_entity = (False, "")
        if is_compare_query:
            _has_entity, _query_entity = (False, "")
        query_entity = (_query_entity or "").strip().lower() if _has_entity else ""

        entity_definition_docs = []
        definition_docs = []
        if is_definition_query:
            original_definition_docs = list(doc_dicts or [])
            total_docs = len(doc_dicts or [])
            def _collect_definition_candidates(current_docs):
                concept_docs = _apply_concept_filter_to_docs(list(current_docs or []), query_entity)
                local_filtered_ranked_docs = []
                local_entity_definition_docs = []
                local_definition_docs = []
                local_explanation_docs = []
                local_indirect_evidence_pool: list[dict] = []
                for doc_rank, d in enumerate(concept_docs or []):
                    chunk_text = str(d.get("page_content") or d.get("text") or d.get("content") or "")

                    if _is_wrong_concept_definition_chunk(chunk_text, query_entity):
                        S.logger.info(
                            "[ENTITY DEF REJECT] reason=wrong_concept chunk_preview=%s",
                            chunk_text[:220].replace("\n", " "),
                        )
                        continue

                    local_filtered_ranked_docs.append(d)

                    if is_entity_definition_like(chunk_text, query_entity):
                        local_entity_definition_docs.append(d)
                    elif is_definition_like(chunk_text):
                        local_definition_docs.append(d)
                    elif _doc_has_explanation_for_entity(chunk_text, query_entity):
                        local_explanation_docs.append(d)

                    chunk_score = float(d.get("score", 0.0) or 0.0)
                    evidence_scored = collect_indirect_entity_evidence(chunk_text, query_entity, return_scored=True)
                    for idx_ev, scored_item in enumerate(evidence_scored):
                        try:
                            sentence_quality, is_table_like, sent = scored_item
                        except Exception:
                            sentence_quality, is_table_like, sent = (0.0, _is_table_or_classification_sentence(str(scored_item)), str(scored_item))
                        S.logger.info("[INDIRECT DEF EVIDENCE] sentence=%s", sent[:180])
                        prose_bonus = 0.35 if not is_table_like else 0.0
                        table_penalty = 0.35 if is_table_like else 0.0
                        rank_decay = float(doc_rank) * 0.03
                        sentence_score_boost = max(0.0, float(sentence_quality)) * 0.55
                        score = chunk_score + sentence_score_boost + prose_bonus - table_penalty - rank_decay - (idx_ev * 0.01)
                        md = dict((d or {}).get("metadata") or {})
                        local_indirect_evidence_pool.append({
                            "score": score,
                            "is_table": bool(is_table_like),
                            "sentence": sent,
                            "chunk_id": str(md.get("chunk_id") or md.get("id") or md.get("chunk_index") or ""),
                            "chunk_index": md.get("chunk_index"),
                            "section": str(md.get("section") or md.get("chapter") or "").strip().lower(),
                        })
                return (
                    local_filtered_ranked_docs,
                    local_entity_definition_docs,
                    local_definition_docs,
                    local_explanation_docs,
                    local_indirect_evidence_pool,
                )

            filtered_ranked_docs, entity_definition_docs, definition_docs, explanation_docs, indirect_evidence_pool = _collect_definition_candidates(doc_dicts)

            need_rescue = (
                (not entity_definition_docs)
                and (not definition_docs)
                and _indirect_evidence_pool_is_weak(indirect_evidence_pool)
            )
            if query_entity and (not entity_definition_docs) and len(filtered_ranked_docs) <= 1:
                need_rescue = True
            if need_rescue and query_entity:
                S.logger.info("[RETRIEVAL RESCUE] activated entity=%s", query_entity)
                rescue_queries = _build_definition_entity_rescue_queries(text, query_entity)
                rescue_collected: list[dict] = []
                for rq in rescue_queries:
                    S.logger.info("[RETRIEVAL RESCUE QUERY] %s", rq)
                    rescue_collected.extend(await _search_fast_minimal_async(rq, top_k=8) or [])
                if rescue_collected:
                    doc_dicts = _merge_rescue_docs_and_rerank(text, doc_dicts, rescue_collected, top_k=max(12, total_docs + 8))
                    S.logger.info("[RETRIEVAL RESCUE MERGED] count=%d", len(doc_dicts or []))
                    filtered_ranked_docs, entity_definition_docs, definition_docs, explanation_docs, indirect_evidence_pool = _collect_definition_candidates(doc_dicts)

            if not filtered_ranked_docs:
                doc_dicts = []
                S.logger.info("[DEF REJECT WEAK] entity=%s reason=no_strong_definition_chunk", query_entity)
                S.logger.info(
                    "[DEF FILTER EMPTY] entity=%s total_before=%d after_entity_filter=%d",
                    query_entity,
                    total_docs,
                    len(filtered_ranked_docs),
                )
            else:
                blended_pool = []
                blended_pool.extend(entity_definition_docs)
                blended_pool.extend(definition_docs)
                blended_pool.extend(explanation_docs)
                if blended_pool:
                    doc_dicts = blended_pool
                else:
                    doc_dicts = filtered_ranked_docs
                    S.logger.info("[STRICT DEF PREF MISS] entity=%s reason=no_strict_definition_using_ranked_pool", query_entity)

            if entity_definition_docs and len(entity_definition_docs) == 1 and len(doc_dicts) > 1:
                S.logger.info("[STRICT DEF PREF MISS] entity=%s reason=single_strict_doc_blended_with_explanations", query_entity)

            # MP-C12 — Indirect-evidence promotion (mirror of upstream branch).
            # See the parallel definition pipeline above for full rationale.
            if (
                query_entity
                and not entity_definition_docs
                and not definition_docs
                and indirect_evidence_pool
                and not _indirect_evidence_pool_is_weak(indirect_evidence_pool)
            ):
                ranked_indirect = sorted(
                    indirect_evidence_pool,
                    key=lambda it: (
                        not bool((it or {}).get("is_table", False)),
                        float((it or {}).get("score", 0.0) or 0.0),
                    ),
                    reverse=True,
                )
                indirect_sentences = [
                    str((it or {}).get("sentence") or "").strip()
                    for it in ranked_indirect
                    if str((it or {}).get("sentence") or "").strip()
                    and not bool((it or {}).get("is_table", False))
                ]
                if indirect_sentences:
                    seed_doc = next(
                        (d for d in (explanation_docs or filtered_ranked_docs or doc_dicts) if d),
                        None,
                    )
                    seed_md = dict((seed_doc or {}).get("metadata") or {}) if seed_doc else {}
                    seed_md["_indirect_definition_mode"] = True
                    seed_md["_indirect_entity"] = query_entity
                    seed_md["_indirect_evidence"] = indirect_sentences[:3]
                    indirect_doc = {
                        "page_content": "\n".join(indirect_sentences[:3]),
                        "text": "\n".join(indirect_sentences[:3]),
                        "metadata": seed_md,
                        "score": float((seed_doc or {}).get("score", 1.0) or 1.0) + 0.5,
                    }
                    doc_dicts = [indirect_doc] + list(doc_dicts or [])
                    S.logger.info(
                        "[INDIRECT PROMOTE] entity=%s sentences=%d top=%s",
                        query_entity,
                        len(indirect_sentences[:3]),
                        indirect_sentences[0][:160],
                    )

            entity_filtered_docs = _dedup_docs_exact_text(filtered_ranked_docs)
            entity_filtered_docs = sorted(
                entity_filtered_docs,
                key=lambda x: float((x or {}).get("score", 0.0) or 0.0),
                reverse=True,
            )
            entity_filtered_keep = min(5, len(entity_filtered_docs))
            entity_filtered_docs = entity_filtered_docs[:entity_filtered_keep]

            doc_dicts = _dedup_docs_exact_text(doc_dicts)
            doc_dicts = sorted(doc_dicts, key=lambda x: float((x or {}).get("score", 0.0) or 0.0), reverse=True)
            if len(doc_dicts) <= 1 and len(entity_filtered_docs) > 1:
                doc_dicts = list(entity_filtered_docs)
            def_pool_keep = min(5, len(doc_dicts))
            doc_dicts = doc_dicts[:def_pool_keep]
            S.logger.info("[DEF POOL SIZE] kept=%d total=%d", len(doc_dicts), total_docs)
            try:
                pool_chunks = [
                    {
                        "idx": i,
                        "score": round(float((d or {}).get("score", 0.0) or 0.0), 4),
                        "chunk": ((d.get("metadata") or {}).get("chunk_index")),
                    }
                    for i, d in enumerate(doc_dicts)
                ]
                S.logger.info("[DEF POOL CHUNKS] %s", pool_chunks)
            except Exception:
                S.logger.exception("DEF POOL CHUNKS logging failed (ws)")

            try:
                entity_pool_chunks = [
                    {
                        "idx": i,
                        "score": round(float((d or {}).get("score", 0.0) or 0.0), 4),
                        "chunk": ((d.get("metadata") or {}).get("chunk_index")),
                    }
                    for i, d in enumerate(entity_filtered_docs)
                ]
                S.logger.info("[ENTITY DEF FILTER CHUNKS] %s", entity_pool_chunks)
            except Exception:
                S.logger.exception("ENTITY DEF FILTER CHUNKS logging failed (ws)")

            S.logger.info(
                "[ENTITY DEF FILTER] entity=%s kept=%d total=%d",
                query_entity,
                len(entity_filtered_docs),
                total_docs,
            )
            doc_dicts = _enforce_definition_doc_contamination_guard(doc_dicts, query_entity)
            if doc_dicts:
                S.logger.info("[FINAL CONCEPT CHECK] entity=%s sentences=%d same_chunk=%s", query_entity, len(doc_dicts), len(doc_dicts) == 1)
                S.logger.info("[ACCEPT FINAL] preview=%s", str((doc_dicts[0] or {}).get("page_content") or "")[:180].replace("\n", " "))
        if is_definition_query:
            S.logger.info(
                "[DEF FILTER] applied=%s kept=%d total=%d",
                True,
                len(doc_dicts or []),
                len(original_definition_docs or []),
            )
        else:
            S.logger.info("[DEF FILTER] applied=%s kept=%d total=%d",
                        bool(definition_docs), len(definition_docs), len(doc_dicts))

        family_legacy_current = _classify_query_family(text)
        needs_early_section_rerank = (
            family_v2_current in {"list_entity", "toc_structure"}
            or family_legacy_current in {"list_structure", "overview_chapter_compare"}
        )
        if needs_early_section_rerank and doc_dicts and not bool(t_meta.get("ar_fast_explanation_single_retrieval")):
            pool_before = len(doc_dicts)
            rerank_top_k = min(max(6, pool_before), 12)
            doc_dicts = _rerank_docs_for_query_intent(text, doc_dicts)
            doc_dicts = _retrieve_with_section_bias(text, doc_dicts, top_k=rerank_top_k)
            S.logger.info(
                "[SECTION RERANK DEBUG][WS] stage=early_pre_shortlist family_v2=%s family=%s before=%d after=%d top_k=%d",
                family_v2_current,
                family_legacy_current,
                pool_before,
                len(doc_dicts or []),
                rerank_top_k,
            )

        doc_dicts = sorted(doc_dicts, key=lambda x: x.get("score", 0), reverse=True)
        S.logger.info("[SORT CHECK] top scores: %s", [round(d.get("score",0),4) for d in doc_dicts[:5]])
        doc_router_decision = S._route_multi_document_evidence(text, doc_dicts)
        doc_router_mode = str(doc_router_decision.get("mode") or "single_source")
        doc_router_reason = str(doc_router_decision.get("reason") or "")
        doc_router_selected_sources = list(doc_router_decision.get("selected_display_sources") or [])
        doc_dicts = list(doc_router_decision.get("docs") or [])
        if doc_router_mode == "clarification":
            clarification_text = "I found relevant evidence in more than one active document. Please clarify which document or source you want me to use."
            if arabic_mode and (_is_compare_query(text) or bool(all(_compare_terms_from_query(text)))):
                t_meta["comparison_synthesis_ms"] = 0
                S.logger.info("[AR PERF] comparison_synthesis_ms=0 reason=clarification")
            try:
                S.last_answer_state.pop(connection_id, None)
            except Exception:
                pass
            try:
                history.append({"role": "user", "content": text.strip()})
                history.append({"role": "assistant", "content": clarification_text})
            except Exception:
                pass
            try:
                await send_final_response(
                    connection_id,
                    clarification_text,
                    "ar" if arabic_mode else xtts_lang,
                    effective_query_tts,
                    websocket=websocket,
                    sources=len(doc_dicts),
                    arabic_mode=arabic_mode,
                    t_meta=t_meta,
                    branch="multi_doc_clarification",
                )
            except Exception:
                pass
            try:
                response_time = int((time.time() - start_time) * 1000)
                log_usage(
                    user.get("username", "unknown"),
                    user.get("role", "unknown"),
                    text,
                    "success",
                    None,
                    response_time,
                    len(doc_dicts),
                    len((text or "").strip()),
                    len(clarification_text),
                )
            except Exception:
                pass
            _emit_perf_report(t_meta, perf_start, text, clarification_text, connection_id)
            return
        is_fact_query = _classify_query_family_v2(text) == "fact_entity"
        keep_n = 5 if (is_definition_query or _is_compare_query(text) or is_fact_query or needs_early_section_rerank) else 3
        if family_v2_current == "document_summary":
            keep_n = max(keep_n, min(8, len(doc_dicts or [])))
        if doc_router_mode == "multi_source_synthesis":
            keep_n = max(keep_n, min(8, len(doc_dicts or [])))
        if family_legacy_current == "list_structure" or family_v2_current == "list_entity":
            S.logger.info("[LIST RECALL DEBUG][WS] stage=pre_shortlist family_v2=%s family=%s pool=%d keep_n=%d", family_v2_current, family_legacy_current, len(doc_dicts or []), keep_n)
        if family_v2_current == "document_summary":
            doc_dicts = _select_document_summary_coverage_docs(doc_dicts, max_docs=keep_n)
        else:
            doc_dicts = doc_dicts[:keep_n]
        if _phase14_trace_enabled(t_meta):
            t_meta["phase14_keep_n"] = keep_n
            t_meta["phase14_selected_context"] = _phase14_doc_trace_rows(doc_dicts, limit=keep_n, preview_chars=500)
            t_meta["phase14_selected_context_chars"] = sum(len(_phase14_doc_text(d)) for d in doc_dicts or [])
        relevant_docs = [
            {
                "page_content": d.get("page_content") or d.get("text") or d.get("content") or "",
                "text": d.get("page_content") or d.get("text") or d.get("content") or "",
                "content": d.get("page_content") or d.get("text") or d.get("content") or "",
                "metadata": dict(d.get("metadata") or {}),
            }
            for d in doc_dicts
        ]
        try:
            for i, d in enumerate(doc_dicts):
                S.logger.info(
                    "[RAG FINAL SELECTED] idx=%s score=%s page=%s chunk_index=%s preview=%s",
                    i,
                    (d.get("metadata") or {}).get("_score"),
                    (d.get("metadata") or {}).get("page"),
                    (d.get("metadata") or {}).get("chunk_index"),
                    str(d.get("page_content") or "")[:160],
                )
        except Exception:
            S.logger.exception("RAG FINAL SELECTED logging failed (ws)")
        _log_selected_doc_markers(doc_dicts)
        
        # Guard against empty/malformed retrieval output in streaming mode.
        docs_valid = bool(
            isinstance(doc_dicts, list)
            and doc_dicts
            and isinstance(doc_dicts[0], dict)
            and str(doc_dicts[0].get("page_content") or "").strip()
        )
        relevant_valid = bool(
            isinstance(relevant_docs, list)
            and relevant_docs
            and isinstance(relevant_docs[0], dict)
        )
        if not docs_valid or not relevant_valid:
            if S._skip_deterministic_rag_shortcuts(text, doc_router_mode if 'doc_router_mode' in locals() else ""):
                S.logger.info("[WS SAFE FALLBACK] skipped reason=bridge_or_format_query")
            else:
                S.logger.warning(
                    "[WS SAFE FALLBACK] relevant_docs/doc_dicts invalid docs_valid=%s relevant_valid=%s",
                    docs_valid,
                    relevant_valid,
                )
                short_answer = _apply_not_found_ux(text, RAG_NO_MATCH_RESPONSE, doc_dicts if isinstance(doc_dicts, list) else [])
                try:
                    # Clears any stale prior state because answer is not-found.
                    _save_last_answer_state(connection_id, text, short_answer, doc_dicts if isinstance(doc_dicts, list) else [])
                    _append_conversation_turn(connection_id, text, short_answer)
                except Exception:
                    S.logger.exception("[FOLLOWUP] save state failed (WS safe fallback)")
                try:
                    await send_final_response(
                        connection_id,
                        short_answer,
                        "ar" if arabic_mode else xtts_lang,
                        effective_query_tts,
                        websocket=websocket,
                        sources=len(doc_dicts) if isinstance(doc_dicts, list) else 0,
                        arabic_mode=arabic_mode,
                        t_meta=t_meta,
                        branch="safe_fallback_invalid_docs",
                    )
                except Exception:
                    pass
                response_time = int((time.time() - start_time) * 1000)
                log_usage(
                    user.get("username", "unknown"),
                    user.get("role", "unknown"),
                    text,
                    "success",
                    None,
                    response_time,
                    len(doc_dicts) if isinstance(doc_dicts, list) else 0,
                    len((text or "").strip()),
                    len(short_answer),
                )
                _emit_perf_report(t_meta, perf_start, text, short_answer, connection_id)
                return

        simple_recovery_type = _classify_simple_recovery_query_type(
            text,
            original_query_text=original_query_text,
            original_arabic_text=(original_arabic_text if arabic_mode else ""),
        )
        S.logger.info(
            "[SIMPLE QUERY TRACE] category=%s family_v2=%s ar_type=%s definition=%s list=%s fact=%s explanation_intent=%s docs=%d candidates=%d",
            simple_recovery_type,
            _classify_query_family_v2(text),
            ar_query_type,
            bool(is_definition_query),
            bool(_is_targeted_list_question(text)),
            bool(_classify_query_family_v2(text) == "fact_entity"),
            bool(
                _is_explanation_intent_query(original_query_text)
                or _is_explanation_intent_query(text)
                or (arabic_mode and _is_explanation_intent_query(original_arabic_text))
            ),
            len(doc_dicts or []),
            len(explanation_candidate_doc_dicts or []),
        )
        explanation_mode = bool(simple_recovery_type == "relationship_explanation")
        if explanation_mode and not is_generation_query_requested:
            explanation_source_docs = _dedup_docs_exact_text(
                list(doc_dicts or []) + [
                    candidate_doc for candidate_doc in (explanation_candidate_doc_dicts or [])
                    if candidate_doc not in (doc_dicts or [])
                ]
            ) or (explanation_candidate_doc_dicts or doc_dicts)
            explanation_builder_query = text
            explanation_ranked_docs = _rank_explanation_docs_for_query(
                explanation_builder_query,
                explanation_source_docs,
                max_docs=3,
            )
            if (
                not explanation_ranked_docs
                and arabic_mode
                and original_arabic_text
                and not bool(t_meta.get("ar_external_query_provider"))
            ):
                try:
                    external_text_for_rag, external_query_provider = await _build_external_arabic_explanation_query(original_arabic_text, t_meta)
                except Exception:
                    S.logger.exception("[EXPLANATION MODE] external_non_llm_fallback_failed")
                    external_text_for_rag, external_query_provider = "", "failed"
                if external_text_for_rag:
                    try:
                        external_docs_raw = await _search_fast_minimal_async(external_text_for_rag, top_k=10) or []
                        if "protected_terms" in locals() and protected_terms:
                            external_docs_raw = S._filter_docs_by_protected_terms(external_docs_raw or [], protected_terms)
                        external_docs_raw = S._filter_results_to_active_sources(external_docs_raw or [])
                        external_doc_dicts = _prepare_rag_doc_dicts_shared(external_docs_raw, external_text_for_rag)
                        external_ranked_docs = _rank_explanation_docs_for_query(
                            external_text_for_rag,
                            external_doc_dicts,
                            max_docs=3,
                        )
                    except Exception:
                        S.logger.exception("[EXPLANATION MODE] external_non_llm_fallback_retrieval_failed provider=%s", external_query_provider)
                        external_ranked_docs = []
                    if external_ranked_docs:
                        S.logger.info(
                            "[EXPLANATION MODE] external_non_llm_fallback accepted provider=%s docs=%d",
                            external_query_provider,
                            len(external_ranked_docs),
                        )
                        explanation_builder_query = external_text_for_rag
                        explanation_ranked_docs = external_ranked_docs
                    else:
                        S.logger.info(
                            "[EXPLANATION MODE] external_non_llm_fallback weak provider=%s docs=%d",
                            external_query_provider,
                            len(external_docs_raw or []) if 'external_docs_raw' in locals() else 0,
                        )
            answer_generation_t0 = time.perf_counter()
            semantic_top_docs = _dedup_docs_exact_text(
                _prepare_rag_doc_dicts_shared(relevant_docs or [], explanation_builder_query)
                if relevant_docs else []
            )
            explanation_answer = RAG_NO_MATCH_RESPONSE
            explanation_source_docs = []
            explanation_stage = "not_found"
            fallback_stages: list[tuple[str, list[dict], int]] = [
                ("explanation_ranked_docs", explanation_ranked_docs or [], 3),
                ("reranker_top_docs", list(doc_dicts or []), 5),
                ("semantic_top_docs", semantic_top_docs, 5),
            ]
            for stage_name, stage_docs, stage_limit in fallback_stages:
                stage_docs = _dedup_docs_exact_text(list(stage_docs or []))[:stage_limit]
                if not stage_docs:
                    S.logger.info("[FINAL GATE TRACE] category=%s stage=%s docs=0 decision=skip_empty", simple_recovery_type, stage_name)
                    continue
                candidate_answer = await _build_controlled_explanation_answer(
                    explanation_builder_query,
                    stage_docs,
                    language=("ar" if arabic_mode else "en"),
                    original_query_text=(original_arabic_text if arabic_mode else original_query_text),
                )
                candidate_answer = str(candidate_answer or "").strip() or RAG_NO_MATCH_RESPONSE
                accepted = candidate_answer.lower() != RAG_NO_MATCH_RESPONSE.lower()
                S.logger.info(
                    "[FINAL GATE TRACE] category=%s stage=%s docs=%d accepted=%s answer_chars=%d",
                    simple_recovery_type,
                    stage_name,
                    len(stage_docs),
                    bool(accepted),
                    len(candidate_answer),
                )
                if accepted:
                    explanation_answer = candidate_answer
                    explanation_source_docs = stage_docs
                    explanation_stage = stage_name
                    break
            if explanation_answer.lower() == RAG_NO_MATCH_RESPONSE.lower():
                extraction_docs = _dedup_docs_exact_text(
                    list(explanation_ranked_docs or [])
                    + list(doc_dicts or [])
                    + list(semantic_top_docs or [])
                )[:8]
                extracted_answer = _safe_grounded_concise_explanation_extraction(explanation_builder_query, extraction_docs, max_lines=2)
                extracted_answer = str(extracted_answer or "").strip() or RAG_NO_MATCH_RESPONSE
                accepted_extraction = extracted_answer.lower() != RAG_NO_MATCH_RESPONSE.lower()
                S.logger.info(
                    "[FINAL GATE TRACE] category=%s stage=safe_grounded_concise_extraction docs=%d accepted=%s answer_chars=%d",
                    simple_recovery_type,
                    len(extraction_docs),
                    bool(accepted_extraction),
                    len(extracted_answer),
                )
                if accepted_extraction:
                    explanation_answer = extracted_answer
                    explanation_source_docs = extraction_docs
                    explanation_stage = "safe_grounded_concise_extraction"
            if explanation_answer.lower() == RAG_NO_MATCH_RESPONSE.lower():
                S.logger.info("[EXPLANATION MODE] fallback=not_found_after_cascade")
            else:
                S.logger.info("[EXPLANATION MODE] cascade_accept stage=%s docs=%d", explanation_stage, len(explanation_source_docs or []))
            t_meta["answer_generation_ms"] = int(round((time.perf_counter() - answer_generation_t0) * 1000))
            explanation_answer = str(explanation_answer or "").strip() or RAG_NO_MATCH_RESPONSE
            try:
                _save_last_answer_state(connection_id, text, explanation_answer, explanation_source_docs)
                _append_conversation_turn(
                    connection_id,
                    original_arabic_text if arabic_mode else text,
                    explanation_answer,
                )
            except Exception:
                S.logger.exception("[FOLLOWUP] save state failed (WS controlled explanation)")
            try:
                await send_final_response(
                    connection_id,
                    explanation_answer,
                    "ar" if arabic_mode else xtts_lang,
                    effective_query_tts,
                    websocket=websocket,
                    sources=len(explanation_source_docs),
                    arabic_mode=arabic_mode,
                    t_meta=t_meta,
                    branch="controlled_explanation",
                )
            except Exception:
                pass
            try:
                response_time = int((time.time() - start_time) * 1000)
                log_usage(
                    user.get("username", "unknown"),
                    user.get("role", "unknown"),
                    original_arabic_text if arabic_mode else text,
                    "success",
                    None,
                    response_time,
                    len(explanation_source_docs),
                    len((original_arabic_text if arabic_mode else text or "").strip()),
                    len(explanation_answer),
                )
            except Exception:
                pass
            _emit_perf_report(t_meta, perf_start, text, explanation_answer, connection_id)
            return

        compare_left, compare_right = _compare_terms_from_query(text)
        if compare_left and compare_right and _is_compare_query(text):
            S.logger.info(
                "[COMPARE ROUTE][WS] deterministic_aligned left=%s right=%s router_mode=%s",
                compare_left,
                compare_right,
                doc_router_mode,
            )
            comparison_synthesis_start = time.perf_counter()
            if arabic_mode:
                t_meta["comparison_synthesis_start"] = comparison_synthesis_start
            short_answer = _compare_answer_from_docs(text, doc_dicts) or RAG_NO_MATCH_RESPONSE
            if arabic_mode:
                comparison_synthesis_end = time.perf_counter()
                t_meta["comparison_synthesis_end"] = comparison_synthesis_end
                comparison_synthesis_ms = int(round((comparison_synthesis_end - comparison_synthesis_start) * 1000))
                t_meta["comparison_synthesis_ms"] = comparison_synthesis_ms
                S.logger.info("[AR PERF] comparison_synthesis_ms=%s", comparison_synthesis_ms)
            try:
                _save_last_answer_state(connection_id, text, short_answer, doc_dicts)
                _append_conversation_turn(connection_id, text, short_answer)
            except Exception:
                S.logger.exception("[FOLLOWUP] save state failed (WS compare aligned)")
            try:
                await send_final_response(
                    connection_id,
                    short_answer,
                    "ar" if arabic_mode else xtts_lang,
                    effective_query_tts,
                    websocket=websocket,
                    sources=len(doc_dicts),
                    arabic_mode=arabic_mode,
                    t_meta=t_meta,
                    branch="comparison_aligned",
                )
            except Exception:
                pass
            response_time = int((time.time() - start_time) * 1000)
            log_usage(
                user.get("username", "unknown"),
                user.get("role", "unknown"),
                text,
                "success",
                None,
                response_time,
                len(doc_dicts),
                len((text or "").strip()),
                len(short_answer),
            )
            _emit_perf_report(t_meta, perf_start, text, short_answer, connection_id)
            return

        generation_query_requested = S._is_llm_generation_query(original_query_text)
        generation_source_query = original_query_text if generation_query_requested else text
        if S._use_early_generation_shortcut(original_query_text, doc_router_mode):
            S.logger.info("[LLM GENERATION MODE][WS]")
            generation_docs = S._select_generation_context_docs(generation_source_query, doc_dicts, max_docs=5)
            if len(generation_docs or []) < 1 and doc_dicts:
                generation_docs = list(doc_dicts)[:5]
            generation_context = _build_generation_context(generation_source_query, generation_docs, max_chars=3600)

            context_sufficient = _has_sufficient_context(
                generation_source_query,
                generation_context,
                relevant_chunks=len(generation_docs or []),
            )
            S.logger.info(
                "[LLM GENERATION CONTEXT CHECK][WS] chunks=%s token_hits=%s sufficient=%s",
                len(generation_docs or []),
                count_token_matches(extract_keywords(generation_source_query), generation_context),
                context_sufficient,
            )
            if not context_sufficient:
                composed = _compose_grounded_generation_answer(generation_source_query, generation_context)
                if composed and _is_answer_grounded_in_docs(composed, doc_dicts or [], query_text=text):
                    short_answer = composed
                else:
                    short_answer = _apply_not_found_ux(text, RAG_NO_MATCH_RESPONSE, doc_dicts if isinstance(doc_dicts, list) else [])
                try:
                    # On not-found, this clears any stale prior state.
                    _save_last_answer_state(connection_id, text, short_answer, doc_dicts)
                    _append_conversation_turn(connection_id, text, short_answer)
                except Exception:
                    S.logger.exception("[FOLLOWUP] save state failed (WS generation insufficient)")
                try:
                    await send_final_response(
                        connection_id,
                        short_answer,
                        "ar" if arabic_mode else xtts_lang,
                        effective_query_tts,
                        websocket=websocket,
                        sources=len(doc_dicts),
                        arabic_mode=arabic_mode,
                        t_meta=t_meta,
                        branch="generation_insufficient_context",
                    )
                except Exception:
                    pass
                _emit_perf_report(t_meta, perf_start, text, short_answer, connection_id)
                return

            bridge_rules = ""
            if S._doc_router_cross_corpus_bridge(generation_source_query):
                bridge_rules = (
                    "\nBRIDGE SYNTHESIS:\n"
                    "- Cite each source by the document name/title exactly as it appears in the context.\n"
                    "- Name requested models, frameworks or concepts explicitly when they appear in the context.\n"
                    "- Synthesize across sources only when each fact is supported by the provided context.\n"
                )
            generation_system_prompt = (
                f"{CUSTOMER_SUPPORT_AGENT_SYSTEM_PROMPT}\n\n"
                "Use ONLY the provided context.\n\n"
                "Your task:\n"
                "* explain clearly in a friendly support tone\n"
                "* summarize key ideas\n"
                "* compare concepts when asked\n\n"
                "Guidelines:\n"
                "* Use full sentences\n"
                "* Be clear and structured\n"
                "* Use bullet points for comparisons\n"
                "* Summaries should be 2–5 sentences\n"
                f"{bridge_rules}\n"
                "IMPORTANT:\n"
                "* Do NOT invent information or use outside knowledge\n"
                "* If the answer cannot be derived from context, say warmly that the detail "
                "is not in the uploaded help materials\n"
            )
            generation_query = S._rewrite_generation_query_for_grounded_llm(generation_source_query)
            generation_answer = await call_llm_with_context(
                query=generation_query,
                context=generation_context,
                system_prompt=generation_system_prompt,
            )
            if str(generation_answer or "").strip().lower() == RAG_NO_MATCH_RESPONSE.lower():
                generation_retry_prompt = generation_system_prompt
                generation_answer = await call_llm_with_context(
                    query=generation_query,
                    context=generation_context,
                    system_prompt=generation_retry_prompt,
                )
            short_answer = str(generation_answer or "").strip() or RAG_NO_MATCH_RESPONSE
            if short_answer.lower() == RAG_NO_MATCH_RESPONSE.lower():
                composed = _compose_grounded_generation_answer(generation_source_query, generation_context)
                if composed and _is_answer_grounded_in_docs(composed, doc_dicts or [], query_text=text):
                    short_answer = composed
                else:
                    short_answer = _apply_not_found_ux(text, RAG_NO_MATCH_RESPONSE, doc_dicts)
            elif not _is_answer_grounded_in_docs(short_answer, doc_dicts or [], query_text=text):
                docs_count = len(doc_dicts or [])
                fallback_docs_count = len(generation_docs or [])
                if docs_count == 0 and fallback_docs_count == 0:
                    S.logger.info("[LLM GENERATION MODE][WS] grounded=false action=not_found")
                    S.logger.info("[POST-GUARD CHECK] docs_count=%s grounded=%s decision=%s", docs_count, False, "not_found_no_docs")
                    short_answer = _apply_not_found_ux(text, RAG_NO_MATCH_RESPONSE, doc_dicts)
                else:
                    S.logger.info("[POST-GUARD CHECK] docs_count=%s grounded=%s decision=%s", docs_count, False, "allow_generation_response")
            else:
                S.logger.info("[LLM GENERATION MODE][WS] grounded=true action=accept")
                S.logger.info("[POST-GUARD CHECK] docs_count=%s grounded=%s decision=%s", len(doc_dicts or []), True, "accept_grounded")
            short_answer = S._ensure_bridge_source_signals(
                text,
                S._format_generation_answer_by_query(text, _cleanup_final_answer_text(short_answer)),
            )
            try:
                _save_last_answer_state(connection_id, text, short_answer, doc_dicts)
                _append_conversation_turn(connection_id, text, short_answer)
            except Exception:
                S.logger.exception("[FOLLOWUP] save state failed (WS generation accept)")
            try:
                await send_final_response(
                    connection_id,
                    short_answer,
                    "ar" if arabic_mode else xtts_lang,
                    effective_query_tts,
                    websocket=websocket,
                    sources=len(doc_dicts),
                    arabic_mode=arabic_mode,
                    t_meta=t_meta,
                    branch="generation_accept",
                    user_query=text,
                )
            except Exception:
                pass
            _emit_perf_report(t_meta, perf_start, text, short_answer, connection_id)
            return

        def _ws_counted_list_context_rescue(current_docs: Optional[List[Dict[str, Any]]] = None) -> Optional[str]:
            if not _is_targeted_list_question(text):
                return None
            query_info = S._detect_short_symbolic_list_query(text)
            if not query_info:
                return None
            source_docs: List[Dict[str, Any]] = []
            for doc in list(current_docs or doc_dicts or []) + list(relevant_docs or []):
                if isinstance(doc, dict):
                    source_docs.append(doc)
            if not source_docs:
                return None

            def _doc_text(doc: Dict[str, Any]) -> str:
                return str(
                    (doc or {}).get("page_content")
                    or (doc or {}).get("text")
                    or (doc or {}).get("content")
                    or ""
                )

            def _items_supported(answer_text: str, evidence_text: str) -> bool:
                evidence_norm = S._normalize_symbolic_list_surface(evidence_text)
                if not evidence_norm:
                    return False
                rows = [
                    re.sub(r"^\s*(?:[-•*]|\d+[.)])\s+", "", line).strip()
                    for line in str(answer_text or "").splitlines()
                    if line.strip()
                ]
                if len(rows) < 2:
                    return False
                for row in rows:
                    tokens = [tok for tok in re.findall(r"[a-z0-9']+", S._normalize_symbolic_list_surface(row)) if len(tok) >= 3]
                    if not tokens or not all(tok in evidence_norm for tok in tokens):
                        return False
                return True

            evidence_blocks: List[str] = []
            for doc in source_docs[:12]:
                body = _doc_text(doc)
                if body.strip():
                    evidence_blocks.append(body)
            combined_evidence = "\n\n".join(evidence_blocks)
            search_blocks = list(evidence_blocks) + ([combined_evidence] if combined_evidence else [])
            local_support = _collect_local_window_support(source_docs)
            for block in search_blocks:
                rescued = S._extract_counted_list_labels_from_context(text, block, query_info)
                if not rescued or not _items_supported(rescued, block):
                    continue
                list_ok, list_reason, shaped = _assess_list_coherence(
                    text,
                    rescued,
                    strict_fast=False,
                    local_support=local_support,
                )
                if list_ok and shaped:
                    S.logger.info("[WS COUNTED LIST RESCUE] accepted=true reason=%s", list_reason)
                    return shaped
                count_target = query_info.get("count")
                item_count = len([line for line in rescued.splitlines() if line.strip()])
                if isinstance(count_target, int) and item_count == count_target:
                    S.logger.info("[WS COUNTED LIST RESCUE] accepted=true reason=count_grounded count=%s", count_target)
                    return rescued
            return None

        # Fast/simple early selector for definition/list/overview queries.
        if _is_metric_fact_query(text) and not _is_attribute_lookup_query(text) and doc_dicts and not S._skip_deterministic_rag_shortcuts(text, doc_router_mode):
            metric_pool = list(doc_dicts or [])
            rescue_q = " ".join(_evidence_concept_tokens(text)[:6]).strip()
            if rescue_q:
                kpi_rescue = await _search_fast_minimal_async(rescue_q, top_k=8) or []
                if kpi_rescue:
                    metric_pool = _merge_rescue_docs_and_rerank(text, metric_pool, kpi_rescue, top_k=12)
            metric_answer = _extract_metric_fact_answer(text, metric_pool)
            if not metric_answer and metric_pool:
                anchored = _select_fact_anchor_docs(
                    text,
                    metric_pool,
                    top_k=min(8, len(metric_pool)),
                    scan_limit=min(25, len(metric_pool)),
                )
                metric_answer = _extract_metric_fact_answer(text, anchored) or metric_answer
            if metric_answer:
                try:
                    await send_final_response(
                        connection_id,
                        metric_answer,
                        "ar" if arabic_mode else xtts_lang,
                        effective_query_tts,
                        websocket=websocket,
                        sources=len(doc_dicts),
                        arabic_mode=arabic_mode,
                        t_meta=t_meta,
                        branch="metric_fact_symbolic",
                        user_query=text,
                    )
                except Exception:
                    pass
                _emit_perf_report(t_meta, perf_start, text, metric_answer, connection_id)
                return

        stream_pre_simple = {"used_llm": True, "answer_type": "doc_router_multi_source"}
        if doc_router_mode != "multi_source_synthesis":
            answer_generation_t0 = time.perf_counter()
            stream_pre_simple = _shared_rag_final_answer_decision(text, doc_dicts, llm_text=None)
            stream_pre_simple = _enforce_runtime_answer_acceptance(text, stream_pre_simple, doc_dicts)
            t_meta["answer_generation_ms"] = int(round((time.perf_counter() - answer_generation_t0) * 1000))
        else:
            S.logger.info("[DOC ROUTER] deterministic_bypass=pre_simple reason=multi_source_synthesis")
        if not stream_pre_simple.get("used_llm", True) and not S._skip_deterministic_rag_shortcuts(text, doc_router_mode):
            short_answer = _apply_not_found_ux(text, str(stream_pre_simple.get("answer") or RAG_NO_MATCH_RESPONSE), doc_dicts)
            if short_answer == RAG_NO_MATCH_RESPONSE:
                short_answer = _ws_counted_list_context_rescue(doc_dicts) or short_answer
            short_answer = _ws_fix_explanation_answer(text, short_answer, doc_dicts)
            _log_answer_mode_markers(text, doc_dicts, short_answer, source_mode="extractor")
            try:
                _save_last_answer_state(connection_id, text, short_answer, doc_dicts)
                _append_conversation_turn(connection_id, text, short_answer)
            except Exception:
                S.logger.exception("[FOLLOWUP] save state failed (WS pre_simple extractor)")
            try:
                await send_final_response(
                    connection_id,
                    short_answer,
                    "ar" if arabic_mode else xtts_lang,
                    effective_query_tts,
                    websocket=websocket,
                    sources=len(doc_dicts),
                    arabic_mode=arabic_mode,
                    t_meta=t_meta,
                    branch=str(stream_pre_simple.get("answer_type") or "deterministic_pre_simple"),
                )
            except Exception:
                pass
            response_time = int((time.time() - start_time) * 1000)
            log_usage(
                user.get("username", "unknown"),
                user.get("role", "unknown"),
                text,
                "success",
                None,
                response_time,
                len(doc_dicts),
                len((text or "").strip()),
                len(short_answer),
            )
            _emit_perf_report(t_meta, perf_start, text, short_answer, connection_id)
            return

        # Merge adjacent high-ranking chunks for list-style questions (selective)
        text = str(text or "")
        is_list_query = _is_targeted_list_question(text)

        # Safe relevant_docs check
        if not relevant_docs or not isinstance(relevant_docs, list):
            relevant_docs_safe = []
        else:
            relevant_docs_safe = relevant_docs

        # Inspect top-ranked doc to avoid hijacking strong matches
        if relevant_docs_safe:
            top_meta = (relevant_docs_safe[0].get("metadata") or {}) if isinstance(relevant_docs_safe[0], dict) else {}
            top_exact = bool(top_meta.get("exact_phrase_matched") or (relevant_docs_safe[0].get("exact_phrase_matched") if isinstance(relevant_docs_safe[0], dict) else False))
            try:
                top_concept_hits = int(top_meta.get("concept_hits", 0) or (relevant_docs_safe[0].get("concept_hits") if isinstance(relevant_docs_safe[0], dict) else 0) or 0)
            except Exception:
                top_concept_hits = 0
        else:
            top_meta = {}
            top_exact = False
            top_concept_hits = 0

        skip_merge = top_exact or top_concept_hits >= 3

        if is_list_query and len(doc_dicts) > 1 and not skip_merge and relevant_docs_safe:
            # Only consider top few candidates
            top_n = min(3, len(doc_dicts))
            top_candidates = doc_dicts[:top_n]

            # Determine top key (source,page) to avoid unrelated merges
            top_key = (top_meta.get("source"), top_meta.get("page"))

            # Prepare query tokens for relevance checking
            q_low = text.lower()
            query_tokens = [tok for tok in re.findall(r"\w+", q_low) if tok not in {"what", "are", "the", "of", "in", "is", "a", "an", "list"}]

            groups = {}
            for idx, d in enumerate(top_candidates):
                meta = d.get("metadata") or {}
                # safe extraction
                source = meta.get("source")
                page = meta.get("page")
                key = (source, page)
                # only consider groups that match top_key
                if key != top_key:
                    continue
                # extract chunk_index safely
                raw_ci = meta.get("chunk_index")
                try:
                    ci = int(raw_ci) if raw_ci is not None else None
                except Exception:
                    ci = None
                groups.setdefault(key, []).append((idx, ci, d))

            merged_created = False
            for (source, page), items in groups.items():
                if source is None and page is None:
                    continue
                # Build items that share query relevance
                relevant_items = []
                for orig_idx, ci, d in items:
                    page_content = str(d.get("page_content") or "")
                    content = page_content.lower()
                    meta = d.get("metadata") or {}
                    # Strong match if exact phrase flagged in metadata for this doc
                    doc_exact = bool(meta.get("exact_phrase_matched") or d.get("exact_phrase_matched"))
                    relevance_hit = False
                    if doc_exact:
                        relevance_hit = True
                    else:
                        try:
                            for tok in query_tokens:
                                if tok and tok in content:
                                    relevance_hit = True
                                    break
                        except Exception:
                            relevance_hit = False
                        if not relevance_hit:
                            # generic fallback: match if full query appears
                            if q_low.strip() and q_low.strip() in content:
                                relevance_hit = True

                    if relevance_hit:
                        # only include if chunk_index available
                        if ci is None:
                            continue
                        relevant_items.append((ci, orig_idx, d))

                if len(relevant_items) < 2:
                    # Need at least two relevant adjacent chunks to consider merging
                    continue

                relevant_items.sort(key=lambda x: x[0])

                # Find adjacent sequences (difference == 1)
                seq = [relevant_items[0]]
                sequences = []
                for cur in relevant_items[1:]:
                    try:
                        if abs(cur[0] - seq[-1][0]) == 1:
                            seq.append(cur)
                        else:
                            if len(seq) >= 2:
                                sequences.append(list(seq))
                            seq = [cur]
                    except Exception:
                        seq = [cur]
                if len(seq) >= 2:
                    sequences.append(list(seq))

                if sequences and not merged_created:
                    # prefer longest adjacent sequence
                    best_seq = max(sequences, key=lambda s: len(s))
                    merged_indexes = [s[0] for s in best_seq]
                    merged_text = "\n".join([str(s[2].get("page_content", "")) for s in best_seq])
                    merged_meta = dict(best_seq[0][2].get("metadata") or {})
                    merged_meta["merged_chunk_indexes"] = merged_indexes
                    merged_meta["merged_source"] = source
                    merged_meta["merged_page"] = page

                    merged_doc = {
                        "page_content": merged_text,
                        "text": merged_text,
                        "content": merged_text,
                        "metadata": merged_meta,
                    }

                    # Remove originals that were merged
                    to_remove = set(s[1] for s in best_seq)
                    new_doc_list = [d for i, d in enumerate(doc_dicts) if i not in to_remove]

                    # Preserve original top-chunk as anchor for list queries — never replace top-1
                    try:
                        original_top = doc_dicts[0]
                    except Exception:
                        original_top = None
                    if original_top is not None:
                        # Insert merged doc after the original top chunk to avoid overriding it
                        # and keep the top-1 anchor intact for list queries
                        # Remove any duplicates while preserving original_top first
                        filtered_new = [d for d in new_doc_list if d is not original_top]
                        doc_dicts = [original_top, merged_doc] + filtered_new
                    else:
                        doc_dicts = [merged_doc] + new_doc_list
                    merged_created = True
                    break
        else:
            pass

        # Generic list-style adjacent-chunk merging and focused span selection
        is_list_query = _is_targeted_list_question(text)

        def _focus_best_answer_span(query: str, txt: str, window: int = 1200) -> str:
            import re
            try:
                if not txt:
                    return txt

                query_tokens = [
                    t for t in re.findall(r"\w+", (query or "").lower())
                    if t not in {"what", "are", "the", "of", "in", "a", "an", "and", "to"}
                ]
                if not query_tokens:
                    return str(txt)[:window]

                best_start = 0
                best_score = -1
                step = 200
                txt_len = len(str(txt))
                for start in range(0, max(1, txt_len), step):
                    end = min(txt_len, start + window)
                    chunk = str(txt[start:end]).lower()

                    token_hits = sum(1 for t in query_tokens if t in chunk)
                    bullet_hits = len(re.findall(r"(?:^|\n)\s*(?:[-•*]|\d+[.)])\s+", chunk))
                    comma_lists = len(re.findall(r"\b\w+\s*,\s*\w+\s*,\s*\w+", chunk))
                    short_phrase_density = len(re.findall(r"\b[a-z]{3,}(?:\s+[a-z]{3,}){0,2}\b", chunk))

                    score = token_hits * 5 + bullet_hits * 4 + comma_lists * 3 + min(short_phrase_density, 10)

                    if score > best_score:
                        best_score = score
                        best_start = start

                return str(txt[best_start: min(txt_len, best_start + window)])
            except Exception:
                try:
                    return str(txt)[:1200]
                except Exception:
                    return ""

        if is_list_query and doc_dicts:
            # Preserve the top-ranked chunk prior to any merge modifications
            top_doc = doc_dicts[0]
            top_rank_idx = 0
            top_meta_doc = top_doc.get("metadata") or {}
            try:
                top_ci = int(top_meta_doc.get("chunk_index", 0))
            except Exception:
                top_ci = 0
            top_source = top_meta_doc.get("source")
            top_page = top_meta_doc.get("page")
            top_n = min(3, len(doc_dicts))
            top_candidates = doc_dicts[:top_n]

            # Build groups by (source, page)
            groups = {}
            for rank_idx, d in enumerate(top_candidates):
                meta = d.get("metadata") or {}
                try:
                    ci = int(meta.get("chunk_index", 0))
                except Exception:
                    ci = 0
                key = (meta.get("source"), meta.get("page"))
                groups.setdefault(key, []).append((rank_idx, ci, d))

            # --- cluster scoring to detect contiguous list-bearing clusters ---
            best_cluster = None
            best_score = -1
            q_low = (text or "").lower()
            query_tokens = [tok for tok in re.findall(r"\w+", q_low) if tok not in {"what", "are", "the", "of", "in", "a", "an", "and", "to"}]

            for (source, page), items in groups.items():
                if source is None and page is None:
                    continue
                items.sort(key=lambda x: x[1])
                seq = [items[0]]
                sequences = []
                for cur in items[1:]:
                    if cur[1] - seq[-1][1] <= 1:
                        seq.append(cur)
                    else:
                        if seq:
                            sequences.append(list(seq))
                        seq = [cur]
                if seq:
                    sequences.append(list(seq))

                for s in sequences:
                    merged_text = "\n".join([x[2].get("page_content", "") for x in s])
                    mt_low = merged_text.lower()
                    token_hits = sum(mt_low.count(t) for t in query_tokens)
                    bullet_hits = len(re.findall(r"(?:^|\n)\s*(?:[-•*]|\d+[.)])\s+", mt_low))
                    comma_lists = len(re.findall(r"\b\w+\s*,\s*\w+\s*,\s*\w+", mt_low))
                    short_phrase_density = len(re.findall(r"\b[a-z]{3,}(?:\s+[a-z]{3,}){0,2}\b", mt_low))
                    cluster_size = len(s)
                    rank_bonus = (top_n - min(x[0] for x in s)) + 1

                    score = token_hits * 5 + bullet_hits * 4 + comma_lists * 3 + min(short_phrase_density, 10) + cluster_size * 2 + rank_bonus * 3

                    if score > best_score:
                        best_score = score
                        best_cluster = {
                            "source": source,
                            "page": page,
                            "items": s,
                            "merged_text": merged_text,
                            "merged_indexes": [x[1] for x in s],
                            "score": score,
                            "best_rank": min(x[0] for x in s),
                        }

            # If we found a candidate cluster, prepare merged doc but DO NOT replace top unless cluster_contains_top is True
            if best_cluster and best_score > 0:
                selected_page = best_cluster.get("page")
                selected_indexes = best_cluster.get("merged_indexes")
                merged_text = best_cluster.get("merged_text")
                merged_meta = dict((best_cluster.get("items")[0][2].get("metadata") or {}))
                merged_meta["merged_chunk_indexes"] = selected_indexes
                merged_meta["merged_source"] = best_cluster.get("source")
                merged_meta["merged_page"] = selected_page

                merged_doc = {
                    "page_content": merged_text,
                    "text": merged_text,
                    "content": merged_text,
                    "metadata": merged_meta,
                }

                def _meta_key(d):
                    m = d.get("metadata") or {}
                    try:
                        ci = int(m.get("chunk_index", 0))
                    except Exception:
                        ci = 0
                    return (m.get("source"), m.get("page"), ci)

                remove_keys = set((best_cluster.get("source"), selected_page, ci) for ci in selected_indexes)
                new_doc_list = [d for d in doc_dicts if _meta_key(d) not in remove_keys]

                # Determine whether the merged cluster actually contains the original top-ranked chunk
                cluster_contains_top = (
                    best_cluster is not None
                    and best_cluster.get("source") == top_source
                    and best_cluster.get("page") == top_page
                    and top_ci in best_cluster.get("merged_indexes", [])
                )
                # Ensure top-1 is NEVER replaced when cluster_contains_top is False
                replace_top = False
                try:
                    top_text = (top_doc.get("page_content") or "").lower()
                    merged_low = (merged_text or "").lower()
                    top_token_hits = sum(top_text.count(t) for t in query_tokens) if query_tokens else 0
                    merged_token_hits = sum(merged_low.count(t) for t in query_tokens) if query_tokens else 0
                    top_bullets = len(re.findall(r"(?:^|\n)\s*(?:[-•*]|\d+[.)])\s+", top_text))
                    merged_bullets = len(re.findall(r"(?:^|\n)\s*(?:[-•*]|\d+[.)])\s+", merged_low))
                    top_commas = len(re.findall(r"\b\w+\s*,\s*\w+\s*,\s*\w+", top_text))
                    merged_commas = len(re.findall(r"\b\w+\s*,\s*\w+\s*,\s*\w+", merged_low))
                except Exception:
                    top_token_hits = merged_token_hits = top_bullets = merged_bullets = top_commas = merged_commas = 0

                top_looks_like_caption = False
                try:
                    head = top_text[:300]
                    if len(top_text.strip()) < 250 or any(k in head for k in ("figure", "table", "caption", "fig.")):
                        top_looks_like_caption = True
                except Exception:
                    top_looks_like_caption = False

                # Only allow replacement when cluster actually contains the top chunk AND merged cluster is clearly stronger
                if cluster_contains_top and top_looks_like_caption:
                    score_top = top_token_hits + top_bullets * 4 + top_commas * 3
                    score_merged = merged_token_hits + merged_bullets * 4 + merged_commas * 3
                    if score_merged >= score_top + 3:
                        replace_top = True

                # If cluster_contains_top is False, force preserve top_doc (rule enforcement)
                if not cluster_contains_top:
                    replace_top = False

                # Log structured merge decision metrics
                try:
                    S.logger.info(
                        "RAG MergeDecision | top_page=%s | selected_page=%s | cluster_contains_top=%s | top_caption=%s | top_score=%.2f | merged_score=%.2f",
                        top_page,
                        selected_page,
                        cluster_contains_top,
                        top_looks_like_caption,
                        float(score_top if 'score_top' in locals() else 0.0),
                        float(score_merged if 'score_merged' in locals() else 0.0),
                    )
                except Exception:
                    pass

                if replace_top:
                    S.logger.info(
                        "RAG MergeAction | Replacing top_doc -> top_page=%s replaced_by_page=%s | reason=%s",
                        top_page,
                        selected_page,
                        "top looks like caption and merged cluster stronger",
                    )
                    merged_meta["replacement_reason"] = "caption_replaced_by_list_cluster"
                    merged_meta["replaced_top_page"] = top_page
                    doc_dicts = [merged_doc] + new_doc_list
                    was_top_replaced = True
                else:
                    remaining = [d for d in doc_dicts if _meta_key(d) not in remove_keys and d is not top_doc]
                    doc_dicts = [top_doc, merged_doc] + remaining
                    S.logger.info(
                        "RAG MergeAction | Preserved top_doc as anchor | top_page=%s | inserted_merged_page=%s",
                        top_page,
                        selected_page,
                    )
                    was_top_replaced = False

                # --- CONTEXT EXPANSION FOR LIST QUERIES ---
                try:
                    # Expand primary chunk to ensure minimum context for lists (1200-2000 chars)
                    min_chars = 1500
                    # Build contiguous context from same source/page around the top_doc
                    primary_meta = (doc_dicts[0].get("metadata") or {})
                    p_source = primary_meta.get("source")
                    p_page = primary_meta.get("page")

                    # collect surrounding chunks from original doc_dicts (not the filtered list)
                    surrounding = []
                    # search doc_dicts (original ordering) to find chunks with same source/page
                    for d in new_doc_list + [top_doc]:
                        m = d.get("metadata") or {}
                        if m.get("source") == p_source and m.get("page") == p_page:
                            surrounding.append((int(m.get("chunk_index", 0) or 0), d.get("page_content") or ""))
                    # include top_doc chunk if not present
                    if not any(ci == top_ci for ci, _ in surrounding):
                        surrounding.append((top_ci, top_doc.get("page_content") or ""))
                    # sort by chunk index
                    surrounding.sort(key=lambda x: x[0])

                    # create expanded text by joining contiguous chunks until min_chars reached
                    expanded = "\n\n".join([c for _, c in surrounding])
                    if len(expanded) < min_chars:
                        # also include next chunks from doc_dicts (best effort)
                        more = []
                        for d in doc_dicts[1:4]:
                            more.append(d.get("page_content") or "")
                        expanded = expanded + "\n\n" + "\n\n".join(more)

                    # Safety cap
                    expanded = expanded[:4000]
                    doc_dicts[0]["page_content"] = expanded
                except Exception:
                    pass

                # --- GENERIC STRUCTURE FOCUS ---
                try:
                    section_detected = None
                    doc_dicts[0]["page_content"] = S._focus_doc_to_query_window(text, doc_dicts[0].get("page_content", ""), window=1800)
                except Exception:
                    pass

                # Ensure list completeness: if the extracted block looks like a list, extend until next heading or no more list lines
                try:
                    pc = doc_dicts[0].get("page_content", "")
                    lines = pc.splitlines()
                    list_lines = []
                    list_mode = False
                    for L in lines:
                        if re.match(r"\s*(?:[-•*]|\d+[.)])\s+", L) or re.match(r"\s*\w+\s*:\s*", L):
                            list_mode = True
                            list_lines.append(L)
                        else:
                            if list_mode:
                                # stop when contiguous list ends
                                break
                    if list_mode and list_lines:
                        # keep the full block starting from first list line until end of contiguous list
                        first_idx = None
                        for i, L in enumerate(lines):
                            if L in list_lines:
                                first_idx = i
                                break
                        if first_idx is not None:
                            cont = []
                            for L in lines[first_idx:]:
                                if re.match(r"\s*(?:[-•*]|\d+[.)])\s+", L) or L.strip() == "" or re.match(r"\s*\w+\s*:\s*", L):
                                    cont.append(L)
                                else:
                                    # stop at new heading-like line
                                    if bool(re.match(r"^\s*[A-Z][A-Za-z0-9\- ,:]{2,120}\s*$", L.strip())):
                                        break
                                    cont.append(L)
                            doc_dicts[0]["page_content"] = "\n".join(lines[:first_idx] + cont)
                except Exception:
                    pass

                # Final focus: ensure generous window for list queries (2000 chars)
                try:
                    doc_dicts[0]["page_content"] = _focus_best_answer_span(text, doc_dicts[0].get("page_content", ""), window=2000)
                except Exception:
                    try:
                        doc_dicts[0]["page_content"] = str(doc_dicts[0].get("page_content", ""))[:2000]
                    except Exception:
                        doc_dicts[0]["page_content"] = ""

                # Structured logging required by validation: top_page, selected_page, was_top_replaced, context_length, section_detected
                try:
                    final_top_page = top_page
                    final_selected_page = selected_page if 'selected_page' in locals() else None
                    context_length = len(doc_dicts[0].get("page_content", ""))
                    S.logger.info(
                        "RAGQueryLog | top_page=%s | selected_page=%s | was_top_replaced=%s | context_length=%s | section_detected=%s",
                        final_top_page, final_selected_page, bool(was_top_replaced), context_length, section_detected
                    )
                except Exception:
                    pass

        # Focus each retrieved doc to a query-centered window to improve relevance
        t_meta["context_focus_start"] = time.perf_counter()
        for d in doc_dicts:
            try:
                focused = S._focus_doc_to_query_window(text, d.get("page_content", ""))
            except Exception:
                try:
                    focused = str(d.get("page_content", ""))[:1200]
                except Exception:
                    focused = ""
            d["page_content"] = focused
            d["text"] = focused
            d["content"] = focused
        t_meta["context_focus_end"] = time.perf_counter()

        # Ensure doc_dicts[0] valid
        if not doc_dicts:
            doc_dicts = [{"page_content": "", "text": "", "content": "", "metadata": {}}]

        if not doc_dicts[0].get("page_content"):
            try:
                doc_dicts[0]["page_content"] = str(doc_dicts[0])
            except Exception:
                doc_dicts[0]["page_content"] = ""

        # Structured log: record top retrieved vs final selected page and whether top-1 was replaced
        try:
            original_top_page = None
            try:
                original_top_page = top_meta.get("page") if isinstance(top_meta, dict) else None
            except Exception:
                original_top_page = None
            final_selected_page = None
            try:
                final_selected_page = (doc_dicts[0].get("metadata") or {}).get("page")
            except Exception:
                final_selected_page = None
            replaced_flag = False
            try:
                if (doc_dicts[0].get("metadata") or {}).get("replaced_top_page"):
                    replaced_flag = True
                elif original_top_page is not None and final_selected_page is not None and str(original_top_page) != str(final_selected_page):
                    replaced_flag = True
            except Exception:
                replaced_flag = False
            S.logger.info(
                "RAG FinalSelection | original_top_page=%s | final_selected_page=%s | top1_replaced=%s | final_preview=%s",
                original_top_page,
                final_selected_page,
                replaced_flag,
                (doc_dicts[0].get("page_content", "")[:300] if doc_dicts and doc_dicts[0].get("page_content") else ""),
            )
        except Exception:
            pass

        is_fact_query_for_llm = _classify_query_family_v2(text) == "fact_entity"
        context_docs_for_llm = _build_compact_fact_context_docs(text, doc_dicts, max_snippets=FACT_CONTEXT_MAX_SNIPPETS, max_chars=FACT_CONTEXT_MAX_CHARS) if is_fact_query_for_llm else doc_dicts
        toon_context = format_rag_context_toon(context_docs_for_llm)
        ws_format_intent = S._classify_response_format_intent(text)
        if ws_format_intent != "default" or doc_router_mode == "multi_source_synthesis":
            context_cap = 5200
        else:
            context_cap = FACT_CONTEXT_MAX_CHARS if is_fact_query_for_llm else (1400 if is_simple_factual_query else 4000)
        if len(toon_context) > context_cap:
            toon_context = toon_context[:context_cap] + "\n...[Context truncated for length]..."
        if is_fact_query_for_llm:
            S.logger.info("[FACT CONTEXT] final_snippets=%s final_chars=%s", len(context_docs_for_llm or []), len(toon_context or ""))

        doc_router_context_rules = ""
        if _classify_query_family_v2(text) == "document_summary" and doc_dicts:
            doc_router_context_rules += (
                "\nDOCUMENT SUMMARY MODE\n"
                "- The user is asking for an overview/summary of the retrieved document evidence.\n"
                "- Do not say the summary, overview, chapter breakdown, or structure is missing when retrieved context is present.\n"
                "- If exact chapter labels are incomplete, summarize the retrieved sections/topics and say they are based on retrieved sections.\n"
                "- Use only topics, section labels, and facts visible in the provided context.\n"
            )
        if doc_router_mode == "multi_source_synthesis":
            doc_router_context_rules = (
                "\nDOC ROUTER MODE: MULTI_SOURCE_SYNTHESIS\n"
                "- Use only the selected active source documents in the context.\n"
                "- Cite each source by the document name/title exactly as it appears in the context.\n"
                "- Label sections by their source document (e.g., 'From <document name>: ...').\n"
                "- Combine facts only when each fact is directly supported by the context.\n"
                "- For comparison or bridge questions, connect concepts across sources only when both are present in the context.\n"
                "- When the query names a model, framework or concept, name and apply it explicitly if it appears in the context.\n"
                "- Do not invent unstated contrasts, formulas, codes, figures, or historical links.\n"
                "- If a requested detail is missing from context, say clearly that it is not in the uploaded materials.\n"
            )
        elif doc_router_mode == "single_source":
            doc_router_context_rules += "\nDOC ROUTER MODE: SINGLE_SOURCE\n- Use only the selected active source document in the context.\n"

        format_intent = ws_format_intent
        format_rules = ""
        if format_intent == "executive_memo":
            format_rules = (
                "\nFORMAT: EXECUTIVE MEMO\n"
                "- Write a professional memo with TO/FROM/DATE/SUBJECT headers.\n"
                "- Translate the findings in the context into clear, actionable recommendations.\n"
                "- Cite frameworks or theories only when supported by the provided context.\n"
            )
        elif format_intent == "quiz_generation":
            format_rules = (
                "\nFORMAT: QUIZ GENERATION\n"
                "- Create exactly 5 numbered multiple-choice questions.\n"
                "- Each question MUST include four labeled options: A) B) C) D)\n"
                "- Base every question only on facts present in the provided context.\n"
                "- End with a section titled 'Answer Key' listing the correct letter for each question.\n"
                "- Do not invent facts not present in the context.\n"
            )
        elif format_intent == "extreme_summary":
            format_rules = (
                "\nFORMAT: EXTREME SUMMARY\n"
                "- Respond with exactly 5 bullet points, each on its own line starting with '- '.\n"
                "- Cover the main points present in the context.\n"
            )
            
        context_block = build_english_stream_context_block(
            toon_context,
            doc_router_context_rules=doc_router_context_rules,
            format_rules=format_rules,
        )
        S.logger.info(f"{connection_id} RAG: {len(relevant_docs)} docs injected as authoritative context")
        # (Deterministic extraction removed to favor pure RAG pipeline and strict system prompt rules)

    S.logger.info(
        "%s context_ready | context_chars=%s fast_path=%s",
        connection_id,
        len(context_block),
        is_simple_factual_query,
    )

    if (
        not arabic_mode
        and _classify_query_family_v2(text) == "document_summary"
        and re.search(r"\b(?:chapter[- ]by[- ]chapter|section[- ]by[- ]section|chapter\s+overview|section\s+overview|chapters?|sections?)\b", text or "", flags=re.IGNORECASE)
        and doc_dicts
    ):
        chapter_overview_answer = _apply_not_found_ux(text, RAG_NO_MATCH_RESPONSE, doc_dicts)
        if chapter_overview_answer and not _ws_generated_not_found_like(chapter_overview_answer):
            t_meta["answer_generation_ms"] = 0
            t_meta["phase14_generation_path"] = "document_summary_section_fallback"
            try:
                _save_last_answer_state(connection_id, text, chapter_overview_answer, doc_dicts)
                _append_conversation_turn(connection_id, text, chapter_overview_answer)
            except Exception:
                S.logger.exception("[FOLLOWUP] save state failed (WS document summary section fallback)")
            try:
                await send_final_response(
                    connection_id,
                    chapter_overview_answer,
                    xtts_lang,
                    effective_query_tts,
                    websocket=websocket,
                    sources=len(doc_dicts),
                    arabic_mode=False,
                    t_meta=t_meta,
                    branch="document_summary_section_fallback",
                    replace=True,
                    user_query=text,
                )
            except Exception:
                pass
            _emit_perf_report(t_meta, perf_start, text, chapter_overview_answer, connection_id)
            return

    # MP-C11 — Fast no-match response (skip LLM when context is clearly weak).
    # Three independent conditions are checked in order; any one triggers the
    # fast path.  The gate is deliberately conservative (thresholds / scoping)
    # so it never fires for greetings, generation queries, arabic mode, small
    # talk, or any query type where weak-doc answers are still useful.
    #
    # Condition A — too few docs: fewer than 2 prepared chunks provides
    #   insufficient evidence for ANY structured answer; skip LLM.
    # Condition B — top similarity too low: the best retrieved chunk is below
    #   the meaningful-relevance floor, meaning the retriever found nothing
    #   semantically close to the query.
    # Condition C — entity absent from every candidate (list / definition
    #   queries only): entity tokens were extracted but not a single doc
    #   contains any of them → the document pool doesn't cover this topic.
    #
    # Fallback: if NO condition fires, proceed normally.
    _mpc11_fast_fail = False
    _mpc11_fail_reason = ""
    if (
        not is_greeting
        and not arabic_mode
        and not _is_smalltalk(text)
        and not is_generation_query_requested
        and doc_router_mode != "multi_source_synthesis"
        and S._classify_response_format_intent(text) == "default"
        and not S._doc_router_cross_corpus_bridge(text)
    ):
        _mpc11_fam = _classify_query_family_v2(text)
        # --- Pre-compute entity-presence in retrieved docs (definition_entity
        # only). When TRUE, Condition B (max_sim<0.25) is skipped because the
        # rerank scoring scale on this project can be raw/negative even when
        # the canonical entity sits in a kept chunk (e.g. table-row matches
        # like "Administrative Theory  Henry Fayol"). Condition C is still
        # applied below; if the entity is genuinely absent everywhere (e.g.
        # "BioChemistry") fast-fail still fires via that route.
        _mpc11_def_entity_present = False
        _mpc11_def_entity_tokens: list[str] = []
        if _mpc11_fam == "definition_entity":
            _mpc11_def_entity_tokens, _ = _query_main_entity_tokens(text, _mpc11_fam)
            if _mpc11_def_entity_tokens:
                for _mpc11_d in (doc_dicts or [])[:10]:
                    _mpc11_text = str(
                        (_mpc11_d or {}).get("page_content") or
                        (_mpc11_d or {}).get("text") or ""
                    )
                    _mpc11_md = dict((_mpc11_d or {}).get("metadata") or {})
                    _mpc11_heading = " ".join(
                        str(_mpc11_md.get(k) or "")
                        for k in ("heading", "section", "title", "chapter")
                    ).lower()
                    _mpc11_window = f"{_mpc11_heading} {_mpc11_text[:2000].lower()}"
                    if any(_token_match_light(_mpc11_window, t) for t in _mpc11_def_entity_tokens):
                        _mpc11_def_entity_present = True
                        break
                if _mpc11_def_entity_present:
                    S.logger.info(
                        "[FAST FAIL EXEMPT] definition_entity entity present in retrieved docs | tokens=%s",
                        _mpc11_def_entity_tokens,
                    )
        # --- Condition A: no retrieved evidence at all ---
        if len(doc_dicts) < 1:
            _mpc11_fast_fail = True
            _mpc11_fail_reason = "doc_count=0"
        # --- Condition B: top similarity below floor ---
        # SKIPPED for definition_entity queries when the entity is clearly
        # present in retrieved docs (the rerank score floor of 0.25 can be
        # too aggressive on negative-scaled rerank scores).
        if not _mpc11_fast_fail and not _mpc11_def_entity_present:
            _mpc11_top_sim = max(
                _max_doc_similarity(relevant_docs or []),
                _max_doc_similarity(doc_dicts or []),
            )
            # Skip similarity floor for fact/metric queries with retrieved evidence.
            if _mpc11_fam == "fact_entity" and len(doc_dicts or []) >= 1 and (
                _mpc11_top_sim > 0.0 or _is_metric_fact_query(text)
            ):
                pass
            elif _mpc11_fam in {"list_entity", "list_structure"} and len(doc_dicts or []) >= 1 and _is_targeted_list_question(text):
                pass
            elif _mpc11_top_sim < 0.25:
                _mpc11_fast_fail = True
                _mpc11_fail_reason = f"max_sim={_mpc11_top_sim:.3f}<0.25"
        # --- Condition C: entity absent from all candidates (list/def only) ---
        if not _mpc11_fast_fail and _mpc11_fam in {
            "list_entity", "list_structure", "definition_entity"
        }:
            if _mpc11_fam == "definition_entity":
                # Reuse the pre-computed result so we don't iterate twice.
                _mpc11_entity_tokens = _mpc11_def_entity_tokens
                _mpc11_entity_present = _mpc11_def_entity_present
            else:
                _mpc11_entity_tokens, _ = _query_main_entity_tokens(text, _mpc11_fam)
                _mpc11_entity_present = False
                if _mpc11_entity_tokens:
                    for _mpc11_d in (doc_dicts or [])[:10]:
                        _mpc11_text = str(
                            (_mpc11_d or {}).get("page_content") or
                            (_mpc11_d or {}).get("text") or ""
                        )
                        _mpc11_md = dict((_mpc11_d or {}).get("metadata") or {})
                        _mpc11_heading = " ".join(
                            str(_mpc11_md.get(k) or "")
                            for k in ("heading", "section", "title", "chapter")
                        ).lower()
                        _mpc11_window = f"{_mpc11_heading} {_mpc11_text[:2000].lower()}"
                        if any(_token_match_light(_mpc11_window, t) for t in _mpc11_entity_tokens):
                            _mpc11_entity_present = True
                            break
            if _mpc11_entity_tokens and not _mpc11_entity_present:
                _mpc11_fast_fail = True
                _mpc11_fail_reason = (
                    f"entity_absent_from_all_docs tokens={_mpc11_entity_tokens}"
                )
    # #region agent log
    try:
        S._dbg7d3bbb("assistify_rag_server.py:call_llm_streaming.mpc11_fast_fail", "fast-fail gate", {
            "fast_fail": bool(_mpc11_fast_fail),
            "fail_reason": _mpc11_fail_reason,
            "family_v2": _classify_query_family_v2(text),
            "doc_dicts_count": len(doc_dicts or []),
            "relevant_docs_count": len(relevant_docs or []),
            "max_doc_similarity": _max_doc_similarity(relevant_docs or []),
            "is_greeting": bool(is_greeting),
            "arabic_mode": bool(arabic_mode),
        }, "H-H")
    except Exception as _e:
        S._dbg7d3bbb("assistify_rag_server.py:call_llm_streaming.mpc11_fast_fail", "fast-fail gate log error",
                   {"err": str(_e)}, "H-H")
    # #endregion
    if _mpc11_fast_fail:
        S.logger.info(
            "[FAST FAIL] skipping LLM due to weak context | reason=%s query=%s",
            _mpc11_fail_reason,
            (text or "")[:120],
        )
        _mpc11_answer = _apply_not_found_ux(text, RAG_NO_MATCH_RESPONSE, doc_dicts)
        if _mpc11_answer == RAG_NO_MATCH_RESPONSE:
            _mpc11_answer = _ws_counted_list_context_rescue(doc_dicts) or _mpc11_answer
        try:
            await send_final_response(
                connection_id,
                _mpc11_answer,
                "ar" if arabic_mode else xtts_lang,
                effective_query_tts,
                websocket=websocket,
                sources=len(doc_dicts),
                arabic_mode=arabic_mode,
                t_meta=t_meta,
                branch="weak_context_fast_fail",
            )
        except Exception:
            pass
        try:
            response_time = int((time.time() - start_time) * 1000)
            log_usage(
                username=user.get("username", "unknown"),
                user_role=user.get("role", "unknown"),
                query_text=text,
                response_status="success",
                error_message=None,
                response_time_ms=response_time,
                rag_docs_found=len(doc_dicts),
                query_length=len(text.strip()),
                response_length=len(_mpc11_answer),
            )
        except Exception:
            pass
        _emit_perf_report(t_meta, perf_start, text, _mpc11_answer, connection_id)
        return

    if doc_router_mode == "multi_source_synthesis" or S._skip_deterministic_rag_shortcuts(text, doc_router_mode):
        stream_pre_decision = {
            "used_llm": True,
            "answer_type": "doc_router_multi_source" if doc_router_mode == "multi_source_synthesis" else "generation_llm_required",
        }
        S.logger.info(
            "[DOC ROUTER] deterministic_bypass=stream_pre_decision reason=%s",
            "multi_source_synthesis" if doc_router_mode == "multi_source_synthesis" else "bridge_or_format_query",
        )
    else:
        answer_generation_t0 = time.perf_counter()
        stream_pre_decision = _shared_rag_final_answer_decision(text, doc_dicts)
        stream_pre_decision = _enforce_runtime_answer_acceptance(text, stream_pre_decision, doc_dicts)
        t_meta["answer_generation_ms"] = int(round((time.perf_counter() - answer_generation_t0) * 1000))
    stream_short_circuit_non_llm = not stream_pre_decision.get("used_llm", True)
    S.logger.info("[TRACE STREAM] short_circuit_non_llm=%s", stream_short_circuit_non_llm)
    S.logger.info("[TRACE STREAM] used_llm=%s", stream_pre_decision.get("used_llm", True))
    S.logger.info("[TRACE STREAM] answer_type=%s", stream_pre_decision.get("answer_type", "llm_required"))

    if stream_short_circuit_non_llm and not S._skip_deterministic_rag_shortcuts(text, doc_router_mode):
        short_answer = stream_pre_decision.get("answer") or RAG_NO_MATCH_RESPONSE
        if _is_smalltalk(text):
            short_answer = _smalltalk_response(text)
        else:
            if _ws_generated_not_found_like(short_answer) and _classify_query_family_v2(text) == "document_summary":
                repaired_short = _apply_not_found_ux(text, RAG_NO_MATCH_RESPONSE, doc_dicts)
                short_answer = repaired_short if repaired_short and not _ws_generated_not_found_like(repaired_short) else _apply_not_found_ux(text, short_answer, doc_dicts)
            else:
                short_answer = _apply_not_found_ux(text, short_answer, doc_dicts)
        if short_answer == RAG_NO_MATCH_RESPONSE:
            short_answer = _ws_counted_list_context_rescue(doc_dicts) or short_answer
        short_answer = _ws_fix_explanation_answer(text, short_answer, doc_dicts)
        _log_answer_mode_markers(text, doc_dicts, short_answer, source_mode="extractor")
        try:
            _save_last_answer_state(connection_id, text, short_answer, doc_dicts)
            _append_conversation_turn(connection_id, text, short_answer)
        except Exception:
            S.logger.exception("[FOLLOWUP] save state failed (WS short_circuit_non_llm)")
        try:
            await send_final_response(
                connection_id,
                short_answer,
                "ar" if arabic_mode else xtts_lang,
                effective_query_tts,
                websocket=websocket,
                sources=len(doc_dicts),
                arabic_mode=arabic_mode,
                t_meta=t_meta,
                branch=str(stream_pre_decision.get("answer_type") or "stream_short_circuit"),
            )
        except Exception:
            pass
        try:
            response_time = int((time.time() - start_time) * 1000)
            log_usage(
                username=user.get("username", "unknown"),
                user_role=user.get("role", "unknown"),
                query_text=text,
                response_status="success",
                error_message=None,
                response_time_ms=response_time,
                rag_docs_found=len(doc_dicts),
                query_length=len(text.strip()),
                response_length=len(short_answer),
            )
        except Exception:
            pass
        _emit_perf_report(t_meta, perf_start, text, short_answer, connection_id)
        return
    
    fact_type_current = _detect_fact_query_type(text)
    is_fact_llm_query = (_classify_query_family_v2(text) == "fact_entity") and bool(fact_type_current)
    stream_family = _classify_query_family(text)
    stream_family_v2 = _classify_query_family_v2(text)
    stream_guard_list_mode = bool(stream_family == "list_structure" or stream_family_v2 == "list_entity")
    if stream_guard_list_mode:
        S.logger.info("[UI STREAM GUARD] enabled=true family_v2=%s family=%s", stream_family_v2, stream_family)

    if arabic_mode:
        if arabic_small_talk:
            system_prompt = (
                "أنت مساعد ودود اسمه Assistify. رد بتحية عربية قصيرة وودية (أقل من 10 كلمات). "
                "أجب بالعربية فقط. لا تستخدم كلمات إنجليزية إطلاقاً."
            )
        else:
            system_prompt = (
                "أنت Assistify، مساعد دعم عملاء ودود لهذا العمل. "
                "القواعد الصارمة:\n"
                "1. أجب بالعربية فقط — يُمنع منعاً باتاً استخدام أي كلمة بالإنجليزية أو الصينية أو أي لغة غير العربية.\n"
                "2. احتفظ بأسماء العلامات التجارية والمنتجات التقنية كما هي بالإنجليزية عند الحاجة.\n"
                "3. لا تبدأ إجابتك بـ 'حسناً' أو 'حسنا' أو 'بالتأكيد'. ابدأ بالإجابة مباشرة.\n"
                "4. أجب في جملة واحدة أو جملتين فقط (أقل من 35 كلمة). "
                "يُحظر تمامًا استخدام القوائم المرقّمة أو النقطية أو أي ترقيم (1. 2. 3. \u2022 -). "
                "اكتب فقرة واحدة متصلة. لا تقطع الجملة في المنتصف أبدًا.\n"
                "5. إجابتك يجب أن تأتي فقط من قاعدة المعرفة (KNOWLEDGE BASE) أدناه. "
                "ترجم محتوى قاعدة المعرفة إلى العربية بأمانة ودقة حرفية — لا تختلق أو تستبدل أو تضيف أي معلومة غير موجودة في قاعدة المعرفة. "
                "كل رقم وكل حقيقة يجب أن تأتي من قاعدة المعرفة مباشرة. اترك الأسماء التقنية كما هي بالإنجليزية."
                f"{context_block}"
            )
    else:
        if is_fact_llm_query and not _is_metric_fact_query(text):
            fact_context_mode = _infer_fact_context_mode_from_docs(doc_dicts)
            system_prompt = _build_strict_fact_system_prompt(
                fact_type_current,
                allow_multi_chunk=(fact_context_mode == "multi_chunk"),
            ) + "\n\n" + context_block
        else:
            format_extra_rules = ""
            user_text_l = text.strip().lower()
            if "list only" in user_text_l:
                format_extra_rules += "\nOUTPUT FORMAT: Return ONLY list items, no intro sentence."
            if "one sentence" in user_text_l:
                format_extra_rules += "\nOUTPUT FORMAT: Return exactly one sentence."
            if _is_metric_fact_query(text):
                format_extra_rules += (
                    "\nFor numeric metric questions: quote exact percentages/scores from the context verbatim; "
                    "name departments when asked which department has the highest/lowest value."
                )
            # Active runtime prompt: include relaxed list extraction / OCR tolerance rules
            system_prompt = build_english_support_system_prompt(format_extra_rules) + f"\n{context_block}"
    # Pick a varied opener phrase for this query (round-robin across the pool)
    prefinal_tts_enabled_for_query = False
    global _arabic_opener_counter
    _chosen_opener: str = _ARABIC_OPENER_PHRASE      # fallback default
    _chosen_opener_pcm: bytes = S._arabic_opener_pcm   # fallback default PCM
    if arabic_mode and prefinal_tts_enabled_for_query and S._arabic_opener_pool:
        _pool_ready = [p for p in _ARABIC_OPENER_PHRASES if S._arabic_opener_pool.get(p)]
        if _pool_ready:
            _chosen_opener = _pool_ready[_arabic_opener_counter % len(_pool_ready)]
            _chosen_opener_pcm = S._arabic_opener_pool[_chosen_opener]
            _arabic_opener_counter += 1

    messages = [{"role": "system", "content": system_prompt}]
    # When KB context is present, skip conversation history to prevent stale
    # old answers from overriding fresh KB data.
    if not relevant_docs:
        messages.extend(history[-10:])
    # In Arabic mode always send the original Arabic question so the model
    # sees an Arabic user turn and stays in Arabic. (text was replaced with
    # the English translation for RAG search — do NOT send that to the LLM.)
    user_message = original_arabic_text.strip() if arabic_mode else text.strip()
    messages.append({"role": "user", "content": user_message})
    
    # Arabic assistant prefill — steers qwen2.5 (a Chinese-first model) to begin
    # its response in Arabic rather than defaulting to Chinese when the KB context
    # is in English.  Ollama supports the 'assistant' partial-response pattern.
    if arabic_mode and prefinal_tts_enabled_for_query:
        messages.append({"role": "assistant", "content": _chosen_opener + " "})
    
    username = user.get("username", "unknown")
    user_role = user.get("role", "unknown")
    query_length = len(text.strip())

    answer_generation_t0 = time.perf_counter()
    deterministic_decision = _shared_rag_final_answer_decision(text, doc_dicts, llm_text=None)
    deterministic_decision = _enforce_runtime_answer_acceptance(text, deterministic_decision, doc_dicts)
    t_meta["answer_generation_ms"] = int(round((time.perf_counter() - answer_generation_t0) * 1000))
    if not deterministic_decision.get("used_llm", True) and not S._skip_deterministic_rag_shortcuts(text, doc_router_mode):
        deterministic_answer = (deterministic_decision.get("answer") or RAG_NO_MATCH_RESPONSE).strip()
        if deterministic_answer == RAG_NO_MATCH_RESPONSE:
            deterministic_answer = _ws_counted_list_context_rescue(doc_dicts) or deterministic_answer
        if _is_smalltalk(text):
            deterministic_answer = _smalltalk_response(text)
        else:
            if _ws_generated_not_found_like(deterministic_answer) and _classify_query_family_v2(text) == "document_summary":
                repaired_deterministic = _apply_not_found_ux(text, RAG_NO_MATCH_RESPONSE, doc_dicts)
                deterministic_answer = repaired_deterministic if repaired_deterministic and not _ws_generated_not_found_like(repaired_deterministic) else _apply_not_found_ux(text, deterministic_answer, doc_dicts)
            else:
                deterministic_answer = _apply_not_found_ux(text, deterministic_answer, doc_dicts)
        if not arabic_mode:
            deterministic_answer = _ws_fix_explanation_answer(text, deterministic_answer, doc_dicts)
        try:
            _log_answer_mode_markers(text, doc_dicts, deterministic_answer, source_mode="extractor")
            _save_last_answer_state(connection_id, text, deterministic_answer, doc_dicts)
            _append_conversation_turn(connection_id, text, deterministic_answer)
            await websocket.send_json({"type": "thinking"})
            await send_final_response(
                connection_id,
                deterministic_answer,
                "ar" if arabic_mode else xtts_lang,
                effective_query_tts,
                websocket=websocket,
                sources=len(relevant_docs),
                arabic_mode=arabic_mode,
                t_meta=t_meta,
                branch=str(deterministic_decision.get("answer_type") or "deterministic_fast_path"),
                replace=True,
                user_query=text,
                extra_payload={
                    "latency": {
                    "first_token_ms": None,
                    "first_sentence_ms": None,
                    "first_opener_ms": None,
                    "first_tts_synthesis_ms": None,
                    "total_ms": int((time.perf_counter() - perf_start) * 1000),
                    },
                    "adaptive_chunk": {
                    "tier": adaptive_manager.get_stats().get("current_tier", "fast"),
                    "words_per_chunk": adaptive_manager.get_stats().get("words_per_chunk", 14),
                    "buffer_delay_s": adaptive_manager.get_stats().get("buffer_delay_s", 0.0),
                    "tts_chunks_processed": 0,
                    },
                },
            )
        except Exception:
            return

        response_time = int((time.time() - start_time) * 1000)
        log_usage(username, user_role, text, "success", None, response_time, len(relevant_docs), query_length, len(deterministic_answer))
        S.logger.info("RAG: deterministic fast-path response (%s chars) in %sms", len(deterministic_answer), response_time)
        _emit_perf_report(t_meta, perf_start, text, deterministic_answer, connection_id)
        return

    try:
        await websocket.send_json({"type": "thinking"})
    except Exception:
        return
    
    # Ollama streaming payload — optimized for speed on 8GB VRAM
    # Phase 2: SPEED UP LLM RESPONSE - fast mode config
    # For simple factual inquiries, decrease max tokens and context size.
    is_simple_factual_query = bool(_is_simple_factual_text_query(text))
    
    # Lower temperature when KB context is present to prevent the LLM drifting
    # away from retrieved facts toward its own parametric knowledge.
    effective_temperature = 0.0 if is_fact_llm_query else (0.1 if is_simple_factual_query else (0.2 if relevant_docs else 0.6))

    _format_intent = S._classify_response_format_intent(text)
    if _format_intent == "executive_memo":
        _llm_num_ctx, _llm_num_predict = 6144, 900
        effective_temperature = 0.2
        is_fact_llm_query = False
        is_simple_factual_query = False
    elif _format_intent == "quiz_generation":
        _llm_num_ctx, _llm_num_predict = 6144, 850
        effective_temperature = 0.15
        is_fact_llm_query = False
        is_simple_factual_query = False
    elif _format_intent == "extreme_summary":
        _llm_num_ctx, _llm_num_predict = 4096, 400
        effective_temperature = 0.1
        is_fact_llm_query = False
        is_simple_factual_query = False
    elif doc_router_mode == "multi_source_synthesis":
        _llm_num_ctx, _llm_num_predict = 6144, 520
        effective_temperature = 0.2
        is_fact_llm_query = False
        is_simple_factual_query = False
    else:
        _llm_num_ctx = 3072
        if is_fact_llm_query or _is_metric_fact_query(text):
            _llm_num_predict = 180
        elif family_v2_current in {"list_entity", "list_structure"}:
            _llm_num_predict = 180
        else:
            _llm_num_predict = 96 if is_simple_factual_query else 150

    if _phase14_trace_enabled(t_meta):
        t_meta["phase14_generation_path"] = "ollama_stream"
        t_meta["phase14_context_cap"] = context_cap if 'context_cap' in locals() else None
        t_meta["phase14_llm_num_ctx"] = _llm_num_ctx
        t_meta["phase14_llm_num_predict"] = _llm_num_predict
    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": True,
        "keep_alive": -1,        # keep model in VRAM between requests
        "options": {
            "num_ctx": _llm_num_ctx,     # IMPORTANT: Must match warmup exactly to avoid VRAM reloading
            "temperature": effective_temperature,
            "top_p": 0.9,
            "num_predict": _llm_num_predict,
            "num_gpu": 99,
        }
    }
    S.logger.info(
        "%s llm_start | fast_path=%s num_ctx=%s num_predict=%s",
        connection_id,
        is_simple_factual_query,
        payload["options"]["num_ctx"],
        payload["options"]["num_predict"],
    )
    S.logger.info(
        "[STREAM DEBUG] event=OLLAMA_PAYLOAD_READY ts=%.6f connection_id=%s num_ctx=%s num_predict=%s stream=%s",
        time.perf_counter(),
        connection_id,
        payload["options"]["num_ctx"],
        payload["options"]["num_predict"],
        payload.get("stream"),
    )
    
    full_response = ""
    ollama_done_received = False
    stream_completed_normally = False
    sentence_index = 0
    _stream_mid_token_timed_out = False
    # Arabic: pre-seed the accumulated response with the opener phrase so that
    # arabic_chars counting is not fooled by a short LLM continuation that starts
    # mid-sentence (after the prefill) and so the final fullText includes the opener.
    if arabic_mode and prefinal_tts_enabled_for_query:
        full_response = _chosen_opener + " "
        sentence_index = 1  # opener occupies index 0

    first_token_time = None
    first_sentence_time = None
    first_tts_chunk_time = None    # first actual XTTS synthesis byte received
    first_opener_time: float | None = None  # pre-cached opener PCM sent (~ms after query)
    vram_llm_active = 0

    # ---- Adaptive chunk sizing ----
    adaptive_words, adaptive_buffer = adaptive_manager.begin_query()
    # Arabic TTS synthesis is inherently slower: force a tiny first chunk (2-3 words)
    # so audio playback begins as quickly as possible, then grow to full chunks.
    if arabic_mode:
        adaptive_words = min(adaptive_words, 3)
    S.logger.info(f"{connection_id} Adaptive TTS: words_per_chunk={adaptive_words} buffer={adaptive_buffer:.2f}s")
    tts_chunk_count = 0
    tts_total_time = 0.0
    final_replace_chunk = False
    suppress_sentinel_stream = False

    # ---- Producer-Consumer Pipeline: LLM → Queue → TTS ----
    tts_enabled_for_query = effective_query_tts
    streaming_tts_enabled_for_query = bool(tts_enabled_for_query and prefinal_tts_enabled_for_query)
    sentence_queue = asyncio.Queue()
    # Reuse the per-connection lock so _tts_arabic_response background tasks
    # and this function never write to the socket concurrently.
    _ws_send_lock = voice_state.ws_write_locks.get(connection_id) or asyncio.Lock()

    async def _safe_ws_json(data):
        async with _ws_send_lock:
            await websocket.send_json(data)

    async def _safe_ws_bytes(data):
        async with _ws_send_lock:
            await websocket.send_bytes(data)

    async def llm_producer():
        """Stream tokens from Ollama and dispatch to TTS queue using a
        timer + word-count state machine.

        FIRST CHUNK — fire as fast as possible:
          • 6-8 words accumulated  OR  700 ms since first LLM token
          • Punctuation is *ignored* for the first chunk.

        SUBSEQUENT CHUNKS — balance quality vs latency:
          • target words (tier-dependent)  OR  500 ms buffer timeout
          •   OR sentence end (preference, never a hard gate)
          • Hard-max to prevent runaway accumulation.
        """
        nonlocal full_response, sentence_index, first_token_time, first_sentence_time, vram_llm_active
        nonlocal adaptive_words, suppress_sentinel_stream, final_replace_chunk
        nonlocal _stream_mid_token_timed_out, ollama_done_received, stream_completed_normally
        word_buffer: list[str] = []
        first_chunk_sent = False
        first_token_wall: float | None = None    # wall-clock of first LLM token
        chunk_start_wall: float | None = None    # wall-clock when current chunk accumulation began

        # Pre-fetch policy values from adaptive manager
        # Arabic: the pre-cached opener fills the ~2-3s synthesis gap, so
        # the first real LLM chunk needs enough words to make a meaningful
        # TTS request.  Using 5-8 words prevents single-character Chinese
        # tokens from causing per-token log spam when the LLM misbehaves.
        if arabic_mode:
            fc_min  = 5
            fc_max  = 8
            fc_tmo  = 0.50   # 500 ms
        else:
            fc_min  = adaptive_manager.first_chunk_min_words()
            fc_max  = adaptive_manager.first_chunk_max_words()
            fc_tmo  = adaptive_manager.first_chunk_timeout_s()
        sub_tmo  = adaptive_manager.subsequent_timeout_s()

        # Track consecutive dropped non-Arabic chunks.  If the LLM is
        # outputting entirely Chinese/English, we must still graduate out of
        # "first chunk" mode after enough tokens so the producer doesn't
        # degenerate into per-token flushing (50+ log lines, wasted CPU).
        _non_arabic_drops = 0

        async def _flush_buffer():
            """Send accumulated words to WebSocket + TTS queue, reset state."""
            nonlocal word_buffer, sentence_index, first_sentence_time, chunk_start_wall, first_chunk_sent
            nonlocal _non_arabic_drops, suppress_sentinel_stream, final_replace_chunk
            chunk_text = " ".join(word_buffer).strip()
            word_buffer = []
            chunk_start_wall = None  # reset timer for next chunk

            if not chunk_text or len(chunk_text) <= 3:
                return

            if _looks_like_rag_no_match_stream(full_response) or _looks_like_rag_no_match_stream(chunk_text):
                suppress_sentinel_stream = True
                final_replace_chunk = True
                return

            # In Arabic mode: sanitize stray English words (keep brand names)
            if arabic_mode:
                chunk_text = _sanitize_arabic_text(chunk_text)
                if not chunk_text or len(chunk_text) <= 3:
                    # Still graduate out of first-chunk mode so we stop
                    # per-token log-spamming when LLM outputs non-Arabic.
                    _non_arabic_drops += 1
                    if _non_arabic_drops >= 3:
                        first_chunk_sent = True
                    return
                # Drop chunks that are purely English/Latin — these are RAG context
                # being regurgitated by the LLM before it switches to Arabic output.
                # _sanitize_arabic_text returns all-English text unchanged (caller
                # decides), so we must explicitly reject it here.
                if not any('\u0600' <= c <= '\u06FF' for c in chunk_text):
                    _non_arabic_drops += 1
                    if _non_arabic_drops >= 3:
                        first_chunk_sent = True
                    return
                # Strip markdown / numbered-list formatting from display text too
                # (prevents "1. التسجيل 2. التحقق..." leaking into the chat bubble).
                chunk_text = _re_mod.sub(r'(?m)^\s*\d+\.\s+', '، ', chunk_text)
                chunk_text = _re_mod.sub(r'(?m)^\s*[-\u2022]\s+', '، ', chunk_text)
                chunk_text = _re_mod.sub(r'^\u060c\s*', '', chunk_text).strip()
                if not chunk_text or len(chunk_text) <= 3:
                    return

            if first_sentence_time is None:
                first_sentence_time = time.perf_counter()
                t_meta["first_sentence_ready"] = first_sentence_time
                S.logger.info(f"LATENCY [First Sentence Ready]: {(first_sentence_time - perf_start)*1000:.0f}ms")

            if stream_guard_list_mode:
                S.logger.info("[UI STREAM GUARD] suppress_chunk index=%s chars=%d", sentence_index, len(chunk_text))
            elif suppress_sentinel_stream:
                S.logger.info("[UI STREAM GUARD] suppress_sentinel index=%s chars=%d", sentence_index, len(chunk_text))
            else:
                # Stream text chunk to the client immediately (both English and Arabic).
                # Arabic text is generated directly by the LLM so it can be shown live,
                # in sync with the TTS audio — same behaviour as English.
                try:
                    await _safe_ws_json({
                        "type": "aiResponseChunk",
                        "text": chunk_text,
                        "index": sentence_index,
                        "done": False,
                        "timing": t_meta if sentence_index == 0 else None
                    })
                    sentence_index += 1
                except Exception:
                    return

            # In text-first safe mode, skip all audio queueing for text queries.
            if streaming_tts_enabled_for_query and (not stream_guard_list_mode):
                await sentence_queue.put(_normalize_digits_for_tts(chunk_text))
            first_chunk_sent = True

        async def _run_non_stream_fallback(*, reset_partial: bool, reason: str) -> bool:
            """Re-run Ollama without streaming when the producer exits early."""
            nonlocal full_response
            if reset_partial:
                full_response = ""
            try:
                fb_payload = dict(payload)
                fb_payload["stream"] = False
                async with aiohttp.ClientSession(
                    timeout=aiohttp.ClientTimeout(total=LLM_FALLBACK_TOTAL_TIMEOUT_S)
                ) as fallback_sess:
                    S.logger.info(
                        "[OLLAMA CALL] endpoint=%s model=%s query_type=%s",
                        OLLAMA_API_URL,
                        OLLAMA_MODEL,
                        reason,
                    )
                    async with fallback_sess.post(OLLAMA_API_URL, json=fb_payload) as fallback_resp:
                        S.logger.info(
                            "[OLLAMA CALL RESULT] status=%s endpoint=%s",
                            fallback_resp.status,
                            OLLAMA_API_URL,
                        )
                        if fallback_resp.status != 200:
                            raise ValueError(f"Fallback API returned {fallback_resp.status}")
                        data = await fallback_resp.json()
                        fallback_text = (data.get("message", {}).get("content", "") or "").strip()
                        if reset_partial:
                            full_response = fallback_text
                        else:
                            full_response += fallback_text
                        if streaming_tts_enabled_for_query and full_response:
                            await sentence_queue.put(_normalize_digits_for_tts(full_response))
                        return bool(full_response.strip())
            except Exception as fb_err:
                mem_fb = S._get_memory_snapshot()
                S.logger.exception(
                    "%s Fallback LLM failed: %s | GPU=%.0fMB CPU=%.0fMB",
                    connection_id,
                    fb_err,
                    mem_fb["gpu_reserved_mb"],
                    mem_fb["cpu_rss_mb"],
                )
            return False

        try:
            timeout = aiohttp.ClientTimeout(total=600, connect=10, sock_read=300)
            _local_stream_session = None
            _stream_sess = S.llm_session
            if _stream_sess is None or _stream_sess.closed:
                _local_stream_session = aiohttp.ClientSession(timeout=timeout)
                _stream_sess = _local_stream_session

            try:
                if is_fact_llm_query:
                    ws_query_type = "fact_entity"
                elif is_simple_factual_query:
                    ws_query_type = "simple_factual"
                elif S._is_llm_generation_query(text):
                    ws_query_type = "generation"
                else:
                    ws_query_type = "general"
                S.logger.info("[OLLAMA CALL] endpoint=%s model=%s query_type=%s", OLLAMA_API_URL, OLLAMA_MODEL, ws_query_type)
                _ollama_post_start = time.perf_counter()
                S.logger.info(
                    "[STREAM DEBUG] event=OLLAMA_POST_START ts=%.6f elapsed_ms=%d connection_id=%s query_type=%s",
                    _ollama_post_start,
                    int(round((_ollama_post_start - perf_start) * 1000)),
                    connection_id,
                    ws_query_type,
                )
                async with _stream_sess.post(OLLAMA_API_URL, json=payload, timeout=timeout) as resp:
                    _ollama_headers_time = time.perf_counter()
                    S.logger.info("[OLLAMA CALL RESULT] status=%s endpoint=%s", resp.status, OLLAMA_API_URL)
                    S.logger.info(
                        "[STREAM DEBUG] event=OLLAMA_HEADERS_RECEIVED ts=%.6f post_to_headers_ms=%d total_elapsed_ms=%d status=%s connection_id=%s",
                        _ollama_headers_time,
                        int(round((_ollama_headers_time - _ollama_post_start) * 1000)),
                        int(round((_ollama_headers_time - perf_start) * 1000)),
                        resp.status,
                        connection_id,
                    )
                    if resp.status != 200:
                        error_text = await resp.text()
                        S.logger.error(f"Ollama streaming error {resp.status}: {error_text}")
                        full_response = "The AI service is temporarily unavailable."
                        return

                    # Read lines with explicit timeouts
                    while True:
                        if cancel_event and cancel_event.is_set():
                            S.logger.info(f"{connection_id} LLM streaming interrupted by user (barge-in)")
                            break

                        try:
                            # Strict timeout for the first token, standard timeout thereafter
                            if _format_intent in {"executive_memo", "quiz_generation", "extreme_summary"}:
                                tmo = 45.0 if first_token_time is None else 20.0
                            else:
                                tmo = S.STREAM_FIRST_TOKEN_TIMEOUT_S if first_token_time is None else S.STREAM_MID_TOKEN_TIMEOUT_S
                            line = await asyncio.wait_for(resp.content.readline(), timeout=tmo)
                        except asyncio.TimeoutError:
                            if first_token_time is None:
                                _timeout_now = time.perf_counter()
                                S.logger.error(
                                    "[STREAM DEBUG] event=FIRST_TOKEN_TIMEOUT ts=%.6f elapsed_ms=%d post_elapsed_ms=%d timeout_s=%.1f accumulated_length=%d preview=%r connection_id=%s",
                                    _timeout_now,
                                    int(round((_timeout_now - perf_start) * 1000)),
                                    int(round((_timeout_now - _ollama_post_start) * 1000)),
                                    tmo,
                                    len(full_response),
                                    full_response[:100],
                                    connection_id,
                                )
                                S.logger.error(f"{connection_id} Timeout waiting for FIRST token from LLM")
                                raise ValueError("TIMEOUT_FIRST_TOKEN")
                            else:
                                _timeout_now = time.perf_counter()
                                S.logger.error(
                                    "[STREAM DEBUG] event=MID_TOKEN_TIMEOUT ts=%.6f elapsed_ms=%d post_elapsed_ms=%d timeout_s=%.1f accumulated_length=%d preview=%r connection_id=%s",
                                    _timeout_now,
                                    int(round((_timeout_now - perf_start) * 1000)),
                                    int(round((_timeout_now - _ollama_post_start) * 1000)),
                                    tmo,
                                    len(full_response),
                                    full_response[:100],
                                    connection_id,
                                )
                                S.logger.error(f"{connection_id} Timeout waiting for mid-stream token from LLM")
                                _stream_mid_token_timed_out = True
                                t_meta["stream_mid_token_timed_out"] = True
                                if await _run_non_stream_fallback(reset_partial=True, reason="mid_stream_timeout_fallback"):
                                    final_replace_chunk = True
                                else:
                                    full_response = "Sorry, I had trouble generating a full answer. Please try again."
                                    final_replace_chunk = True
                                break
                                
                        if not line:
                            stream_completed_normally = True
                            break

                        line_str = line.decode('utf-8').strip()
                        if not line_str:
                            continue

                        try:
                            chunk_data = json.loads(line_str)
                        except json.JSONDecodeError:
                            continue

                        if chunk_data.get("done"):
                            ollama_done_received = True
                            stream_completed_normally = True
                            _done_now = time.perf_counter()
                            S.logger.info(
                                "[STREAM DEBUG] event=OLLAMA_DONE ts=%.6f elapsed_ms=%d post_elapsed_ms=%d accumulated_length=%d preview=%r connection_id=%s",
                                _done_now,
                                int(round((_done_now - perf_start) * 1000)),
                                int(round((_done_now - _ollama_post_start) * 1000)),
                                len(full_response),
                                full_response[:100],
                                connection_id,
                            )
                            break

                        token = chunk_data.get("message", {}).get("content", "")
                        if not token:
                            continue

                        now = time.perf_counter()

                        if first_token_time is None:
                            first_token_time = now
                            first_token_wall = now
                            t_meta["llm_first_token"] = first_token_time
                            S.logger.info(f"LATENCY [LLM First Token]: {(first_token_time - perf_start)*1000:.0f}ms")
                            S.logger.info(
                                "[STREAM DEBUG] event=FIRST_TOKEN_RECEIVED ts=%.6f elapsed_ms=%d post_elapsed_ms=%d token=%r token_length=%d connection_id=%s",
                                now,
                                int(round((now - perf_start) * 1000)),
                                int(round((now - _ollama_post_start) * 1000)),
                                token,
                                len(token),
                                connection_id,
                            )
                            if torch.cuda.is_available():
                                vram_llm_active = torch.cuda.memory_reserved(0) / 1024**2

                        full_response += token
                        S.logger.info(
                            "[STREAM DEBUG] event=TOKEN_ACCUMULATED ts=%.6f chunk=%r chunk_length=%d accumulated_length=%d preview=%r connection_id=%s",
                            now,
                            token,
                            len(token),
                            len(full_response),
                            full_response[:100],
                            connection_id,
                        )

                        if _looks_like_rag_no_match_stream(full_response):
                            suppress_sentinel_stream = True
                            final_replace_chunk = True

                        if not streaming_tts_enabled_for_query:
                            if first_sentence_time is None:
                                first_sentence_time = now
                                t_meta["first_sentence_ready"] = first_sentence_time
                                S.logger.info(f"LATENCY [First Sentence Ready]: {(first_sentence_time - perf_start)*1000:.0f}ms")
                            if stream_guard_list_mode:
                                S.logger.info("[UI STREAM GUARD] suppress_token index=%s chars=%d", sentence_index, len(token))
                            elif suppress_sentinel_stream:
                                S.logger.info("[UI STREAM GUARD] suppress_sentinel_token index=%s chars=%d", sentence_index, len(token))
                            else:
                                await _safe_ws_json({
                                    "type": "aiResponseChunk",
                                    "text": token,
                                    "index": sentence_index,
                                    "done": False,
                                    "timing": t_meta if sentence_index == 0 else None,
                                })
                                sentence_index += 1
                            continue

                        # Tokenise new token(s) into words and accumulate.
                        # Sub-word joining: LLM tokenizers split words across
                        # multiple tokens without a leading space — both in
                        # English ("Sc"+"anning") and Arabic ("أما"+"ز"+"ون").
                        # Tokens that arrive WITHOUT a leading space continue
                        # the previous word and must be concatenated.
                        new_words = token.split()
                        if not new_words:
                            continue

                        if word_buffer and token and not token[0].isspace():
                            # Continuation token — join onto last buffered word
                            word_buffer[-1] += new_words[0]
                            word_buffer.extend(new_words[1:])
                        else:
                            word_buffer.extend(new_words)

                        # Start the chunk timer when first word of this chunk arrives
                        if chunk_start_wall is None:
                            chunk_start_wall = now

                        elapsed = now - chunk_start_wall
                        n_words = len(word_buffer)

                        # ========== FIRST CHUNK — hard override ==========
                        # Completely isolated from adaptive tier logic.
                        # No tier switching, no sentence detection, no tier
                        # buffer timing.  Uses ONLY fixed word count + timer.
                        if not first_chunk_sent:
                            should_flush = (
                                n_words >= fc_max                               # hard cap 8 words
                                or n_words >= fc_min                             # min 6 words reached
                                or (first_token_wall is not None
                                    and (now - first_token_wall) >= fc_tmo)      # 700ms timeout
                            )
                            if should_flush and word_buffer:
                                time_since_first_ms = (
                                    (now - first_token_wall) * 1000
                                    if first_token_wall is not None else 0.0
                                )
                                S.logger.info(
                                    "FIRST CHUNK FLUSHED (override mode) "
                                    "words=%d time_since_first_token=%.0fms",
                                    len(word_buffer), time_since_first_ms,
                                )
                                await _flush_buffer()
                            # CRITICAL: skip subsequent-chunk / tier logic
                            # on every cycle until first chunk is sent.
                            continue

                        # ========== SUBSEQUENT CHUNKS — adaptive tier ==========
                        # Include Arabic punctuation (؟ ، ؛ !) so natural sentence
                        # boundaries flush the buffer instead of the 500ms timeout.
                        has_sentence_end = bool(_re.search(r'[.!?\u061f\u060c\u061b]$', word_buffer[-1]))
                        sub_target = adaptive_manager.subsequent_words()
                        sub_hard   = adaptive_manager.subsequent_hard_max()
                        # Arabic TTS: larger chunks → fewer XTTS round-trips → less
                        # inter-chunk silence (each synthesis call costs ~300-500ms).
                        if arabic_mode:
                            sub_target = max(sub_target, 18)
                            sub_hard   = max(sub_hard,   24)

                        should_flush = (
                            n_words >= sub_hard                              # hard cap
                            or (has_sentence_end and n_words >= sub_target)  # sentence end at target
                            or elapsed >= sub_tmo                            # 500ms timeout
                        )

                        if should_flush and word_buffer:
                            await _flush_buffer()

                # Flush any remaining buffered words
                if word_buffer:
                    await _flush_buffer()
            finally:
                if _local_stream_session is not None and not _local_stream_session.closed:
                    await _local_stream_session.close()

        except asyncio.CancelledError:
            _cancel_now = time.perf_counter()
            S.logger.error(
                "[STREAM DEBUG] event=STREAM_CANCELLED ts=%.6f elapsed_ms=%d accumulated_length=%d preview=%r connection_id=%s",
                _cancel_now,
                int(round((_cancel_now - perf_start) * 1000)),
                len(full_response),
                full_response[:100],
                connection_id,
            )
            raise
        except Exception as e:
            mem = S._get_memory_snapshot()
            if str(e) == "TIMEOUT_FIRST_TOKEN":
                S.logger.warning(f"{connection_id} LLM streaming timeout waiting for first token, falling back to non-stream mode...")
                if not await _run_non_stream_fallback(reset_partial=False, reason="stream_timeout_fallback"):
                    if not full_response:
                        full_response = "Sorry, I am having trouble processing your query."
            else:
                S.logger.exception(f"LLM producer error: {e} | GPU={mem['gpu_reserved_mb']:.0f}MB CPU={mem['cpu_rss_mb']:.0f}MB")
                _partial = full_response.strip()
                _needs_fallback = (
                    not _partial
                    or (sentence_index == 0 and len(_partial) < 40)
                )
                if _needs_fallback:
                    S.logger.warning(
                        "%s LLM producer incomplete response (chars=%s chunks=%s); non-stream fallback",
                        connection_id,
                        len(_partial),
                        sentence_index,
                    )
                    if not await _run_non_stream_fallback(reset_partial=True, reason="producer_error_fallback"):
                        full_response = (
                            _partial
                            if _partial and sentence_index > 0
                            else "Sorry, I had trouble generating a full answer. Please try again."
                        )
                elif not _partial:
                    full_response = "Sorry, I encountered an issue."
        finally:
            # Signal TTS consumer to stop
            await sentence_queue.put(None)

    async def tts_consumer():
        """Read chunks from queue, synthesize via XTTS, stream PCM audio over WebSocket.

        Measures first-chunk latency and feeds it back to the
        AdaptiveChunkManager so subsequent chunks (and future queries)
        use an optimised word count.  Applies an inter-chunk buffer delay
        when the system is classified as slow or medium.
        """
        nonlocal first_tts_chunk_time, adaptive_words, adaptive_buffer
        nonlocal tts_chunk_count, tts_total_time
        # Use the persistent global TTS session (avoids TCP setup cost per query).
        # Fall back to a local session if the global is unavailable (e.g. during
        # startup before startup_event has run).
        _local_tts_session = None
        _tts_sess = S.tts_session
        if _tts_sess is None or _tts_sess.closed:
            _local_tts_session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=None, sock_connect=5, sock_read=None)
            )
            _tts_sess = _local_tts_session
        if not streaming_tts_enabled_for_query:
            return

        try:
            while True:
                if cancel_event and cancel_event.is_set():
                    break

                try:
                    # Timeout prevents waiting forever if producer dies silently
                    sentence = await asyncio.wait_for(sentence_queue.get(), timeout=20.0)
                except asyncio.TimeoutError:
                    S.logger.warning(f"{connection_id} TTS consumer timed out waiting for sentence queue")
                    break

                if sentence is None:
                    break

                if cancel_event and cancel_event.is_set():
                    break

                if not streaming_tts_enabled_for_query:
                    # Skip TTS entirely in safe mode
                    continue

                # Clean text for TTS — strip surrogate-pairs then apply deep
                # Arabic normalization (digits, markdown, punctuation, pauses)
                clean = _re.sub(r'[\U00010000-\U0010ffff]', '', sentence, flags=_re.UNICODE).strip()
                clean = _preprocess_for_tts(clean, language=xtts_lang)
                if not clean:
                    continue

                ws_tts_cache_key = _tts_cache_key(clean, xtts_lang, XTTS_SPEAKER)
                cached_wav = await _tts_cache_get(ws_tts_cache_key)
                ws_tts_cache_hit = cached_wav is not None
                S.logger.info(
                    "[WS TTS CACHE] hit=%s language=%s key=%s text_len=%s",
                    bool(ws_tts_cache_hit),
                    xtts_lang,
                    ws_tts_cache_key,
                    len(clean),
                )
                if arabic_mode:
                    t_meta["tts_cache_hit"] = bool(ws_tts_cache_hit)
                    S.logger.info("[AR PERF] cache_hit=%s stage=tts", bool(ws_tts_cache_hit))
                if cached_wav is not None:
                    chunk_start = time.perf_counter()
                    if not t_meta.get("xtts_send"):
                        t_meta["xtts_send"] = chunk_start
                    try:
                        await _safe_ws_json({"type": "ttsAudioStart", "sampleRate": 24000})
                        pcm_data = _wav_bytes_to_pcm16(cached_wav)
                        if pcm_data:
                            await _safe_ws_bytes(pcm_data)
                            if first_tts_chunk_time is None:
                                first_tts_chunk_time = time.perf_counter()
                                t_meta["first_tts_chunk"] = first_tts_chunk_time
                            t_meta["xtts_last_chunk"] = time.perf_counter()
                        else:
                            await _safe_ws_json({"type": "ttsFallback", "text": clean})
                    finally:
                        await _safe_ws_json({"type": "ttsAudioEnd"})
                    chunk_elapsed = time.perf_counter() - chunk_start
                    tts_chunk_count += 1
                    tts_total_time += chunk_elapsed
                    if arabic_mode:
                        t_meta["tts_ms"] = int(round(chunk_elapsed * 1000))
                        S.logger.info("[AR PERF] tts_ms=%s cache_hit=True", t_meta["tts_ms"])
                    continue

                chunk_start = time.perf_counter()
                if not t_meta.get("xtts_send"):
                    t_meta["xtts_send"] = chunk_start  # first XTTS request time

                try:
                    await _safe_ws_json({"type": "ttsAudioStart", "sampleRate": 24000})

                    # Serialize all XTTS calls system-wide. /tts and the WS
                    # voice-mode consumer share the same single-flight lock
                    # so XTTS is never asked to synthesize two at once.
                    _t_q_wait = time.perf_counter()
                    S.logger.info(
                        f"[TTS QUEUE] ws_consumer waiting_for_synth_lock "
                        f"text_len={len(clean)} lang={xtts_lang}"
                    )
                    async with _XTTS_SYNTH_SEM:
                        _t_q_acq = time.perf_counter()
                        S.logger.info(
                            f"[TTS QUEUE] ws_consumer acquired_synth_lock "
                            f"wait_ms={int((_t_q_acq - _t_q_wait) * 1000)} text_len={len(clean)}"
                        )
                        resp = await _tts_sess.post(
                            f"{XTTS_SERVICE_URL}/synthesize",
                            json={"text": clean, "speaker": XTTS_SPEAKER, "language": xtts_lang},
                        )

                        if resp.status == 200:
                            header_skipped = False
                            header_buf = b''
                            pcm_remainder = b''
                            wav_accum = bytearray()

                            async for chunk in resp.content.iter_chunked(4096):
                                if cancel_event and cancel_event.is_set():
                                    break

                                if chunk:
                                    wav_accum.extend(chunk)

                                if not header_skipped:
                                    header_buf += chunk
                                    if len(header_buf) >= 44:
                                        data = header_buf[44:]
                                        header_skipped = True
                                        header_buf = b''
                                        if not data:
                                            continue
                                    else:
                                        continue
                                else:
                                    data = chunk

                                # Handle PCM16 alignment (2 bytes per sample)
                                if pcm_remainder:
                                    data = pcm_remainder + data
                                    pcm_remainder = b''
                                if len(data) % 2 != 0:
                                    pcm_remainder = data[-1:]
                                    data = data[:-1]

                                if data:
                                    await _safe_ws_bytes(data)
                                    if first_tts_chunk_time is None:
                                        first_tts_chunk_time = time.perf_counter()
                                        t_meta["first_tts_chunk"] = first_tts_chunk_time
                                        first_chunk_latency_s = first_tts_chunk_time - perf_start
                                        _lang_tag = " (Arabic)" if arabic_mode else ""
                                        S.logger.info(f"LATENCY [First XTTS Synthesis{_lang_tag}]: {first_chunk_latency_s*1000:.0f}ms")

                                        # Feed latency into adaptive manager — may adjust mid-query
                                        adaptive_words, adaptive_buffer = (
                                            adaptive_manager.record_first_chunk_latency(first_chunk_latency_s)
                                        )

                            resp.close()

                            # Track per-chunk timing
                            chunk_elapsed = time.perf_counter() - chunk_start
                            tts_chunk_count += 1
                            tts_total_time += chunk_elapsed
                            t_meta["xtts_last_chunk"] = time.perf_counter()  # updated each chunk; final value = end of last chunk
                            if wav_accum and not (cancel_event and cancel_event.is_set()):
                                await _tts_cache_put(ws_tts_cache_key, bytes(wav_accum))
                                S.logger.info(
                                    "[WS TTS CACHE] stored=True language=%s key=%s bytes=%s text_len=%s",
                                    xtts_lang,
                                    ws_tts_cache_key,
                                    len(wav_accum),
                                    len(clean),
                                )
                            if arabic_mode:
                                t_meta["tts_ms"] = int(round(chunk_elapsed * 1000))
                                S.logger.info("[AR PERF] tts_ms=%s cache_hit=False", t_meta["tts_ms"])

                        else:
                            detail = await resp.text()
                            resp.close()
                            S.logger.warning(f"XTTS returned {resp.status}: {detail[:100]}")
                            await _safe_ws_json({"type": "ttsFallback", "text": clean})

                    _t_q_rel = time.perf_counter()
                    S.logger.info(
                        f"[TTS QUEUE] ws_consumer released_synth_lock "
                        f"held_ms={int((_t_q_rel - _t_q_acq) * 1000)} text_len={len(clean)}"
                    )

                    await _safe_ws_json({"type": "ttsAudioEnd"})

                    # ---- Buffer strategy: inter-chunk delay for slower systems ----
                    if adaptive_buffer > 0:
                        await asyncio.sleep(adaptive_buffer)

                except aiohttp.ClientConnectorError:
                    S.logger.warning("XTTS microservice unavailable for TTS consumer")
                    try:
                        await _safe_ws_json({"type": "ttsFallback", "text": clean})
                        await _safe_ws_json({"type": "ttsAudioEnd"})
                    except Exception:
                        pass
                except Exception as e:
                    S.logger.warning(f"TTS consumer error for sentence: {e}")
                    try:
                        await _safe_ws_json({"type": "ttsAudioEnd"})
                    except Exception:
                        pass
        except Exception as e:
            S.logger.warning(f"TTS consumer session error: {e}")
        finally:
            if _local_tts_session is not None and not _local_tts_session.closed:
                await _local_tts_session.close()

    try:
        # For Arabic mode: play the pre-cached opener audio and emit its text as
        # the first visible chunk (index 0) BEFORE the LLM generates any tokens.
        # This fills the ~2-3s XTTS synthesis gap so the user hears audio within
        # ~200ms of the query, not 5-6s later.
        if streaming_tts_enabled_for_query and arabic_mode and _chosen_opener_pcm:
            try:
                await _safe_ws_json({"type": "aiResponseChunk", "text": _chosen_opener,
                                     "index": 0, "done": False, "timing": t_meta})
                await _safe_ws_json({"type": "ttsAudioStart", "sampleRate": 24000})
                await _safe_ws_bytes(_chosen_opener_pcm)
                await _safe_ws_json({"type": "ttsAudioEnd"})
                first_opener_time = time.perf_counter()
                tts_chunk_count += 1
                S.logger.info(
                    f"LATENCY [Opener Audio Played (cached)]: "
                    f"{(first_opener_time - perf_start)*1000:.0f}ms"
                )
                t_meta["first_ack_sent"] = first_opener_time
            except Exception as _op_e:
                S.logger.warning(f"{connection_id} Opener playback error: {_op_e}")

        # Run LLM producer and TTS consumer concurrently — overlapping generation
        try:
            _watchdog_start = time.perf_counter()
            S.logger.info(
                "[STREAM DEBUG] event=WATCHDOG_START ts=%.6f elapsed_ms=%d timeout_s=%.1f connection_id=%s",
                _watchdog_start,
                int(round((_watchdog_start - perf_start) * 1000)),
                STREAM_TOTAL_TIMEOUT_S,
                connection_id,
            )
            await asyncio.wait_for(
                asyncio.gather(llm_producer(), tts_consumer()),
                timeout=STREAM_TOTAL_TIMEOUT_S,
            )
        except asyncio.TimeoutError:
            _watchdog_now = time.perf_counter()
            S.logger.error(
                "[STREAM DEBUG] event=WATCHDOG_TRIGGERED ts=%.6f elapsed_ms=%d watchdog_elapsed_ms=%d accumulated_length=%d preview=%r connection_id=%s",
                _watchdog_now,
                int(round((_watchdog_now - perf_start) * 1000)),
                int(round((_watchdog_now - _watchdog_start) * 1000)),
                len(full_response),
                full_response[:100],
                connection_id,
            )
            S.logger.error(
                f"{connection_id} Streaming pipeline exceeded {STREAM_TOTAL_TIMEOUT_S:.0f}s; forcing non-stream fallback"
            )
            _partial = full_response.strip()
            _stream_complete = ollama_done_received or stream_completed_normally
            if not (_partial and _stream_complete):
                S.logger.warning(
                    "%s Watchdog rejected incomplete stream response "
                    "(chars=%s, chunks=%s, ollama_done=%s, stream_complete=%s); non-stream fallback",
                    connection_id,
                    len(_partial),
                    sentence_index,
                    ollama_done_received,
                    stream_completed_normally,
                )
                if not await _run_non_stream_fallback(reset_partial=True, reason="watchdog_timeout_fallback"):
                    full_response = "Sorry, request timed out. Please try again."
                final_replace_chunk = True

        # Log Arabic response stats (text was already streamed progressively above)
        if arabic_mode and full_response.strip():
            # Count Arabic chars in the LLM-generated portion only (the opener
            # phrase was pre-seeded into full_response before streaming and must
            # not mask a Chinese-only LLM response from the fallback logic).
            _opener_len = len(_chosen_opener) + 1  # +1 for space
            _llm_portion = full_response[_opener_len:].strip() if arabic_mode else full_response
            arabic_chars = sum(1 for c in _llm_portion if '\u0600' <= c <= '\u06FF')
            S.logger.info(f"{connection_id} Arabic mode: streamed response ({len(full_response.strip())} chars, {arabic_chars} Arabic chars in LLM portion)")

            # FALLBACK: If the LLM responded entirely in English/Chinese despite
            # the Arabic system prompt (0 Arabic chars), translate the response
            # into Arabic and send it as a corrected final chunk.
            if arabic_chars == 0 and full_response.strip():
                S.logger.warning(f"{connection_id} Arabic fallback: LLM responded in non-Arabic — translating to Arabic")
                # Detect the actual language of the LLM output so translate_with_llm
                # receives the correct source-language tag.  qwen2.5:3b often outputs
                # Chinese (CJK) even when told not to; passing that as 'en' confuses
                # the translator and it outputs more Chinese.
                _cjk_chars = sum(
                    1 for c in full_response
                    if '\u4e00' <= c <= '\u9fff' or '\u3400' <= c <= '\u4dbf'
                )
                _src_lang = "zh" if _cjk_chars > len(full_response) * 0.2 else "en"
                if _src_lang == "zh":
                    S.logger.warning(
                        f"{connection_id} LLM output is Chinese ({_cjk_chars} CJK chars) — "
                        "forcing direct Arabic translation prompt"
                    )
                try:
                    # For Chinese output, bypass translate_with_llm's source-language
                    # assumption and use a direct Arabic-only prompt.
                    if _src_lang == "zh":
                        _direct_msgs = [
                            {"role": "system", "content": (
                                "أنت مساعد يجيب بالعربية فقط. لا تكتب أي كلمة بالإنجليزية أو الصينية. "
                                "أجب في جملة أو جملتين فقط (أقل من 35 كلمة). "
                                "يُحظر استخدام القوائم المرقمة أو النقطية."
                            )},
                            {"role": "user", "content": f"سؤال المستخدم: {original_arabic_text}\n\nأجب عنه بالعربية:"},
                        ]
                        _fb_payload = {
                            "model": OLLAMA_MODEL,
                            "messages": _direct_msgs,
                            "stream": False,
                            "keep_alive": -1,
                            "options": {"num_ctx": 3072, "num_gpu": 99,
                                        "temperature": 0.1, "num_predict": 95},
                        }
                        import aiohttp as _aiohttp_fb
                        _fb_sess = S.llm_session
                        if _fb_sess is None or _fb_sess.closed:
                            _fb_sess = _aiohttp_fb.ClientSession()
                        S.logger.info("[OLLAMA CALL] endpoint=%s model=%s query_type=arabic_direct_fallback", LLM_URL, OLLAMA_MODEL)
                        async with _fb_sess.post(
                            LLM_URL, json=_fb_payload,
                            timeout=_aiohttp_fb.ClientTimeout(total=20)
                        ) as _fb_resp:
                            S.logger.info("[OLLAMA CALL RESULT] status=%s endpoint=%s", _fb_resp.status, LLM_URL)
                            if _fb_resp.status == 200:
                                _fb_data = await _fb_resp.json()
                                ar_fallback = _fb_data["message"]["content"].strip()
                            else:
                                ar_fallback = full_response  # give up
                    else:
                        ar_fallback = await asyncio.wait_for(
                            translate_with_llm(full_response.strip(), "en", "ar"), timeout=15.0
                        )
                    ar_check = sum(1 for c in ar_fallback if '\u0600' <= c <= '\u06FF')
                    if ar_check >= 3:
                        S.logger.info(
                            "[FINAL ANSWER TRANSLATION] source=%s target=ar applied=True branch=arabic_post_llm",
                            _src_lang,
                        )
                        full_response = ar_fallback
                        # Sanitize the fallback Arabic text before displaying / playing
                        ar_fallback_clean = _sanitize_arabic_text(ar_fallback)
                        full_response = ar_fallback_clean
                        final_replace_chunk = True
                        S.logger.info(
                            f"{connection_id} Arabic fallback: prepared translated final response "
                            f"({len(ar_fallback_clean)} chars)"
                        )
                except Exception as _fb_e:
                    S.logger.warning(f"{connection_id} Arabic fallback translation failed: {_fb_e}")
                    S.logger.info(
                        "[FINAL ANSWER TRANSLATION] source=%s target=ar applied=False reason=exception",
                        _src_lang,
                    )

        stream_post_decision = _shared_rag_final_answer_decision(text, doc_dicts, llm_text=full_response.strip())
        stream_post_decision = _enforce_runtime_answer_acceptance(text, stream_post_decision, doc_dicts)
        S.logger.info("[TRACE STREAM] used_llm=%s", stream_post_decision.get("used_llm", True))
        S.logger.info("[TRACE STREAM] answer_type=%s", stream_post_decision.get("answer_type", "llm"))
        if not stream_post_decision.get("used_llm", True) and not S._skip_deterministic_rag_shortcuts(text, doc_router_mode):
            replacement_answer = stream_post_decision.get("answer") or RAG_NO_MATCH_RESPONSE
            if _is_smalltalk(text):
                replacement_answer = _smalltalk_response(text)
            else:
                replacement_answer = _apply_not_found_ux(text, replacement_answer, doc_dicts)
            if replacement_answer == RAG_NO_MATCH_RESPONSE:
                replacement_answer = _ws_counted_list_context_rescue(doc_dicts) or replacement_answer
            full_response = replacement_answer
            final_replace_chunk = True

        # Validate the full response (English and Arabic)
        if full_response.strip():
            validation_result = validate_response(full_response.strip(), text, relevant_docs)
            if not validation_result.is_valid:
                S.logger.warning(f"Streaming response validation FAILED - Severity: {validation_result.severity}")
                full_response = validation_result.modified_response
                final_replace_chunk = True
            elif validation_result.modified_response:
                full_response = validation_result.modified_response
                final_replace_chunk = True

        if not arabic_mode and full_response.strip():
            if _is_smalltalk(text):
                full_response = _smalltalk_response(text)
            else:
                if _ws_generated_not_found_like(full_response) and _classify_query_family_v2(text) == "document_summary":
                    repaired_response = _apply_not_found_ux(text, RAG_NO_MATCH_RESPONSE, doc_dicts)
                    if repaired_response and not _ws_generated_not_found_like(repaired_response):
                        full_response = repaired_response
                        final_replace_chunk = True
                    else:
                        full_response = _apply_not_found_ux(text, full_response.strip(), doc_dicts)
                else:
                    full_response = _apply_not_found_ux(text, full_response.strip(), doc_dicts)

        if full_response.strip():
            # Store original Arabic question in history (not the English translation)
            history_user_text = original_arabic_text if arabic_mode else text.strip()
            history.append({"role": "user", "content": history_user_text})
            history.append({"role": "assistant", "content": full_response.strip()})
            try:
                _save_last_answer_state(connection_id, text, full_response.strip(), doc_dicts)
            except Exception:
                S.logger.exception("[FOLLOWUP] save state failed (WS path)")

        # Send completion message with latency metrics (Phase 6)
        t_llm_done = time.perf_counter()
        t_meta["llm_first_token"] = first_token_time
        t_meta["llm_full_response"] = t_llm_done
        t_meta["vram_llm_active"] = vram_llm_active
        try:
            answer_generation_start = float(t_meta.get("llm_send") or t_meta.get("context_focus_end") or perf_start)
            answer_generation_ms = int(round((t_llm_done - answer_generation_start) * 1000))
            t_meta["answer_generation_ms"] = answer_generation_ms
            t_meta["llm_generation_ms"] = answer_generation_ms
        except Exception:
            pass

        first_token_ms = ((first_token_time - perf_start) * 1000) if first_token_time else None
        first_sentence_ms = ((first_sentence_time - perf_start) * 1000) if first_sentence_time else None
        first_opener_ms = (first_opener_time - perf_start) * 1000 if first_opener_time else None
        first_tts_ms = (first_tts_chunk_time - perf_start) * 1000 if first_tts_chunk_time else None
        total_ms = (t_llm_done - perf_start) * 1000

        # Sanity check: first_tts_ms must be > first_sentence_ms > first_token_ms.
        # If first_tts_chunk_time was somehow set earlier than first_sentence_time
        # (e.g. a timing race) clamp it so the report stays logical.
        if first_tts_ms is not None and first_sentence_ms is not None:
            if first_tts_ms < first_sentence_ms:
                first_tts_ms = None  # discard bad reading

        # Finalise adaptive chunk stats for this query
        adaptive_manager.finish_query(tts_chunk_count, tts_total_time)
        adaptive_stats = adaptive_manager.get_stats()

        translate_ms = ((t_translate_done - perf_start) * 1000) if t_translate_done else None

        S.logger.info(f"=== LATENCY REPORT [{connection_id}] ===")
        if translate_ms:
            cached_lbl = "cached" if _translate_was_cached else "live"
            S.logger.info(f"  Translation (AR→EN): {translate_ms:.0f}ms ({cached_lbl})")
        S.logger.info(f"  LLM First Token:    {first_token_ms:.0f}ms" if first_token_ms else "  LLM First Token:    N/A")
        if translate_ms and first_token_ms:
            S.logger.info(f"  LLM excl.translate: {first_token_ms - translate_ms:.0f}ms")
        S.logger.info(f"  First Sentence:     {first_sentence_ms:.0f}ms" if first_sentence_ms else "  First Sentence:     N/A")
        if first_opener_ms is not None:
            S.logger.info(f"  Opener (cached):    {first_opener_ms:.0f}ms  ← pre-rendered, not synthesis")
        S.logger.info(f"  First XTTS Synth:   {first_tts_ms:.0f}ms" if first_tts_ms else "  First XTTS Synth:   N/A")
        S.logger.info(f"  Total Pipeline:     {total_ms:.0f}ms")
        S.logger.info(f"  Adaptive Tier:      {adaptive_stats['current_tier']} | words={adaptive_stats['words_per_chunk']} buf={adaptive_stats['buffer_delay_s']:.2f}s")
        S.logger.info(f"  TTS Chunks:         {tts_chunk_count} (total TTS time: {tts_total_time:.2f}s)")
        S.logger.info(f"=== END LATENCY REPORT ===")

        # ================================================================
        # PERFORMANCE TIMING REPORT
        # ================================================================
        try:
            _req_start = t_meta.get("request_start") or perf_start
            _rt_start = t_meta.get("routing_start") or perf_start
            _rt_end   = t_meta.get("routing_end")
            _rv_start = t_meta.get("retrieval_start")
            _rv_end   = t_meta.get("retrieval_end")
            _rk_start = t_meta.get("rerank_start")
            _rk_end   = t_meta.get("rerank_end")
            _cf_start = t_meta.get("context_focus_start")
            _cf_end   = t_meta.get("context_focus_end")
            _xs_send  = t_meta.get("xtts_send")
            _xs_first = t_meta.get("first_tts_chunk")
            _xs_last  = t_meta.get("xtts_last_chunk")

            def _ms(a, b):
                if a is None or b is None:
                    return None
                return int(round((b - a) * 1000))

            _p_routing  = _ms(_rt_start, _rt_end)
            _p_retrieval = _ms(_rv_start, _rv_end)
            _p_rerank   = _ms(_rk_start, _rk_end)
            _p_focus    = _ms(_cf_start, _cf_end)
            _p_llm_ft   = int(round(first_token_ms)) if first_token_ms else None
            _p_llm_tot  = int(round(total_ms))
            _p_xtts_ft  = int(round(first_tts_ms)) if first_tts_ms else None
            _p_xtts_tot = int(round(tts_total_time * 1000)) if tts_total_time else None
            _p_total_be = _ms(_req_start, t_llm_done)
            _p_total_au = _ms(_req_start, _xs_last) if _xs_last else None

            def _fmt(v):
                return f"{v} ms" if v is not None else "N/A"

            _REQ_ID = f"{connection_id} / msg_{abs(hash(text)) % 100000:05d}"
            _q_preview = (text or "")[:60]
            _ans_chars = len(full_response)
            _audio_on  = tts_enabled_for_query and bool(_xs_send)

            S.logger.info("=" * 60)
            S.logger.info("PERFORMANCE TIMING REPORT")
            S.logger.info(f"Request ID: {_REQ_ID}")
            S.logger.info(f'Query: "{_q_preview}"')
            S.logger.info(f"Answer chars: {_ans_chars}  |  Audio enabled: {_audio_on}")
            S.logger.info("=" * 60)
            S.logger.info(f"{'Stage':<30} {'Time':>10}")
            S.logger.info("-" * 60)
            S.logger.info(f"{'Routing':<30} {_fmt(_p_routing):>10}")
            S.logger.info(f"{'Retrieval':<30} {_fmt(_p_retrieval):>10}")
            S.logger.info(f"{'Reranking':<30} {_fmt(_p_rerank):>10}")
            S.logger.info(f"{'Context focus':<30} {_fmt(_p_focus):>10}")
            S.logger.info(f"{'LLM first token':<30} {_fmt(_p_llm_ft):>10}")
            S.logger.info(f"{'LLM total generation':<30} {_fmt(_p_llm_tot):>10}")
            S.logger.info(f"{'XTTS first audio':<30} {_fmt(_p_xtts_ft):>10}")
            S.logger.info(f"{'XTTS total audio':<30} {_fmt(_p_xtts_tot):>10}")
            S.logger.info(f"{'Frontend playback start':<30} {'N/A':>10}")
            S.logger.info("-" * 60)
            S.logger.info(f"{'Total backend response':<30} {_fmt(_p_total_be):>10}")
            S.logger.info(f"{'Total with audio':<30} {_fmt(_p_total_au):>10}")
            S.logger.info("=" * 60)

            # Compact one-liner
            def _c(v):
                return f"{v}ms" if v is not None else "N/A"
            S.logger.info(
                f"[PERF SUMMARY] query=\"{_q_preview}\" "
                f"routing={_c(_p_routing)} retrieval={_c(_p_retrieval)} rerank={_c(_p_rerank)} "
                f"focus={_c(_p_focus)} llm_first={_c(_p_llm_ft)} llm_total={_c(_p_llm_tot)} "
                f"xtts_first={_c(_p_xtts_ft)} xtts_total={_c(_p_xtts_tot)} "
                f"total_backend={_c(_p_total_be)} total_audio={_c(_p_total_au)}"
            )
        except Exception:
            S.logger.exception("[PERF REPORT] failed to print timing table")
        # ================================================================


        # (Deterministic overrides removed for Pure RAG)


        _final_text = _sanitize_arabic_text(full_response.strip()) if arabic_mode else full_response.strip()
        S.logger.info(
            "[STREAM DEBUG] event=FINAL_RESPONSE_READY ts=%.6f full_response_length=%d final_text_length=%d full_response_preview=%r final_text_preview=%r replace=%s connection_id=%s",
            time.perf_counter(),
            len(full_response),
            len(_final_text),
            full_response[:100],
            _final_text[:100],
            final_replace_chunk,
            connection_id,
        )
        if not arabic_mode:
            _final_text = _ws_fix_explanation_answer(text, _final_text, doc_dicts)
            _final_text = S._enforce_unanswerable_detail_refusal(text, _final_text)
            if _ws_generated_not_found_like(_final_text) and _classify_query_family_v2(text) == "document_summary":
                repaired_final = _apply_not_found_ux(text, RAG_NO_MATCH_RESPONSE, doc_dicts)
                if repaired_final and not _ws_generated_not_found_like(repaired_final):
                    _final_text = repaired_final
                    final_replace_chunk = True
                else:
                    _final_text = _apply_not_found_ux(text, _final_text, doc_dicts)
            else:
                _final_text = _apply_not_found_ux(text, _final_text, doc_dicts)
        if _is_rag_no_match_sentinel(_final_text):
            final_replace_chunk = True
        S.logger.info(
            "[STREAM DEBUG] event=SEND_FINAL_RESPONSE ts=%.6f final_text_length=%d final_text_preview=%r send_chunk=%s replace=%s connection_id=%s",
            time.perf_counter(),
            len(_final_text),
            _final_text[:100],
            final_replace_chunk,
            final_replace_chunk or _is_rag_no_match_sentinel(_final_text),
            connection_id,
        )
        _log_answer_mode_markers(text, doc_dicts, _final_text, source_mode=("llm" if stream_post_decision.get("used_llm", True) else "extractor"))
        try:
            await asyncio.wait_for(send_final_response(
                connection_id,
                _final_text,
                "ar" if arabic_mode else xtts_lang,
                tts_enabled_for_query,
                websocket=websocket,
                sources=len(relevant_docs),
                arabic_mode=arabic_mode,
                t_meta=t_meta,
                branch="llm_streaming_final",
                send_chunk=final_replace_chunk,
                replace=final_replace_chunk or _is_rag_no_match_sentinel(_final_text),
                user_query=text,
                extra_payload={
                    "latency": {
                    "first_token_ms": round(first_token_ms) if first_token_ms else None,
                    "first_sentence_ms": round(first_sentence_ms) if first_sentence_ms else None,
                    "first_opener_ms": round(first_opener_ms) if first_opener_ms else None,
                    "first_tts_synthesis_ms": round(first_tts_ms) if first_tts_ms else None,
                    "total_ms": round(total_ms),
                    },
                    "adaptive_chunk": {
                    "tier": adaptive_stats['current_tier'],
                    "words_per_chunk": adaptive_stats['words_per_chunk'],
                    "buffer_delay_s": adaptive_stats['buffer_delay_s'],
                    "tts_chunks_processed": tts_chunk_count,
                    },
                },
            ), timeout=WS_FINALIZE_TIMEOUT_S)
            S.logger.info(
                "%s aiResponseDone_sent | full_text_len=%s sources=%s",
                connection_id,
                len(_final_text),
                len(relevant_docs),
            )
        except Exception:
            pass

        # Analytics
        response_time = int((time.time() - start_time) * 1000)
        log_usage(username, user_role, text, "success", None,
                response_time, len(relevant_docs), query_length, len(full_response))
        S.logger.info(f"RAG: Streamed {sentence_index} sentences ({len(full_response)} chars) in {response_time}ms")
        S.logger.info(f"{connection_id} cleanup_finished")

    except Exception as e:
        response_time = int((time.time() - start_time) * 1000)
        log_usage(username, user_role, text, "error", str(e), response_time, 0, query_length, 0)
        mem = S._get_memory_snapshot()
        S.logger.exception(f"Streaming pipeline error: {e} | GPU={mem['gpu_reserved_mb']:.0f}MB CPU={mem['cpu_rss_mb']:.0f}MB")
        try:
            await send_final_response(
                connection_id,
                "Sorry, I encountered an issue. Let's continue.",
                XTTS_LANGUAGE,
                effective_query_tts,
                websocket=websocket,
                sources=0,
                arabic_mode=False,
                t_meta=t_meta,
                branch="streaming_pipeline_error",
                extra_payload={"error": True},
            )
        except Exception:
            pass

