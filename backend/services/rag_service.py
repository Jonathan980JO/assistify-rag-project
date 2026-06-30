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
from backend.retrieval.routing import _active_rag_search_async
from backend.retrieval.followup import _append_conversation_turn
from backend.retrieval.routing import _apply_concept_filter_to_docs
from backend.retrieval.routing import _apply_not_found_ux
from backend.retrieval.routing import _assess_list_coherence
from backend.retrieval.routing import _build_compact_fact_context_docs
from backend.retrieval.routing import _build_definition_entity_rescue_queries
from backend.retrieval.routing import _build_fact_rescue_queries
from backend.retrieval.routing import _build_generation_context
from backend.retrieval.routing import _build_strict_fact_system_prompt
from backend.retrieval.routing import _classify_query_family
from backend.retrieval.routing import _classify_query_family_v2
from backend.retrieval.routing import _clean_mixed_not_found_response
from backend.retrieval.routing import _clean_ocr_artifacts
from backend.retrieval.routing import _cleanup_final_answer_text
from backend.retrieval.routing import _collect_local_window_support
from backend.retrieval.routing import _compare_terms_from_query
from backend.retrieval.routing import _compose_grounded_generation_answer
from backend.retrieval.routing import _context_grounded_definition_override
from backend.core.tenant_context import _current_user_query
from backend.retrieval.routing import _customer_service_no_match_response
from backend.retrieval.routing import _dedup_docs_exact_text
from backend.retrieval.routing import _definition_explanation_fallback
from backend.retrieval.routing import _definition_structural_signal_delta
from backend.retrieval.routing import _detect_fact_query_type
from backend.services.language_service import _detect_language
from backend.retrieval.routing import _direct_route_answer
from backend.retrieval.routing import _distance_threshold_for_query
from backend.retrieval.routing import _doc_has_explanation_for_entity
from backend.retrieval.routing import _enforce_definition_doc_contamination_guard
from backend.retrieval.routing import _enforce_runtime_answer_acceptance
from backend.retrieval.routing import _evidence_concept_tokens
from backend.retrieval.routing import _extract_definition_sentence
from backend.retrieval.routing import _extract_entity_from_definition_query
from backend.retrieval.routing import _extract_list_from_context
from backend.retrieval.routing import _extract_metric_fact_answer
from backend.retrieval.routing import _extract_overview_chapter_compare_answer
from backend.retrieval.routing import _extract_strict_same_line_person_identity_from_retrieved_docs
from backend.retrieval.routing import _force_clean_definition_sentence
from backend.retrieval.followup import _handle_followup_query
from backend.retrieval.routing import _has_sufficient_context
from backend.retrieval.routing import _indirect_evidence_pool_is_weak
from backend.retrieval.routing import _infer_fact_context_mode_from_docs
from backend.retrieval.routing import _is_answer_grounded_in_docs
from backend.retrieval.routing import _is_compare_query
from backend.retrieval.routing import _is_controlled_definition_entity_query
from backend.retrieval.routing import _is_definition_style_query
from backend.retrieval.routing import _is_explicit_oos_query
from backend.retrieval.routing import _is_feature_only_definition_sentence
from backend.retrieval.followup import _is_followup_query
from backend.retrieval.routing import _is_force_overview_paragraph_query
from backend.retrieval.followup import _is_marked_arabic_resolved_followup
from backend.retrieval.followup import _is_memory_rewrite_query
from backend.retrieval.routing import _is_metric_fact_query
from backend.retrieval.routing import _is_pure_smalltalk_query
from backend.retrieval.routing import _is_safe_definition_fast_path_query
from backend.retrieval.routing import _is_simple_factual_text_query
from backend.retrieval.routing import _is_smalltalk
from backend.retrieval.routing import _is_table_or_classification_sentence
from backend.retrieval.routing import _is_targeted_list_question
from backend.retrieval.routing import _is_weak_retrieval_evidence
from backend.retrieval.routing import _is_wrong_concept_definition_chunk
from backend.retrieval.routing import _log_answer_mode_markers
from backend.retrieval.routing import _log_direct_route_handled
from backend.retrieval.routing import _log_selected_doc_markers
from backend.rag_chunk_heuristics import looks_table_or_heading_like_chunk as _looks_table_or_heading_like_chunk
from backend.retrieval.routing import _max_doc_similarity
from backend.retrieval.followup import _maybe_rewrite_about_entity_question
from backend.retrieval.routing import _merge_rescue_docs_and_rerank
from backend.retrieval.routing import _normalize_context_entities
from backend.retrieval.followup import _normalize_conversational_definition_query
from backend.retrieval.routing import _normalize_definition_query_before_retrieval
from backend.retrieval.routing import _not_found_response
from backend.retrieval.routing import _overview_seed_query
from backend.retrieval.routing import _passes_fast_path_definition_validation
from backend.retrieval.routing import _passes_hybrid_relevance_gate
from backend.retrieval.routing import _passes_strict_definition_relevance_guard
from backend.retrieval.routing import _preclean_list_answer_for_assessment
from backend.retrieval.routing import _prepare_rag_doc_dicts_shared
from backend.retrieval.routing import _query_requires_structure
from backend.retrieval.routing import _query_tokens_for_evidence
from backend.retrieval.routing import _rerank_docs_for_query_intent
from backend.retrieval.routing import _rerank_document_summary_for_coverage
from backend.retrieval.routing import _retrieval_context_is_reliable
from backend.retrieval.routing import _retrieval_evidence_metrics
from backend.retrieval.routing import _retrieve_with_section_bias
from backend.retrieval.routing import _select_document_summary_coverage_docs
from backend.retrieval.followup import _rewrite_bare_comparison_query_from_history
from backend.retrieval.routing import _route_response_language
from backend.retrieval.routing import _s_definition_sentence
from backend.retrieval.followup import _save_last_answer_state
from backend.retrieval.routing import _search_fast_definition_minimal_async
from backend.retrieval.routing import _search_fast_minimal_async
from backend.retrieval.routing import _search_with_query_expansion
from backend.retrieval.routing import _select_fact_anchor_docs
from backend.retrieval.routing import _shared_rag_final_answer_decision
from backend.retrieval.routing import _smalltalk_response
from backend.retrieval.routing import _spelling_correction_preserving_exact_terms
import aiohttp
import asyncio
from backend.retrieval.routing import call_llm_with_context
from backend.retrieval.routing import classify_query_route
from backend.retrieval.routing import collect_indirect_entity_evidence
from backend.retrieval.routing import count_token_matches
from backend.retrieval.routing import detect_query_intent
from backend.retrieval.routing import extract_keywords
from backend.retrieval.routing import is_entity_definition_like
import json
from backend.core.tenant_context import log_usage
import re

S = None


def bind_server(server) -> None:
    """Bind the live server module so extracted helpers can reach shared state."""
    global S
    S = server

_ROUTER_DIRECT_ROUTES = frozenset(
    {"smalltalk", "assistant_meta", "unsupported_unclear", "conversational_ack"}
)

async def call_llm_with_rag(text: str, connection_id: str, user):  # pyright: ignore[reportGeneralTypeIssues]
    global llm_session
    import time
    _current_user_query.set(str(text or ""))
    start_time = time.time()
    S.logger.info("[FLOW] entering call_llm_with_rag")
    S.logger.info("[HTTP PATH ENTER] connection_id=%s", connection_id)
    S.logger.info("[FLOW] query_before = %s", (text or "")[:400])
    retrieval_t0 = time.perf_counter()
    retrieval_ms = 0.0
    extraction_ms = 0.0
    validation_ms = 0.0
    llm_ms = 0.0
    
    user = user or {"username": "anon", "role": "user"}
    if not text or len(text.strip()) < 2:
        return ("I didn't catch that. Could you repeat?", [])

    # ---- ABOUT-ENTITY STANDALONE REWRITE (HTTP path, pre-router) -------
    # Run BEFORE the direct router so shapes like "What about X?" /
    # "وماذا عن X" with a real new entity X aren't mis-classified as
    # `unsupported_unclear`.
    if not _is_memory_rewrite_query(text) and not _is_marked_arabic_resolved_followup(connection_id, text):
        text = _maybe_rewrite_about_entity_question(text)

    from backend.rag_query_prep import prepare_query_for_rag

    prepared = await prepare_query_for_rag(text)
    if prepared.direct_response:
        direct_answer = prepared.direct_response
        try:
            _append_conversation_turn(connection_id, prepared.original, direct_answer)
        except Exception:
            pass
        response_time = int((time.time() - start_time) * 1000)
        try:
            log_usage(
                username=(user or {}).get("username", "unknown"),
                user_role=(user or {}).get("role", "unknown"),
                query_text=prepared.original,
                response_status="success",
                error_message=None,
                response_time_ms=response_time,
                rag_docs_found=0,
                query_length=len(prepared.original),
                response_length=len(direct_answer or ""),
            )
        except Exception:
            pass
        return (direct_answer, [])
    if prepared.rag_query:
        text = prepared.rag_query

    route = classify_query_route(text)
    if route in _ROUTER_DIRECT_ROUTES:
        route_lang = _route_response_language(text)
        direct_answer = _direct_route_answer(text, route, route_lang)
        _log_direct_route_handled(route, text, route_lang)
        if direct_answer == RAG_NO_MATCH_RESPONSE:
            try:
                _save_last_answer_state(connection_id, text, direct_answer, [])
            except Exception:
                S.logger.exception("[FOLLOWUP] save state failed (HTTP direct not-found)")
        try:
            _append_conversation_turn(connection_id, text, direct_answer)
        except Exception:
            pass
        response_time = int((time.time() - start_time) * 1000)
        try:
            log_usage(
                username=(user or {}).get("username", "unknown"),
                user_role=(user or {}).get("role", "unknown"),
                query_text=text,
                response_status="success",
                error_message=None,
                response_time_ms=response_time,
                rag_docs_found=0,
                query_length=len((text or "").strip()),
                response_length=len(direct_answer or ""),
            )
        except Exception:
            pass
        return (direct_answer, [])

    # Generic conversational definition normalization (HTTP path).
    try:
        _norm = _normalize_conversational_definition_query(text)
    except Exception:
        _norm = text
    if _norm and _norm != text:
        S.logger.info("[CONV NORM] (http) '%s' -> '%s'", (text or "")[:160], _norm[:160])
        text = _norm

    _spell_norm = _spelling_correction_preserving_exact_terms(text)
    if _spell_norm and _spell_norm.strip().lower() != (text or "").strip().lower():
        text = _spell_norm

    if _is_smalltalk(text):
        return (_smalltalk_response(text), [])

    history_snapshot = list(S.conversation_history.get(connection_id, []) or [])
    rewritten_comparison_query = _rewrite_bare_comparison_query_from_history(text, history_snapshot, connection_id)
    if rewritten_comparison_query and rewritten_comparison_query != text:
        S.logger.info(
            "[COMPARE FOLLOWUP REWRITE] original=%r rewritten=%r",
            (text or "")[:160],
            rewritten_comparison_query[:160],
        )
        text = rewritten_comparison_query

    # ---- ABOUT-ENTITY STANDALONE REWRITE (HTTP path) -------------------
    # Catch "what about X / how about X / and X / tell me about X / explain
    # X" with a real new entity X BEFORE follow-up routing so we don't
    # inherit the previous answer's topic.
    if not _is_memory_rewrite_query(text) and not _is_marked_arabic_resolved_followup(connection_id, text):
        text = _maybe_rewrite_about_entity_question(text)

    # ---- FOLLOW-UP / EXPLANATION MODE (HTTP path) -----------------------
    # Detect generic clarification intents ("what do you mean?", "explain more",
    # "simplify that"). When detected, answer locally from the previously
    # grounded answer + small chunk window. NO new heavy retrieval.
    if _is_followup_query(text, connection_id):
        S.logger.info("[FOLLOWUP] HTTP follow-up detected: '%s'", (text or "")[:80])
        S.logger.info("[FOLLOWUP ROUTE] triggered for query=%s", text)
        fu_text, fu_docs = await _handle_followup_query(text, connection_id)
        try:
            history = S.conversation_history[connection_id]
            history.append({"role": "user", "content": text.strip()})
            history.append({"role": "assistant", "content": fu_text})
        except Exception:
            pass
        response_time = int((time.time() - start_time) * 1000)
        try:
            log_usage(
                username=(user or {}).get("username", "unknown"),
                user_role=(user or {}).get("role", "unknown"),
                query_text=text,
                response_status="success",
                error_message=None,
                response_time_ms=response_time,
                rag_docs_found=0,
                query_length=len((text or "").strip()),
                response_length=len(fu_text or ""),
            )
        except Exception:
            pass
        try:
            S._set_last_latency_breakdown(connection_id, 0.0, 0.0, 0.0, float(response_time), float(response_time), cache_hit=False)
        except Exception:
            pass
        S.logger.info("[FOLLOWUP] HTTP follow-up answered in %dms", response_time)
        return (fu_text, fu_docs)

    original_query_text = text
    is_generation_query_requested = S._is_llm_generation_query(original_query_text)
    is_bridge_query_requested = S._doc_router_cross_corpus_bridge(original_query_text)
    format_intent_early = S._classify_response_format_intent(original_query_text)
    is_fact_query_early = _classify_query_family_v2(text) in {"fact_entity", "attribute_lookup"}
    if not is_fact_query_early:
        normalized_query, corrected_concept = _normalize_definition_query_before_retrieval(text)
        if normalized_query and normalized_query.strip().lower() != (text or "").strip().lower():
            S.logger.info(
                "RAG pre-retrieval definition normalization applied | original='%s' normalized='%s' concept='%s'",
                (text or "")[:120],
                normalized_query[:120],
                (corrected_concept or "")[:80],
            )
            S.logger.info("[FLOW] query_after = %s", (normalized_query or "")[:400])
            text = normalized_query

    cached_answer = S._simple_rag_cache_get(text)
    if cached_answer:
        S.logger.info("RAG CACHE HIT for query='%s'", (text or "")[:100])
        response_time = int((time.time() - start_time) * 1000)
        log_usage(
            username=(user or {}).get("username", "unknown"),
            user_role=(user or {}).get("role", "unknown"),
            query_text=text,
            response_status="success",
            error_message=None,
            response_time_ms=response_time,
            rag_docs_found=0,
            query_length=len((text or "").strip()),
            response_length=len(cached_answer),
        )
        S.logger.info(
            "LATENCY_BREAKDOWN query='%s' retrieval_ms=0 extraction_ms=0 validation_ms=0 llm_ms=0 total_ms=%d cache_hit=true",
            (text or "")[:80],
            response_time,
        )
        S._set_last_latency_breakdown(connection_id, 0.0, 0.0, 0.0, 0.0, float(response_time), cache_hit=True)
        return (cached_answer, [])

    ready, not_ready_reason = S._kb_is_ready_for_queries()
    if not ready:
        S.logger.info("RAG query blocked while KB not ready | state=%s query='%s'", S._kb_pipeline_state.get("state"), text[:80])
        return ("System is loading the document. Please wait...", [])
    
    # Update conversation timestamp for cleanup
    S.conversation_timestamps[connection_id] = time.time()
    
    # Cleanup old conversations periodically (every 100 requests)
    if len(S.conversation_history) % 100 == 0:
        S.cleanup_old_conversations()

    # Log LLM session presence (helps detect whether startup created a persistent session)
    try:
        sess_ok = (S.llm_session is not None) and (not getattr(S.llm_session, 'closed', False))
        S.logger.info(f"LLM session present at call start: {sess_ok}")
    except Exception:
        S.logger.info("LLM session present at call start: unknown")
    
    history = S.conversation_history[connection_id]
    doc_dicts: List[Dict[str, Any]] = []
    explanation_candidate_doc_dicts: List[Dict[str, Any]] = []
    doc_router_mode = "single_source"
    doc_router_reason = "not_run"
    doc_router_selected_sources: List[str] = []
    focused_context = ""
    trace_extractor_used = False
    generation_prefilter_docs: List[Dict[str, Any]] = []
    
    # Skip RAG search for greetings only (optimization)
    is_greeting = _is_pure_smalltalk_query(text)
    is_simple_factual_query: bool = False

    if S._is_kb_unanswerable_detail_query(text):
        refusal = _customer_service_no_match_response(text)
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
            response_length=len(refusal),
        )
        return (refusal, [])

    if is_greeting:
        S.logger.info(f"RAG: Skipping search for greeting: {text}")
        relevant_docs = []
    else:
        S.logger.info(f"RAG: Searching knowledge base for: {text}")
        is_simple_factual_query = _is_simple_factual_text_query(text)
        query_family = _classify_query_family(text)
        query_family_v2 = _classify_query_family_v2(text)
        is_fact_query = query_family_v2 in {"fact_entity", "attribute_lookup"}
        is_definition_fast = (not is_fact_query) and _is_safe_definition_fast_path_query(text)
        is_controlled_def_entity = _is_controlled_definition_entity_query(text)
        if _is_force_overview_paragraph_query(text):
            top_k_req = 2
        elif is_fact_query:
            top_k_req = FACT_MAX_TOP_K
        elif is_controlled_def_entity or query_family_v2 == "definition_comparison":
            top_k_req = 12
        elif is_generation_query_requested or is_bridge_query_requested or format_intent_early != "default":
            top_k_req = 12
        elif query_family == "list_structure":
            top_k_req = 10
        elif query_family == "overview_chapter_compare":
            top_k_req = 2
        else:
            top_k_req = 6
        S.logger.info("[TOPK TRACE] requested=%s actual=%s function=call_llm_with_rag", top_k_req, top_k_req)
        retrieval_query = _overview_seed_query() if query_family_v2 == "document_summary" else text
        if is_definition_fast:
            relevant_docs = await _search_fast_definition_minimal_async(text)
        else:
            relevant_docs = await _search_fast_minimal_async(retrieval_query, top_k=top_k_req)
        if query_family_v2 == "document_summary":
            relevant_docs = _rerank_document_summary_for_coverage(relevant_docs or [])
        S.logger.info("[DOC COUNT TRACE] stage=call_llm_with_rag.initial_retrieval count=%s", len(relevant_docs or []))

        # One-shot typo-retry when lexical grounding is missing or retrieval evidence is weak.
        try:
            metrics = _retrieval_evidence_metrics(text, relevant_docs or []) if relevant_docs else {
                "coverage": 0.0,
                "focus_ratio": 0.0,
                "max_similarity": 0.0,
                "query_tokens": float(len(_query_tokens_for_evidence(text))),
            }
            no_matched_tokens = bool(metrics.get("query_tokens", 0.0) > 0 and metrics.get("coverage", 0.0) <= 0.0)
            weak_scores = (not relevant_docs) or _is_weak_retrieval_evidence(text, query_family, relevant_docs or [])
            corrected_query = _spelling_correction_preserving_exact_terms(text, seed_docs=relevant_docs or [])
            has_corrected_variant = bool(corrected_query and corrected_query.strip().lower() != (text or "").strip().lower())
            force_overview_retry = bool(has_corrected_variant and _is_force_overview_paragraph_query(corrected_query))
            if (no_matched_tokens or weak_scores or force_overview_retry) and has_corrected_variant:
                    corrected_family = _classify_query_family(corrected_query)
                    corrected_family_v2 = _classify_query_family_v2(corrected_query)
                    corrected_is_fact = corrected_family_v2 in {"fact_entity", "attribute_lookup"}
                    corrected_is_def_fast = (not corrected_is_fact) and _is_safe_definition_fast_path_query(corrected_query)
                    corrected_is_controlled_def_entity = _is_controlled_definition_entity_query(corrected_query)
                    if _is_force_overview_paragraph_query(corrected_query):
                        corrected_top_k = 2
                    elif corrected_is_fact:
                        corrected_top_k = FACT_MAX_TOP_K
                    elif corrected_is_controlled_def_entity or corrected_family_v2 == "definition_comparison":
                        corrected_top_k = 12
                    elif S._is_llm_generation_query(original_query_text):
                        corrected_top_k = 12
                    elif corrected_family == "list_structure":
                        corrected_top_k = 10
                    elif corrected_family == "overview_chapter_compare":
                        corrected_top_k = 2
                    else:
                        corrected_top_k = 3

                    if corrected_is_def_fast:
                        retried_docs = await _search_fast_definition_minimal_async(corrected_query)
                    else:
                        retried_docs = await _search_fast_minimal_async(corrected_query, top_k=corrected_top_k)
                    S.logger.info("[DOC COUNT TRACE] stage=call_llm_with_rag.typo_retry_retrieval count=%s", len(retried_docs or []))

                    if retried_docs:
                        relevant_docs = retried_docs
                        query_family = corrected_family
                        text = corrected_query
                        S.logger.info("RAG typo-retry applied | original='%s' corrected='%s'", (original_query_text or "")[:80], corrected_query[:80])
        except Exception:
            S.logger.exception("RAG typo-retry skipped due to internal error")

        if _classify_query_family_v2(text) in {"fact_entity", "attribute_lookup"}:
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
                        S.logger.info("[DOC COUNT TRACE] stage=call_llm_with_rag.fact_rescue_merged count=%s", len(relevant_docs or []))
            except Exception:
                S.logger.exception("FACT rescue retrieval skipped due to internal error")

        if is_generation_query_requested:
            generation_prefilter_docs = [
                d for d in (relevant_docs or [])
                if str((d or {}).get("text") or (d or {}).get("page_content") or (d or {}).get("content") or "").strip()
            ]

    retrieval_ms = (time.perf_counter() - retrieval_t0) * 1000.0

    if (not is_greeting) and relevant_docs and _detect_language(text) == "en" and _is_simple_factual_text_query(text):
        if not _passes_hybrid_relevance_gate(text, relevant_docs):
            max_sim = _max_doc_similarity(relevant_docs)
            # Relaxed: Do not clear relevant_docs to allow LLM to judge fuzzy matches
            pass

    if (not is_greeting) and relevant_docs and not _retrieval_context_is_reliable(text, relevant_docs):
        ql = text.lower()
        keep_for_structure = _query_requires_structure(text)
        keep_for_manifest = ("manifest image" in ql and "scientific image" in ql)
        keep_for_overview = any(k in ql for k in [
            "what is this document about",
            "what does this document talk about",
            "what is this book about",
            "main ideas",
            "topics covered",
            "overview",
            "summary",
        ])
        keep_for_definition = (_classify_query_family(text) in {"definition_entity", "definition_comparison"})
        keep_for_synthesis = bool(
            is_generation_query_requested or is_bridge_query_requested or format_intent_early != "default"
        )
        if keep_for_structure or keep_for_manifest or keep_for_overview or keep_for_definition or keep_for_synthesis:
            S.logger.info("RAG context reliability gate bypassed for targeted query='%s'", text[:80])
        else:
            # Check for name/entity signals — these deserve a chance even if reliability markers are low
            has_names = any(w[0].isupper() and w[0].isalpha() for w in text.split()[1:]) if len(text.split()) > 1 else False
            if has_names:
                S.logger.info("RAG context reliability gate softened for potential named entity query='%s'", text[:80])
            else:
                S.logger.info("RAG context reliability gate rejected retrieved docs for query='%s'", text[:80])
                relevant_docs = []

    if (not is_greeting) and (not relevant_docs):
        rescue_family = _classify_query_family(text)
        if rescue_family in {"list_structure", "overview_chapter_compare", "definition_entity"}:
            S.logger.info("RAG rescue retrieval: broadening search for query='%s'", text[:80])
            rescue_docs = _search_with_query_expansion(
                text,
                top_k=8,
                distance_threshold=max(_distance_threshold_for_query(text), 1.8),
                return_dicts=True,
                enable_rerank=True,
            )
            if (not rescue_docs) and rescue_family == "overview_chapter_compare":
                rescue_docs = await _active_rag_search_async(
                    _overview_seed_query(),
                    top_k=6,
                    distance_threshold=max(_distance_threshold_for_query(text), 1.8),
                    return_dicts=True,
                    enable_rerank=True,
                )
                S.logger.info("[RERANK ACTIVE]")
            if rescue_docs:
                rescue_docs = _rerank_docs_for_query_intent(text, rescue_docs)
                relevant_docs = _retrieve_with_section_bias(text, rescue_docs, top_k=8)
                S.logger.info("[DOC COUNT TRACE] stage=call_llm_with_rag.rescue_retrieval count=%s", len(relevant_docs or []))
                retrieval_ms = (time.perf_counter() - retrieval_t0) * 1000.0

    if (not is_greeting) and (not relevant_docs):
        prefilter_usable_docs = [
            d for d in (generation_prefilter_docs or [])
            if str((d or {}).get("text") or (d or {}).get("page_content") or (d or {}).get("content") or "").strip()
        ]
        S.logger.info(
            "[GENERATION FALLBACK CHECK] query=%s is_generation=%s final_docs_count=%d pre_filter_docs_count=%d",
            (text or "")[:120],
            bool(is_generation_query_requested),
            len(relevant_docs or []),
            len(prefilter_usable_docs),
        )
        if is_generation_query_requested and prefilter_usable_docs:
            S.logger.info(
                "[GENERATION FALLBACK ACTIVATED] reason=final_docs_empty_for_generation using_prefilter_docs=%d",
                len(prefilter_usable_docs),
            )
            relevant_docs = prefilter_usable_docs
        else:
            S.logger.info(
                f"RAG strict guard: no sufficiently relevant docs for query='{text[:80]}' "
                f"(threshold={RAG_STRICT_DISTANCE_THRESHOLD:.2f})"
            )
            no_match_msg = _apply_not_found_ux(text, RAG_NO_MATCH_RESPONSE, [])
            response_time = int((time.time() - start_time) * 1000)
            S._set_last_latency_breakdown(connection_id, retrieval_ms, 0.0, 0.0, 0.0, float(response_time))
            log_usage(
                username=user.get("username", "unknown"),
                user_role=user.get("role", "unknown"),
                query_text=text,
                response_status="success",
                error_message=None,
                response_time_ms=response_time,
                rag_docs_found=0,
                query_length=len(text.strip()),
                response_length=len(no_match_msg),
            )
            return (no_match_msg, [])

    # Build context using TOON format (40-60% token savings)
    context_block = ""
    is_summary_req = 'summar' in text.lower() or 'overview' in text.lower()

    def _is_valid_definition_lock_sentence(sentence: str, query_text: str) -> bool:
        return False  # default stub; real implementation set below inside if relevant_docs

    if relevant_docs:
        early_identity = _extract_strict_same_line_person_identity_from_retrieved_docs(text, relevant_docs)
        if early_identity:
            response_time = int((time.time() - start_time) * 1000)
            log_usage(
                username=user.get("username", "unknown"),
                user_role=user.get("role", "unknown"),
                query_text=text,
                response_status="success",
                error_message=None,
                response_time_ms=response_time,
                rag_docs_found=len(relevant_docs),
                query_length=len(text.strip()),
                response_length=len(early_identity),
            )
            return (early_identity, relevant_docs)

        extraction_t0 = time.perf_counter()
        # Prepare RAG docs: clean OCR artifacts, normalize named-entities
        # Skip empty chunks, deduplicate, and preserve score for ordering.
        def _prepare_rag_doc_dicts(retrieved_docs, query_text):
            """
            Prepare and deduplicate retrieved docs.

            Rules enforced here:
            - Preserve reranker order exactly (no reordering).
            - Keep doc[0] from reranker as doc[0] for LLM context.
            - Deduplicate only by content fingerprint while preserving first occurrence.
            - Log the prepared docs count and a preview of the first doc.
            """
            if not retrieved_docs:
                return []

            seen = set()
            out = []

            def _build_content(doc):
                # Prefer explicit page_content first (most reliable), then text/content.
                raw_page = (
                    doc.get("page_content")
                    or doc.get("text")
                    or doc.get("content")
                    or doc.get("raw_text")
                    or ""
                )

                # basic cleaning but preserve original when over-cleaned
                cleaned = _clean_ocr_artifacts(raw_page)
                if not cleaned or not cleaned.strip():
                    cleaned = raw_page or ""

                normalized = _normalize_context_entities(query_text, cleaned)
                final = normalized or cleaned or ""
                if not isinstance(final, str):
                    final = str(final)
                return raw_page, final

            # Process docs in original reranker order and preserve doc[0]
            for idx, doc in enumerate(retrieved_docs):
                raw_text, final = _build_content(doc)

                # fingerprint and dedupe (empty fingerprint allowed once)
                fp = (final.strip() or "")[:400]
                if fp in seen:
                    continue
                seen.add(fp)

                meta = dict(doc.get("metadata") or {})
                for score_key in ("final_score", "score", "similarity"):
                    if score_key in doc:
                        try:
                            meta["_score"] = float(doc.get(score_key) or 0.0)
                        except Exception:
                            meta["_score"] = 0.0
                        break

                out.append({
                    "page_content": final,
                    "metadata": meta,
                    "score": float(meta.get("_score", 0.0) or 0.0),
                })

            # Fail-safe: if filtering removed everything (shouldn't happen because top is forced),
            # fall back to returning the original retrieved_docs without filtering.
            if not out:
                fallback = []
                for doc in retrieved_docs:
                    raw_text = (
                        doc.get("page_content")
                        or doc.get("text")
                        or doc.get("content")
                        or doc.get("raw_text")
                        or ""
                    )
                    meta = dict(doc.get("metadata") or {})
                    for score_key in ("final_score", "score", "similarity"):
                        if score_key in doc:
                            try:
                                meta["_score"] = float(doc.get(score_key) or 0.0)
                            except Exception:
                                meta["_score"] = 0.0
                            break
                    fallback.append({
                        "page_content": raw_text or "(no content)",
                        "metadata": meta,
                        "score": float(meta.get("_score", 0.0) or 0.0),
                    })
                out = fallback

            # Debug logging: number of prepared docs and preview of first doc
            try:
                count = len(out)
                preview = (out[0].get("page_content", "") or "")[:200]
                S.logger.info(f"RAG PREPARED DOCS COUNT: {count}")
                S.logger.info(f"RAG PREPARED doc[0] preview: {preview}")
            except Exception:
                S.logger.exception("RAG PREPARE: error while logging prepared docs")

            if out:
                try:
                    assert out[0].get('page_content'), "doc_dicts[0] lost content before TOON"
                except AssertionError:
                    raise

            return out

        S.logger.info("[DOC COUNT TRACE] stage=call_llm_with_rag.before_prepare_rag_doc_dicts count=%s", len(relevant_docs or []))
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
            S.logger.exception("RAG PRE-CONTEXT logging failed")
        doc_dicts = _prepare_rag_doc_dicts_shared(relevant_docs, text)
        if _classify_query_family_v2(text) == "document_summary":
            doc_dicts = _select_document_summary_coverage_docs(doc_dicts, max_docs=min(8, len(doc_dicts or []) or 8))
        S.logger.info("[DOC COUNT TRACE] stage=call_llm_with_rag.after_prepare_rag_doc_dicts count=%s", len(doc_dicts or []))

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
            and (not is_generation_query_requested)
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
        original_definition_docs: list[dict] = []
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

            # MP-C12 — Indirect-evidence promotion. The downstream consumer at the
            # `definition_entity` branch checks for a chunk flagged with
            # `_indirect_definition_mode=True` and uses its `_indirect_evidence`
            # sentences to compose a grounded indirect-style answer (e.g. for
            # entities like "bureaucracy" where the document only contains
            # narrative/criticism prose, not a clean "X is ..." sentence).
            # Without this promotion, the flag is never set and the indirect
            # path is dead code. Generic logic — no domain words.
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

            doc_dicts = _dedup_docs_exact_text(doc_dicts)
            doc_dicts = sorted(doc_dicts, key=lambda x: float((x or {}).get("score", 0.0) or 0.0), reverse=True)
            def_pool_keep = max(3, min(5, len(doc_dicts)))
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
                S.logger.exception("DEF POOL CHUNKS logging failed")

            S.logger.info(
                "[ENTITY DEF FILTER] entity=%s kept=%d total=%d",
                query_entity,
                len(entity_definition_docs),
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
        if needs_early_section_rerank and doc_dicts:
            pool_before = len(doc_dicts)
            rerank_top_k = min(max(6, pool_before), 12)
            doc_dicts = _rerank_docs_for_query_intent(text, doc_dicts)
            doc_dicts = _retrieve_with_section_bias(text, doc_dicts, top_k=rerank_top_k)
            S.logger.info(
                "[SECTION RERANK DEBUG] stage=early_pre_shortlist family_v2=%s family=%s before=%d after=%d top_k=%d",
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
        doc_dicts = list(doc_router_decision.get("docs") or doc_dicts)
        is_fact_query = _classify_query_family_v2(text) == "fact_entity"
        if is_fact_query and doc_dicts and not S._skip_deterministic_rag_shortcuts(text, doc_router_mode):
            doc_dicts = _select_fact_anchor_docs(
                text,
                doc_dicts,
                top_k=min(5, len(doc_dicts)),
                scan_limit=min(20, len(doc_dicts)),
            )
        keep_n = 5 if (is_definition_query or _is_compare_query(text) or is_fact_query or is_generation_query_requested or needs_early_section_rerank) else 3
        if doc_router_mode == "multi_source_synthesis":
            keep_n = max(keep_n, min(8, len(doc_dicts or [])))
        if family_legacy_current == "list_structure" or family_v2_current == "list_entity":
            keep_n = max(keep_n, 8)
        if family_legacy_current == "list_structure":
            S.logger.info("[LIST RECALL DEBUG] stage=pre_shortlist family=%s pool=%d keep_n=%d", family_legacy_current, len(doc_dicts or []), keep_n)
        doc_dicts = doc_dicts[:keep_n]
        if is_generation_query_requested and not doc_dicts:
            prefilter_doc_dicts = _prepare_rag_doc_dicts_shared(generation_prefilter_docs, original_query_text)
            prefilter_doc_dicts = [
                d for d in (prefilter_doc_dicts or [])
                if str((d or {}).get("page_content") or (d or {}).get("text") or (d or {}).get("content") or "").strip()
            ]
            S.logger.info(
                "[GENERATION FALLBACK CHECK] query=%s is_generation=%s final_docs_count=%d pre_filter_docs_count=%d",
                (original_query_text or "")[:120],
                True,
                len(doc_dicts or []),
                len(prefilter_doc_dicts),
            )
            if prefilter_doc_dicts:
                S.logger.info(
                    "[GENERATION FALLBACK ACTIVATED] reason=final_docs_empty_for_generation using_prefilter_docs=%d",
                    len(prefilter_doc_dicts),
                )
                doc_dicts = prefilter_doc_dicts[:keep_n]
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
            S.logger.exception("RAG FINAL SELECTED logging failed")
        _log_selected_doc_markers(doc_dicts)

        generation_query_requested = S._is_llm_generation_query(original_query_text)
        generation_source_query = original_query_text if generation_query_requested else text
        if S._use_early_generation_shortcut(original_query_text, doc_router_mode):
            S.logger.info("[LLM GENERATION MODE]")
            generation_docs = S._select_generation_context_docs(generation_source_query, doc_dicts, max_docs=5)
            if len(generation_docs or []) < 1 and doc_dicts:
                generation_docs = list(doc_dicts)[:5]
            generation_context = _build_generation_context(generation_source_query, generation_docs, max_chars=3600)
            generation_llm_called = False

            context_sufficient = _has_sufficient_context(
                generation_source_query,
                generation_context,
                relevant_chunks=len(generation_docs or []),
            )
            S.logger.info(
                "[LLM GENERATION CONTEXT CHECK] chunks=%s token_hits=%s sufficient=%s",
                len(generation_docs or []),
                count_token_matches(extract_keywords(generation_source_query), generation_context),
                context_sufficient,
            )
            if not context_sufficient:
                composed = _compose_grounded_generation_answer(generation_source_query, generation_context)
                if composed and _is_answer_grounded_in_docs(composed, doc_dicts or [], query_text=text):
                    answer = composed
                else:
                    answer = _apply_not_found_ux(text, RAG_NO_MATCH_RESPONSE, doc_dicts)
                S.logger.info(
                    "[GENERATION FALLBACK RESULT] llm_called=%s context_chars=%d final_answer_preview=%s",
                    bool(generation_llm_called),
                    len(generation_context or ""),
                    str(answer or "")[:220],
                )
                extraction_ms = (time.perf_counter() - extraction_t0) * 1000.0
                response_time = int((time.time() - start_time) * 1000)
                S.logger.info(
                    "LATENCY_BREAKDOWN query='%s' retrieval_ms=%.0f extraction_ms=%.0f validation_ms=0 llm_ms=0 total_ms=%d",
                    (text or "")[:80],
                    retrieval_ms,
                    extraction_ms,
                    response_time,
                )
                S._set_last_latency_breakdown(connection_id, retrieval_ms, extraction_ms, 0.0, 0.0, float(response_time))
                log_usage(
                    username=user.get("username", "unknown"),
                    user_role=user.get("role", "unknown"),
                    query_text=text,
                    response_status="success",
                    error_message=None,
                    response_time_ms=response_time,
                    rag_docs_found=len(doc_dicts),
                    query_length=len(text.strip()),
                    response_length=len(answer),
                )
                return (answer, doc_dicts)

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
                "* Summaries should be 2–5 sentences\n\n"
                "IMPORTANT:\n"
                "* Do NOT invent information or use outside knowledge\n"
                "* If the answer cannot be derived from context, say warmly that the detail "
                "is not in the uploaded help materials\n"
            )
            generation_query = S._rewrite_generation_query_for_grounded_llm(generation_source_query)
            llm_t0_generation = time.perf_counter()
            generation_llm_called = True
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
            llm_ms = (time.perf_counter() - llm_t0_generation) * 1000.0
            answer = str(generation_answer or "").strip() or RAG_NO_MATCH_RESPONSE
            if answer.lower() == RAG_NO_MATCH_RESPONSE.lower():
                composed = _compose_grounded_generation_answer(generation_source_query, generation_context)
                if composed and _is_answer_grounded_in_docs(composed, doc_dicts or [], query_text=text):
                    answer = composed
                else:
                    answer = _apply_not_found_ux(text, RAG_NO_MATCH_RESPONSE, doc_dicts)
            elif not _is_answer_grounded_in_docs(answer, doc_dicts or [], query_text=text):
                docs_count = len(doc_dicts or [])
                fallback_docs_count = len(generation_docs or [])
                if docs_count == 0 and fallback_docs_count == 0:
                    S.logger.info("[LLM GENERATION GROUNDED CHECK] grounded=false action=not_found")
                    S.logger.info("[POST-GUARD CHECK] docs_count=%s grounded=%s decision=%s", docs_count, False, "not_found_no_docs")
                    answer = _apply_not_found_ux(text, RAG_NO_MATCH_RESPONSE, doc_dicts)
                else:
                    S.logger.info("[POST-GUARD CHECK] docs_count=%s grounded=%s decision=%s", docs_count, False, "allow_generation_response")
            else:
                S.logger.info("[LLM GENERATION GROUNDED CHECK] grounded=true action=accept")
                S.logger.info("[POST-GUARD CHECK] docs_count=%s grounded=%s decision=%s", len(doc_dicts or []), True, "accept_grounded")
            answer = S._ensure_bridge_source_signals(
                text,
                S._format_generation_answer_by_query(text, _cleanup_final_answer_text(answer)),
            )
            S.logger.info(
                "[GENERATION FALLBACK RESULT] llm_called=%s context_chars=%d final_answer_preview=%s",
                bool(generation_llm_called),
                len(generation_context or ""),
                str(answer or "")[:220],
            )

            extraction_ms = (time.perf_counter() - extraction_t0) * 1000.0
            response_time = int((time.time() - start_time) * 1000)
            S.logger.info(
                "LATENCY_BREAKDOWN query='%s' retrieval_ms=%.0f extraction_ms=%.0f validation_ms=0 llm_ms=%.0f total_ms=%d",
                (text or "")[:80],
                retrieval_ms,
                extraction_ms,
                llm_ms,
                response_time,
            )
            S._set_last_latency_breakdown(connection_id, retrieval_ms, extraction_ms, 0.0, llm_ms, float(response_time))
            log_usage(
                username=user.get("username", "unknown"),
                user_role=user.get("role", "unknown"),
                query_text=text,
                response_status="success",
                error_message=None,
                response_time_ms=response_time,
                rag_docs_found=len(doc_dicts),
                query_length=len(text.strip()),
                response_length=len(answer),
            )
            return (answer, doc_dicts)

        # Fast and simple early selector: avoid heavy downstream processing.
        if _is_metric_fact_query(text) and doc_dicts and not S._skip_deterministic_rag_shortcuts(text, doc_router_mode):
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
                answer = _apply_not_found_ux(text, metric_answer, doc_dicts)
                extraction_ms = (time.perf_counter() - extraction_t0) * 1000.0
                response_time = int((time.time() - start_time) * 1000)
                S._set_last_latency_breakdown(connection_id, retrieval_ms, extraction_ms, 0.0, 0.0, float(response_time))
                log_usage(
                    username=user.get("username", "unknown"),
                    user_role=user.get("role", "unknown"),
                    query_text=text,
                    response_status="success",
                    error_message=None,
                    response_time_ms=response_time,
                    rag_docs_found=len(doc_dicts),
                    query_length=len(text.strip()),
                    response_length=len(answer),
                )
                return (answer, doc_dicts)

        pre_simple = _shared_rag_final_answer_decision(text, doc_dicts, llm_text=None)
        pre_simple = _enforce_runtime_answer_acceptance(text, pre_simple, doc_dicts)
        if not pre_simple.get("used_llm", True) and not S._skip_deterministic_rag_shortcuts(text, doc_router_mode):
            answer = _apply_not_found_ux(text, str(pre_simple.get("answer") or RAG_NO_MATCH_RESPONSE), doc_dicts)
            pre_answer_type = str(pre_simple.get("answer_type") or "")
            pre_family_v2 = _classify_query_family_v2(text)
            pre_family_legacy = _classify_query_family(text)
            pre_list_mode = bool(
                pre_family_v2 == "list_entity"
                or pre_family_legacy == "list_structure"
                or _is_targeted_list_question(text)
                or pre_answer_type.startswith("list_")
            )
            if pre_list_mode and str(answer or "").strip() and str(answer).strip() != RAG_NO_MATCH_RESPONSE:
                strict_pre_fast = bool(pre_answer_type in {"list_deterministic_context", "list_fast_simple", "list_extractor"})
                pre_ok, pre_reason, pre_shaped = _assess_list_coherence(text, _preclean_list_answer_for_assessment(answer), strict_fast=strict_pre_fast, local_support=_collect_local_window_support(doc_dicts or []))
                S.logger.info("[LIST COHERENCE DEBUG] accepted=%s reason=%s", bool(pre_ok), pre_reason)
                if strict_pre_fast:
                    S.logger.info("[FAST LIST GUARD] accepted=%s reason=%s", bool(pre_ok), pre_reason)
                if not pre_ok:
                    answer = RAG_NO_MATCH_RESPONSE
                elif pre_shaped:
                    answer = pre_shaped
                answer = _apply_not_found_ux(text, answer, doc_dicts)
            _log_answer_mode_markers(text, doc_dicts, answer, source_mode="extractor")
            if _classify_query_family(text) == "definition_entity" and not _passes_strict_definition_relevance_guard(text, answer):
                fallback_answer = _definition_explanation_fallback(text, doc_dicts, _extract_entity_from_definition_query(text)[1])
                if fallback_answer:
                    answer = fallback_answer
            if _is_explicit_oos_query(text) and re.match(r"^\s*who\s+(?:is|was)\b", text or "", flags=re.IGNORECASE):
                answer = _not_found_response(text, "out_of_scope")
            extraction_ms = (time.perf_counter() - extraction_t0) * 1000.0
            response_time = int((time.time() - start_time) * 1000)
            S.logger.info(
                "LATENCY_BREAKDOWN query='%s' retrieval_ms=%.0f extraction_ms=%.0f validation_ms=0 llm_ms=0 total_ms=%d",
                (text or "")[:80],
                retrieval_ms,
                extraction_ms,
                response_time,
            )
            S._set_last_latency_breakdown(connection_id, retrieval_ms, extraction_ms, 0.0, 0.0, float(response_time))
            log_usage(
                username=user.get("username", "unknown"),
                user_role=user.get("role", "unknown"),
                query_text=text,
                response_status="success",
                error_message=None,
                response_time_ms=response_time,
                rag_docs_found=len(doc_dicts),
                query_length=len(text.strip()),
                response_length=len(answer),
            )
            return (answer, doc_dicts)

        query_family = _classify_query_family(text)
        for d in doc_dicts:
            if query_family == "list_structure":
                continue
            focused = S._focus_doc_to_query_window(text, d.get("page_content", ""))
            d["page_content"] = focused

        if _is_force_overview_paragraph_query(text):
            compact_docs: List[Dict[str, Any]] = []
            total_chars = 0
            for d in doc_dicts[:2]:
                src = str(d.get("page_content") or "")
                sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", src) if s.strip()]
                kept: List[str] = []
                for s in sents:
                    if re.match(r"^\s*(?:[-•*]|\d+[.)])\s+", s):
                        continue
                    if re.search(r"^\s*(?:chapter\s+\d+|unit\s+\d+|contents?|table of contents|summary|introduction)\s*[:\-–—]?\s*$", s, flags=re.IGNORECASE):
                        continue
                    if not re.search(r"[.!?]$", s):
                        continue
                    if len(re.findall(r"[a-z0-9]+", s.lower())) < 8:
                        continue
                    kept.append(s)
                    if len(kept) >= 3:
                        break
                compact = " ".join(kept).strip()
                if not compact:
                    continue
                remain = 1500 - total_chars
                if remain <= 0:
                    break
                if len(compact) > remain:
                    compact = compact[:remain].rstrip(" ,;:-") + "."
                d2 = dict(d)
                d2["page_content"] = compact
                compact_docs.append(d2)
                total_chars += len(compact)
                if total_chars >= 1500:
                    break
            if compact_docs:
                doc_dicts = compact_docs

        focused_context = "\n\n".join(d.get("page_content", "") for d in doc_dicts)
        if _is_force_overview_paragraph_query(text) and len(focused_context) > 1500:
            focused_context = focused_context[:1500].rstrip(" ,;:-") + "."

        if _classify_query_family(text) == "list_structure":
            structured_answer = _extract_list_from_context(text, focused_context, max_candidate_blocks=2)
            if structured_answer:
                fast_ok, fast_reason, fast_shaped = _assess_list_coherence(text, _preclean_list_answer_for_assessment(structured_answer), strict_fast=True, local_support=_collect_local_window_support(doc_dicts or []))
                S.logger.info("[LIST COHERENCE DEBUG] accepted=%s reason=%s", bool(fast_ok), fast_reason)
                S.logger.info("[FAST LIST GUARD] accepted=%s reason=%s", bool(fast_ok), fast_reason)
                if not fast_ok:
                    structured_answer = RAG_NO_MATCH_RESPONSE
                elif fast_shaped:
                    structured_answer = fast_shaped
                structured_answer = _apply_not_found_ux(text, structured_answer, doc_dicts)
                extraction_ms = (time.perf_counter() - extraction_t0) * 1000.0
                response_time = int((time.time() - start_time) * 1000)
                S.logger.info(
                    "LATENCY_BREAKDOWN query='%s' retrieval_ms=%.0f extraction_ms=%.0f validation_ms=0 llm_ms=0 total_ms=%d",
                    (text or "")[:80],
                    retrieval_ms,
                    extraction_ms,
                    response_time,
                )
                S._set_last_latency_breakdown(connection_id, retrieval_ms, extraction_ms, 0.0, 0.0, float(response_time))
                log_usage(
                    username=user.get("username", "unknown"),
                    user_role=user.get("role", "unknown"),
                    query_text=text,
                    response_status="success",
                    error_message=None,
                    response_time_ms=response_time,
                    rag_docs_found=len(doc_dicts),
                    query_length=len(text.strip()),
                    response_length=len(structured_answer),
                )
                return (structured_answer, doc_dicts)

        def _is_strict_definition_candidate(sentence: str, query_text: str) -> bool:
            s = str(sentence or "").strip()
            if not s:
                return False
            low = f" {s.lower()} "
            low_plain = s.lower()
            allow_introduced = bool(re.match(r"^\s*who\s+introduced\b", (query_text or "").strip().lower()))
            if not re.search(r"\b(is|was|refers to|defined as|known as|is the|was the)\b", low):
                if not (allow_introduced and re.search(r"\bintroduced\b", low)):
                    return False
            if any(p in low_plain for p in ("he thought", "it can be said", "in this way", "before we can")):
                return False
            if re.match(r"^\s*(and|but|or|so|because|therefore|thus|also|then|while|whereas)\b", low_plain):
                return False
            if re.match(r"^\s*(?:[-•*]|\d+[.)])\s+", s):
                return False
            if "|" in s:
                return False
            if len(re.findall(r"[A-Za-z][A-Za-z\-']*", s)) < 6:
                return False
            if len(re.findall(r"[A-Za-z][A-Za-z\-']*", s)) > 40:
                return False
            if re.search(r"\b(?:isbn|https?://|www\.|kdpublications|unit\s*\d+|chapter\s*\d+|table\s+of\s+contents|contents?)\b", low_plain):
                return False
            has_entity, entity = _extract_entity_from_definition_query(query_text)
            if has_entity:
                entity_norm = re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", (entity or "").lower())).strip()
                low_norm = re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", low_plain)).strip()
                concept_q = (query_text or "").strip().lower().startswith("what is") or (query_text or "").strip().lower().startswith("define")
                if concept_q:
                    entity_tokens = [
                        t for t in re.findall(r"[a-z0-9]{2,}", (entity or "").lower())
                        if t not in {"the", "a", "an", "of", "and", "in", "to"}
                    ]
                    if _looks_table_or_heading_like_chunk(s):
                        return False
                    if _is_feature_only_definition_sentence(s):
                        return False
                    if _s_definition_sentence(s, entity_norm, entity_tokens) < 0:
                        return False
                    if re.match(r"^\s*(?:\d+[.)]?\s+)?[A-Z][A-Za-z\-]+(?:\s+[A-Za-z][A-Za-z\-]+){0,4}\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3}\s*$", s.strip()):
                        return False
                    if re.search(r"\b(?:\d{4}|\d{3,4}s)\b", s):
                        return False
                    if re.search(r"\b(?:translated|book|publication|edition)\b", low_plain):
                        return False
                    if re.search(r"\b(?:he|she|his|her|born|birth|died|author|authored|wrote|writer|biography)\b", low_plain):
                        return False
                    if re.search(r"\b(?:introduced\s+by|he\s+is\s+known\s+as|he\s+was\s+known\s+as|is\s+associated\s+with)\b", low_plain):
                        return False
                    if re.match(r"^\s*[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3}\s+(?:is|was)\b", s):
                        if not (entity_norm and re.search(rf"\b{re.escape(entity_norm)}\b", low_norm)):
                            return False
                    cap_words = re.findall(r"\b[A-Z][a-z]{2,}\b", s)
                    if len(cap_words) >= 2 and not re.search(r"\b(?:is|refers to|defined as)\b", low_plain):
                        return False
                    if entity_norm and re.search(rf"\b{re.escape(entity_norm)}\b(?:[\s\"'`”’]+)(?:is|refers\s+to|can\s+be\s+defined\s+as)\b", low_norm):
                        return True

                entity_tokens = [
                    t for t in re.findall(r"[a-z0-9]{3,}", (entity or "").lower())
                    if t not in {"what", "who", "is", "was", "the", "and", "for", "with", "from", "about", "define"}
                ]
                if entity_tokens:
                    hits = sum(1 for t in entity_tokens if re.search(rf"\b{re.escape(t)}\b", low))
                    need = max(1, min(2, len(entity_tokens)))
                    if hits < need:
                        return False
            return True

        def _extract_strict_definition_from_docs(query_text: str, docs: list[dict]) -> str | None:
            has_entity, entity = _extract_entity_from_definition_query(query_text)
            entity_l = (entity or "").strip().lower()
            entity_norm = re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", entity_l)).strip()
            concept_q = (query_text or "").strip().lower().startswith("what is") or (query_text or "").strip().lower().startswith("define")
            entity_tokens = [
                t for t in re.findall(r"[a-z0-9]{2,}", entity_l)
                if t not in {"the", "a", "an", "of", "and", "in", "to"}
            ]
            q_low = (query_text or "").strip().lower()
            q_tokens = [
                t for t in re.findall(r"[a-z0-9]{3,}", q_low)
                if t not in {"what", "who", "is", "was", "the", "a", "an", "of", "and", "in", "to", "define", "about"}
            ]
            weak_phrases = ("he thought", "it can be said", "in this way", "before we can")
            continuation_starts = re.compile(r"^\s*(and|but|or|so|because|therefore|thus|also|then|while|whereas)\b", flags=re.IGNORECASE)
            person_indicators = ("born", "known as", "considered", "introduced", "engineer", "theorist", "manager")
            is_who_query = q_low.startswith("who is") or q_low.startswith("who was")
            early_exit_threshold = 8.0

            best: tuple[float, str] | None = None
            for d in docs[:3]:
                src = str(d.get("page_content") or "")
                if concept_q and entity_norm:
                    src_compact = re.sub(r"\s+", " ", src).strip()
                    src_compact_low = src_compact.lower()
                    pat = re.compile(
                        rf"\b{re.escape(entity_norm)}\b(?:[\s\"'`”’]+)(?:is|refers\s+to|can\s+be\s+defined\s+as)\b[^.?!\n]{{0,240}}[.?!]",
                        flags=re.IGNORECASE,
                    )
                    m = pat.search(src_compact_low)
                    if m:
                        direct = src_compact[m.start():m.end()].strip()
                        if not re.search(r"\b(?:\d{4}|\d{3,4}s|translated|book|publication|edition|isbn|https?://|www\.|kdpublications)\b", direct, flags=re.IGNORECASE):
                            return direct.rstrip(" .") + "."

                parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+|\n+", src) if p.strip()]
                for sent in parts[:5]:
                    if concept_q:
                        concept_quality_score = _s_definition_sentence(sent, entity_norm, entity_tokens)
                        if concept_quality_score <= 0:
                            continue
                        sent_low_norm = re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", sent.lower())).strip()
                        if re.search(r"\b(?:\d{4}|\d{3,4}s)\b", sent):
                            continue
                        if re.search(r"\b(?:translated|book|publication|edition)\b", sent, flags=re.IGNORECASE):
                            continue
                        if re.search(r"\b(?:he|she|his|her|born|birth|died|author|authored|wrote|writer|biography)\b", sent, flags=re.IGNORECASE):
                            continue
                        if entity_norm and re.search(rf"\b{re.escape(entity_norm)}\b(?:[\s\"'`”’]+)(?:is|refers\s+to|can\s+be\s+defined\s+as)\b", sent_low_norm):
                            return sent.strip()

                    if not _is_strict_definition_candidate(sent, query_text):
                        continue

                    low = sent.lower()
                    wc = len(re.findall(r"[a-zA-Z][a-zA-Z\-']*", sent))
                    if wc < 6 or wc > 40:
                        continue
                    if re.match(r"^\s*(?:[-•*]|\d+[.)])\s+", sent):
                        continue
                    if re.match(r"^[A-Z][A-Za-z0-9\s\-,:]{2,100}$", sent) and not re.search(r"[.!?]$", sent):
                        continue

                    score = 0.0
                    has_definition_verb = bool(re.search(r"\b(is|was|defined as|refers to|known as|is the|was the)\b", low))
                    if has_definition_verb:
                        score += 6.0

                    if concept_q:
                        score += float(_s_definition_sentence(sent, entity_norm, entity_tokens))

                    full_concept_hit = False
                    if entity_l and re.search(rf"\b{re.escape(entity_l)}\b", low):
                        full_concept_hit = True
                    token_hits = sum(1 for t in entity_tokens if re.search(rf"\b{re.escape(t)}\b", low))
                    if len(entity_tokens) >= 2 and token_hits >= min(2, len(entity_tokens)):
                        full_concept_hit = True
                    q_hits = sum(1 for t in q_tokens if re.search(rf"\b{re.escape(t)}\b", low))
                    if q_hits >= 2:
                        full_concept_hit = True
                    if full_concept_hit:
                        score += 6.0

                    if q_hits > 0:
                        score += 3.0
                    if q_hits >= 1:
                        score += 1.5
                    if is_who_query and any(ind in low for ind in person_indicators):
                        score += 3.0

                    first_alpha = next((ch for ch in sent if ch.isalpha()), "")
                    if first_alpha and first_alpha.islower():
                        score -= 5.0
                    if continuation_starts.match(sent):
                        score -= 5.0
                    if any(p in low for p in weak_phrases):
                        score -= 5.0

                    # MP-C2: generic structural definition-shape signals
                    score += _definition_structural_signal_delta(sent, entity_l)

                    if score >= early_exit_threshold:
                        return sent.strip()
                    if best is None or score > best[0]:
                        best = (score, sent)

            if not best:
                return None
            return best[1].strip()

        # Early exit for strict safe definition queries when a validated sentence is found.
        q_intent = detect_query_intent(text)
        fast_path_allowed = _is_safe_definition_fast_path_query(text)
        if q_intent == "definition" and fast_path_allowed:
            early_def = _extract_strict_definition_from_docs(text, doc_dicts)
            if not early_def:
                early_def = _extract_definition_sentence(focused_context, text)
            if early_def and _is_strict_definition_candidate(early_def, text) and _passes_fast_path_definition_validation(text, early_def):
                answer = str(early_def).strip()
                cleaned_early = _context_grounded_definition_override(text, doc_dicts, answer)
                if cleaned_early:
                    answer = cleaned_early
                answer = _force_clean_definition_sentence(text, answer, doc_dicts)
                answer = _apply_not_found_ux(text, answer, doc_dicts)
                if _is_explicit_oos_query(text):
                    answer = _not_found_response(text, "out_of_scope")
                extraction_ms = (time.perf_counter() - extraction_t0) * 1000.0
                response_time = int((time.time() - start_time) * 1000)
                S.logger.info("[DEFINITION EARLY EXIT] query='%s'", (text or "")[:120])
                S.logger.info(
                    "LATENCY_BREAKDOWN query='%s' retrieval_ms=%.0f extraction_ms=%.0f validation_ms=0 llm_ms=0 total_ms=%d",
                    (text or "")[:80],
                    retrieval_ms,
                    extraction_ms,
                    response_time,
                )
                S._set_last_latency_breakdown(connection_id, retrieval_ms, extraction_ms, 0.0, 0.0, float(response_time))
                if q_intent == "definition" or _is_simple_factual_text_query(text):
                    S._simple_rag_cache_put(text, answer)
                log_usage(
                    username=user.get("username", "unknown"),
                    user_role=user.get("role", "unknown"),
                    query_text=text,
                    response_status="success",
                    error_message=None,
                    response_time_ms=response_time,
                    rag_docs_found=len(doc_dicts),
                    query_length=len(text.strip()),
                    response_length=len(answer),
                )
                return (answer, doc_dicts)
            elif early_def:
                S.logger.info("[DEFINITION EARLY EXIT] rejected by fast-path validation guard; falling back to normal pipeline")

        def _is_valid_definition_lock_sentence(sentence: str, query_text: str) -> bool:
            s = str(sentence or "").strip()
            if not s:
                return False

            first_alpha = next((ch for ch in s if ch.isalpha()), "")
            if not first_alpha or first_alpha.islower():
                return False

            word_count = len(re.findall(r"[A-Za-z][A-Za-z\-']*", s))
            if word_count < 10:
                return False

            low = f" {s.lower()} "
            if re.match(r"^\s*(?:[-•*]|\d+[.)])\s+", s):
                return False
            if re.match(r"^\s*(and|but|or|so|because|therefore|thus|also|then|while|whereas)\b", s, flags=re.IGNORECASE):
                return False

            has_entity, entity = _extract_entity_from_definition_query(query_text)
            if not has_entity:
                return False

            entity_l = str(entity or "").strip().lower()
            q_low = str(query_text or "").strip().lower()
            is_concept_q = q_low.startswith("what is") or q_low.startswith("define")

            compact_sentence = re.sub(r"[^a-z0-9]+", "", low)
            entity_compact = re.sub(r"[^a-z0-9]+", "", entity_l)
            full_entity_hit = bool(entity_l and re.search(rf"\b{re.escape(entity_l)}\b", low))
            compact_entity_hit = bool(entity_compact and entity_compact in compact_sentence)
            phrase_hit = full_entity_hit or compact_entity_hit
            table_like = _looks_table_or_heading_like_chunk(s)

            parts = [
                p for p in re.findall(r"[a-z0-9]{2,}", entity_l)
                if p not in {"the", "a", "an", "of", "and", "in", "to"}
            ]
            token_hits = sum(1 for p in parts if re.search(rf"\b{re.escape(p)}\b", low))

            if is_concept_q:
                has_concept_verb = bool(re.search(r"\b(is|refers to|defined as|known as)\b", low))
                has_relaxed_concept_verb = bool(re.search(r"\b(is|was|refers to|defined as|known as|focuses on|emphasizes|concerned with|deals with|aims at)\b", low))
                if not has_relaxed_concept_verb:
                    return False

                min_hits = 2 if len(parts) >= 2 else 1
                if table_like and not (phrase_hit or token_hits >= min_hits):
                    return False

                if re.search(r"\b(he|she|his|her|born|worked as|engineer|biography)\b", low):
                    return False

                if re.search(r"\b(you can also call it|also called|also known as)\b", low):
                    return False

                # DISABLED_CHEATING_LOGIC: Domain-specific management rejection rule.
                # if (" management " in low) and (not phrase_hit):
                #     return False

                if phrase_hit and has_concept_verb:
                    return True
                if token_hits < min_hits:
                    return False

                # DISABLED_CHEATING_LOGIC: Domain-specific management token threshold.
                # if (" management " in low) and token_hits < 2:
                #     return False
                return True

            if (" is " in low) or (" was " in low):
                return True

            if entity_l and entity_l in low:
                return True
            if len(parts) >= 2 and all(p in low for p in parts):
                return True
            return False

        pre_decision = _shared_rag_final_answer_decision(text, doc_dicts)
        pre_decision = _enforce_runtime_answer_acceptance(text, pre_decision, doc_dicts)
        S.logger.info("[TRACE] intent=%s", pre_decision.get("intent"))
        S.logger.info("[TRACE] extractor_items_count=%s", pre_decision.get("extractor_items_count", 0))

        if not pre_decision.get("used_llm", True) and not S._skip_deterministic_rag_shortcuts(text, doc_router_mode):
            answer = pre_decision.get("answer") or RAG_NO_MATCH_RESPONSE
            intent = detect_query_intent(text)
            is_definition_prefix = (text or "").strip().lower().startswith("what is") or (text or "").strip().lower().startswith("define")
            answer_type = str(pre_decision.get("answer_type") or "")
            fast_path_allowed = _is_safe_definition_fast_path_query(text)
            pre_family_v2 = _classify_query_family_v2(text)
            pre_family_legacy = _classify_query_family(text)
            pre_list_mode = bool(
                pre_family_v2 == "list_entity"
                or pre_family_legacy == "list_structure"
                or _is_targeted_list_question(text)
                or answer_type.startswith("list_")
            )
            if pre_list_mode and str(answer or "").strip() and str(answer).strip() != RAG_NO_MATCH_RESPONSE:
                strict_pre_fast = bool(answer_type in {"list_deterministic_context", "list_fast_simple", "list_extractor"})
                pre_ok, pre_reason, pre_shaped = _assess_list_coherence(text, _preclean_list_answer_for_assessment(str(answer)), strict_fast=strict_pre_fast, local_support=_collect_local_window_support(doc_dicts or []))
                S.logger.info("[LIST COHERENCE DEBUG] accepted=%s reason=%s", bool(pre_ok), pre_reason)
                if strict_pre_fast:
                    S.logger.info("[FAST LIST GUARD] accepted=%s reason=%s", bool(pre_ok), pre_reason)
                if not pre_ok:
                    answer = RAG_NO_MATCH_RESPONSE
                elif pre_shaped:
                    answer = pre_shaped

            if (intent == "definition" or is_definition_prefix) and answer_type.startswith("definition_"):
                fallback_answer = None
                if _is_valid_definition_lock_sentence(answer, text):
                    S.logger.info("[DEFINITION LOCK EARLY] applying lock")
                    answer = str(answer).strip()
                else:
                    fallback_answer = _extract_definition_sentence(focused_context, text, mode=answer_type)
                    if fallback_answer and _is_valid_definition_lock_sentence(fallback_answer, text):
                        S.logger.info("[DEFINITION LOCK EARLY] fallback extractor replacement applied")
                        answer = str(fallback_answer).strip()

            if (intent == "definition" or is_definition_prefix) and fast_path_allowed:
                if not _passes_strict_definition_relevance_guard(text, answer):
                    S.logger.info("[STRICT DEF PREF MISS] query=%s reason=definition_lock_preference_only", (text or "")[:120])
                    fallback_answer = _definition_explanation_fallback(text, doc_dicts, _extract_entity_from_definition_query(text)[1])
                    if fallback_answer:
                        answer = fallback_answer
                else:
                    if is_definition_prefix:
                        cleaned_pre_llm = _context_grounded_definition_override(text, doc_dicts, answer)
                        if cleaned_pre_llm:
                            answer = cleaned_pre_llm
                    answer = _force_clean_definition_sentence(text, answer, doc_dicts)
                    answer = _apply_not_found_ux(text, answer, doc_dicts)
                    if _is_explicit_oos_query(text):
                        answer = _not_found_response(text, "out_of_scope")

                    trace_extractor_used = True
                    S.logger.info("[TRACE] extractor_used=True")
                    S.logger.info("[TRACE] llm_used=False")
                    extraction_ms = (time.perf_counter() - extraction_t0) * 1000.0
                    response_time = int((time.time() - start_time) * 1000)
                    S.logger.info(
                        "LATENCY_BREAKDOWN query='%s' retrieval_ms=%.0f extraction_ms=%.0f validation_ms=0 llm_ms=0 total_ms=%d",
                        (text or "")[:80],
                        retrieval_ms,
                        extraction_ms,
                        response_time,
                    )
                    S._set_last_latency_breakdown(connection_id, retrieval_ms, extraction_ms, 0.0, 0.0, float(response_time))
                    if detect_query_intent(text) == "definition" or _is_simple_factual_text_query(text):
                        S._simple_rag_cache_put(text, answer)
                    log_usage(
                        username=user.get("username", "unknown"),
                        user_role=user.get("role", "unknown"),
                        query_text=text,
                        response_status="success",
                        error_message=None,
                        response_time_ms=response_time,
                        rag_docs_found=len(doc_dicts),
                        query_length=len(text.strip()),
                        response_length=len(answer),
                    )
                    return (answer, doc_dicts)

            if intent == "definition" and fast_path_allowed and not _passes_strict_definition_relevance_guard(text, answer):
                S.logger.info("[STRICT DEF PREF MISS] query=%s reason=post_extractor_preference_only", (text or "")[:120])
                fallback_answer = _definition_explanation_fallback(text, doc_dicts, _extract_entity_from_definition_query(text)[1])
                if fallback_answer:
                    answer = fallback_answer

            answer = _apply_not_found_ux(text, answer, doc_dicts)
            if _is_explicit_oos_query(text):
                answer = _not_found_response(text, "out_of_scope")

            trace_extractor_used = True
            S.logger.info("[TRACE] extractor_used=True")
            S.logger.info("[TRACE] llm_used=False")
            extraction_ms = (time.perf_counter() - extraction_t0) * 1000.0
            response_time = int((time.time() - start_time) * 1000)
            S.logger.info(
                "LATENCY_BREAKDOWN query='%s' retrieval_ms=%.0f extraction_ms=%.0f validation_ms=0 llm_ms=0 total_ms=%d",
                (text or "")[:80],
                retrieval_ms,
                extraction_ms,
                response_time,
            )
            S._set_last_latency_breakdown(connection_id, retrieval_ms, extraction_ms, 0.0, 0.0, float(response_time))
            if detect_query_intent(text) == "definition" or _is_simple_factual_text_query(text):
                S._simple_rag_cache_put(text, answer)
            log_usage(
                username=user.get("username", "unknown"),
                user_role=user.get("role", "unknown"),
                query_text=text,
                response_status="success",
                error_message=None,
                response_time_ms=response_time,
                rag_docs_found=len(doc_dicts),
                query_length=len(text.strip()),
                response_length=len(answer),
            )
            return (answer, doc_dicts)
        S.logger.info("[TRACE] extractor_used=False")

        extraction_ms = (time.perf_counter() - extraction_t0) * 1000.0

        is_fact_query_for_llm = (
            _classify_query_family_v2(text) == "fact_entity"
            and not S._skip_deterministic_rag_shortcuts(text, doc_router_mode)
        )
        context_docs_for_llm = _build_compact_fact_context_docs(text, doc_dicts, max_snippets=FACT_CONTEXT_MAX_SNIPPETS, max_chars=FACT_CONTEXT_MAX_CHARS) if is_fact_query_for_llm else doc_dicts
        toon_context = format_rag_context_toon(context_docs_for_llm)
        http_format_intent = S._classify_response_format_intent(text)
        if http_format_intent != "default" or doc_router_mode == "multi_source_synthesis":
            context_cap = 5200
        else:
            context_cap = FACT_CONTEXT_MAX_CHARS if is_fact_query_for_llm else (900 if is_simple_factual_query else 2200)
        if len(toon_context) > context_cap:
            toon_context = toon_context[:context_cap] + "\n...[Context truncated for length]..."
        if is_fact_query_for_llm:
            S.logger.info("[FACT CONTEXT] final_snippets=%s final_chars=%s", len(context_docs_for_llm or []), len(toon_context or ""))
        doc_router_context_rules = ""
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
        format_rules = ""
        if http_format_intent == "executive_memo":
            format_rules = (
                "\nFORMAT: EXECUTIVE MEMO\n"
                "- Write a professional memo with TO/FROM/DATE/SUBJECT headers.\n"
                "- Translate the findings in the context into clear, actionable recommendations.\n"
            )
        elif http_format_intent == "quiz_generation":
            format_rules = (
                "\nFORMAT: QUIZ GENERATION\n"
                "- Create exactly 5 numbered multiple-choice questions.\n"
                "- Each question MUST include four labeled options: A) B) C) D)\n"
                "- Base every question only on facts present in the provided context.\n"
                "- End with a section titled 'Answer Key' listing the correct letter for each question.\n"
            )
        elif http_format_intent == "extreme_summary":
            format_rules = (
                "\nFORMAT: EXTREME SUMMARY\n"
                "- Respond with exactly 5 bullet points, each on its own line starting with '- '.\n"
                "- Cover the main points present in the context.\n"
            )
        context_block = f"""
===== KNOWLEDGE BASE CONTEXT =====
{toon_context}
==================================
{doc_router_context_rules}
{format_rules}
"""

    if relevant_docs and doc_dicts:
        S.logger.info("[TRACE] intent=%s", detect_query_intent(text))
    S.logger.info("[TRACE] extractor_used=%s", trace_extractor_used)
    S.logger.info("[TRACE] llm_used=True")

    # Ensure arabic_mode and arabic_small_talk are defined
    arabic_mode = False
    arabic_small_talk = False

    fact_type_current = _detect_fact_query_type(text)
    is_fact_llm_query = (
        (_classify_query_family_v2(text) == "fact_entity")
        and bool(fact_type_current)
        and not S._skip_deterministic_rag_shortcuts(text, doc_router_mode)
    )
    http_format_intent = S._classify_response_format_intent(text)

    # Compose system_prompt and temperature before payload
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
            # Friendly customer-support persona with strict grounding
            system_prompt = build_english_support_system_prompt(format_extra_rules) + f"\n{context_block}"
    effective_temperature = 0.0 if is_fact_llm_query else (0.1 if is_simple_factual_query else (0.2 if relevant_docs else 0.6))
    if http_format_intent == "executive_memo":
        _http_num_ctx, _http_num_predict = 6144, 900
        effective_temperature = 0.2
        is_fact_llm_query = False
    elif http_format_intent == "quiz_generation":
        _http_num_ctx, _http_num_predict = 6144, 850
        effective_temperature = 0.15
        is_fact_llm_query = False
    elif http_format_intent == "extreme_summary":
        _http_num_ctx, _http_num_predict = 4096, 400
        effective_temperature = 0.1
        is_fact_llm_query = False
    elif doc_router_mode == "multi_source_synthesis" or is_generation_query_requested:
        _http_num_ctx, _http_num_predict = 4096, 700
        effective_temperature = 0.15
        is_fact_llm_query = False
    else:
        _http_num_ctx = 3072
        if is_fact_llm_query or _is_metric_fact_query(text):
            _http_num_predict = 180
        else:
            _http_num_predict = 96 if is_simple_factual_query else 150


    # --- Ensure all variables are defined before LLM logic ---
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text.strip()}
        ],
        "stream": False,
        "keep_alive": -1,  # keep model in VRAM — no cold-reload penalty
        "options": {
            "num_ctx": _http_num_ctx,    # must match warmup and streaming path
            "num_gpu": 99,
            "num_predict": _http_num_predict,
            "temperature": effective_temperature,
            "top_p": 0.9,
        },
    }
    username = user.get("username", "unknown")
    user_role = user.get("role", "unknown")
    query_length = len(text.strip())
    max_retries = 3
    ai_text = ""

    # Choose session: prefer persistent global; create local aiohttp session if missing.
    local_session_created = False
    _sess = S.llm_session
    if _sess is None or getattr(_sess, 'closed', False):
        try:
            connector = aiohttp.TCPConnector(limit=4, limit_per_host=2, force_close=False)
            _sess = aiohttp.ClientSession(connector=connector, headers={'Connection': 'keep-alive'})
            local_session_created = True
            S.logger.info("LLM: persistent session missing — created local aiohttp session (fallback)")
        except Exception as e:
            S.logger.warning(f"LLM: failed to create aiohttp fallback session: {e} — will try sync requests fallback")
            _sess = None

    # If we have an async session, prefer it
    if _sess is not None:
        _active_sess = _sess  # narrow type: guaranteed non-None in this block
        llm_t0 = time.perf_counter()
        if is_fact_llm_query:
            query_type = "fact_entity"
        elif is_simple_factual_query:
            query_type = "simple_factual"
        elif S._is_llm_generation_query(text):
            query_type = "generation"
        else:
            query_type = "general"
        S.logger.info("[OLLAMA CALL] endpoint=%s model=%s query_type=%s", LLM_URL, OLLAMA_MODEL, query_type)
        for attempt in range(max_retries):
            try:
                timeout = aiohttp.ClientTimeout(total=180, connect=5, sock_read=150)
                async with _active_sess.post(LLM_URL, json=payload, timeout=timeout) as response:
                    S.logger.info("[OLLAMA CALL RESULT] status=%s endpoint=%s", response.status, LLM_URL)
                    if response.status == 200:
                        data = await response.json()
                        if "error" in data:
                            S.logger.error(f"LLM returned error: {data['error']}")
                            response_time = int((time.time() - start_time) * 1000)
                            log_usage(username, user_role, text, "error", f"LLM error: {data['error']}", response_time, len(relevant_docs), query_length, 0)
                            if local_session_created and _sess and not _sess.closed:
                                await _sess.close()
                            return ("I'm having trouble processing that request. Please try again.", [])

                        ai_text = data["message"]["content"].strip()
                        ai_text = _clean_mixed_not_found_response(ai_text)

                        definition_override = _context_grounded_definition_override(text, relevant_docs, ai_text)
                        if definition_override:
                            ai_text = definition_override

                        if ai_text == RAG_NO_MATCH_RESPONSE and relevant_docs:
                            S.logger.info("Secondary LLM recovery pass disabled for deterministic RAG behavior")
                        break
                    else:
                        S.logger.error(f"LLM HTTP {response.status}")
                        if attempt < max_retries - 1:
                            await asyncio.sleep(0.5 * (attempt + 1))
                            continue
                        if local_session_created and _sess and not _sess.closed:
                            await _sess.close()
                        return ("The AI service is temporarily unavailable. Please try again.", [])
            except (aiohttp.ClientOSError, ConnectionResetError, OSError, asyncio.TimeoutError) as conn_err:
                S.logger.warning(f"LLM connection error (attempt {attempt+1}/{max_retries}): {conn_err}")
                if attempt < max_retries - 1:
                    try:
                        if local_session_created and _sess and not _sess.closed:
                            await _sess.close()
                    except Exception:
                        pass
                    try:
                        connector = aiohttp.TCPConnector(limit=4, limit_per_host=2, force_close=False)
                        _sess = aiohttp.ClientSession(connector=connector, headers={'Connection': 'keep-alive'})
                        local_session_created = True
                    except Exception:
                        _sess = None
                    await asyncio.sleep(1.0 * (attempt + 1))
                    continue
                S.logger.error(f"LLM connection failed after {max_retries} attempts")
                if local_session_created and _sess and not _sess.closed:
                    await _sess.close()
                return ("The AI service is currently unavailable. Please try again in a moment.", [])

        llm_ms = (time.perf_counter() - llm_t0) * 1000.0

        if local_session_created and _sess and not _sess.closed:
            try:
                await _sess.close()
            except Exception:
                pass
    else:
        # No aiohttp available/failable — fallback to synchronous requests in threadpool
        import requests
        llm_t0 = time.perf_counter()

        S.logger.info("LLM: using synchronous requests fallback (no async session available)")

        def _sync_post(url, json_payload, timeout_s=45):
            try:
                resp = requests.post(url, json=json_payload, timeout=timeout_s)
                return resp.status_code, resp.text
            except Exception as e:
                return None, str(e)

        S.logger.info("[OLLAMA CALL] endpoint=%s model=%s query_type=sync_fallback", LLM_URL, OLLAMA_MODEL)
        for attempt in range(max_retries):
            status, text_body = await asyncio.get_event_loop().run_in_executor(None, _sync_post, LLM_URL, payload, 45)
            S.logger.info("[OLLAMA CALL RESULT] status=%s endpoint=%s", status, LLM_URL)
            if status == 200:
                try:
                    data = json.loads(text_body)
                    ai_text = data.get("message", {}).get("content", "").strip()
                    ai_text = _clean_mixed_not_found_response(ai_text)
                    definition_override = _context_grounded_definition_override(text, relevant_docs, ai_text)
                    if definition_override:
                        ai_text = definition_override
                    if ai_text == RAG_NO_MATCH_RESPONSE and relevant_docs:
                        S.logger.info("Secondary LLM recovery pass disabled for deterministic RAG behavior")
                    break
                except Exception as e:
                    S.logger.warning(f"LLM sync fallback parse error: {e}")
                    await asyncio.sleep(0.5 * (attempt + 1))
                    continue
            S.logger.warning(f"LLM sync fallback HTTP error/status={status} body={str(text_body)[:160]}")
            await asyncio.sleep(0.5 * (attempt + 1))

        llm_ms = (time.perf_counter() - llm_t0) * 1000.0

    post_decision = _shared_rag_final_answer_decision(text, doc_dicts, llm_text=ai_text)
    post_decision = _enforce_runtime_answer_acceptance(text, post_decision, doc_dicts)
    if not post_decision.get("used_llm", True):
        S.logger.warning("Blocked bad output pattern detected; forcing extractor fallback")
        ai_text = post_decision.get("answer") or RAG_NO_MATCH_RESPONSE
        trace_extractor_used = True
        S.logger.info("[TRACE] extractor_used=True")
        S.logger.info("[TRACE] llm_used=False")

    compare_q = (text or "").strip().lower()
    is_compare_q = bool(
        re.search(r"difference\s+between\s+.+?\s+and\s+.+?(?:\?|$)", compare_q)
        or re.search(r"compare\s+.+?\s+and\s+.+?(?:\?|$)", compare_q)
    )
    if is_compare_q:
        forced_compare = _extract_overview_chapter_compare_answer(text, doc_dicts, focused_context)
        ai_text = (forced_compare or RAG_NO_MATCH_RESPONSE).strip()
        trace_extractor_used = True
        S.logger.info("[TRACE] compare_force_applied=True")

    definition_lock_applied = False
    intent = detect_query_intent(text)
    extracted_sentence = post_decision.get("answer") if isinstance(post_decision, dict) else None
    answer_type = str(post_decision.get("answer_type") or "") if isinstance(post_decision, dict) else ""
    if intent == "definition" and answer_type.startswith("definition_") and extracted_sentence is not None:
        if _is_valid_definition_lock_sentence(str(extracted_sentence), text):
            ai_text = str(extracted_sentence).strip()
            definition_lock_applied = True
            S.logger.info("[TRACE] definition_extractor_lock=True")

    # Validation runs after successful response
    validation_t0 = time.perf_counter()
    if definition_lock_applied:
        class _ValidationBypass:
            is_valid = True
            modified_response = None
            severity = "none"
            issues = []

        validation_result = _ValidationBypass()
    else:
        validation_result = validate_response(ai_text, text, relevant_docs)
    validation_ms = (time.perf_counter() - validation_t0) * 1000.0

    if not validation_result.is_valid:
        S.logger.warning(f"Response validation FAILED - Severity: {validation_result.severity}")
        for issue in validation_result.issues:
            S.logger.warning(f"  - {issue['severity']}: {issue['message']}")
        ai_text = str(validation_result.modified_response or "")
        response_time = int((time.time() - start_time) * 1000)
        log_usage(
            username,
            user_role,
            text,
            "validation_failed",
            f"{validation_result.severity}: {validation_result.issues[0]['message'] if validation_result.issues else 'unknown'}",
            response_time,
            len(relevant_docs),
            query_length,
            len(ai_text),
        )
    elif validation_result.modified_response:
        S.logger.info("Response modified by validation - added disclaimer")
        ai_text = str(validation_result.modified_response)

    if _is_explicit_oos_query(text):
        grounded = _is_answer_grounded_in_docs(ai_text, doc_dicts, query_text=text)
        strong_miss = _is_weak_retrieval_evidence(text, "out_of_scope_candidate", doc_dicts)
        if (not grounded) or strong_miss:
            ai_text = _not_found_response(text, "out_of_scope")
        else:
            ai_text = _not_found_response(text, "out_of_scope")

    post_family = _classify_query_family_v2(text)
    post_answer_type = str((post_decision or {}).get("answer_type") or "")
    if post_family in {"list_entity", "list_structure"}:
        strict_list_guard = bool(post_answer_type in {"list_deterministic_context", "list_fast_simple", "list_extractor"})
        list_ok_out, list_reason_out, list_shaped_out = _assess_list_coherence(text, _preclean_list_answer_for_assessment(ai_text), strict_fast=strict_list_guard, local_support=_collect_local_window_support(doc_dicts or []))
        S.logger.info("[LIST COHERENCE DEBUG] accepted=%s reason=%s", bool(list_ok_out), list_reason_out)
        if strict_list_guard:
            S.logger.info("[FAST LIST GUARD] accepted=%s reason=%s", bool(list_ok_out), list_reason_out)
        if (not list_ok_out) or (not list_shaped_out):
            ai_text = RAG_NO_MATCH_RESPONSE
            trace_extractor_used = True
        else:
            ai_text = list_shaped_out

    ai_text = _apply_not_found_ux(text, ai_text, doc_dicts)
    ai_text = S._enforce_unanswerable_detail_refusal(text, ai_text)
    _log_answer_mode_markers(text, doc_dicts, ai_text, source_mode=("extractor" if trace_extractor_used else "llm"))

    history.append({"role": "user", "content": text.strip()})
    history.append({"role": "assistant", "content": ai_text})

    response_time = int((time.time() - start_time) * 1000)
    response_length = len(ai_text)

    S.logger.info(
        "LATENCY_BREAKDOWN query='%s' retrieval_ms=%.0f extraction_ms=%.0f validation_ms=%.0f llm_ms=%.0f total_ms=%d",
        (text or "")[:80],
        retrieval_ms,
        extraction_ms,
        validation_ms,
        llm_ms,
        response_time,
    )
    S._set_last_latency_breakdown(connection_id, retrieval_ms, extraction_ms, validation_ms, llm_ms, float(response_time))

    if detect_query_intent(text) == "definition" or _is_simple_factual_text_query(text):
        S._simple_rag_cache_put(text, ai_text)

    # Log TOON token savings
    if relevant_docs and len(doc_dicts) > 0:
        sample_doc = doc_dicts[0]
        savings_stats = compare_token_efficiency(sample_doc)
        S.logger.info(f"TOON: Saved ~{savings_stats['token_savings_pct']}% tokens vs JSON in RAG context")

    # Only log success if validation passed
    if validation_result.is_valid:
        log_usage(
            username,
            user_role,
            text,
            "success",
            None,
            response_time,
            len(relevant_docs),
            query_length,
            response_length,
        )

    S.logger.info(f"RAG: Generated response ({len(ai_text)} chars) in {response_time}ms")
    try:
        _save_last_answer_state(connection_id, text, ai_text, doc_dicts or relevant_docs)
    except Exception:
        S.logger.exception("[FOLLOWUP] save state failed (HTTP path)")
    return (ai_text, relevant_docs)

