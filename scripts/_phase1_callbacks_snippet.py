
# ========== VOICE WS CALLBACKS (Phase 1 extraction) ==========
async def _process_voice_transcript_ws(
    *,
    ws,
    conn_id: str,
    full_text: str,
    lang: str,
    t_meta,
    user,
    active_conversation_id,
    _activate_conversation,
    _conversation_ws,
    segments_list=None,
):
                    try:
                        await ws.send_json({
                            "type": "transcript",
                            "text": full_text,
                            "final": True,
                            "timing": t_meta,
                        })

                        conversation_id_for_voice = _activate_conversation(active_conversation_id)
                        conversation_ws = _conversation_ws(conversation_id_for_voice)
                        try:
                            append_conversation_message(conversation_id_for_voice, "user", full_text)
                        except Exception:
                            logger.exception("[CONV] failed to persist voice user message id=%s", conversation_id_for_voice)

                        cancel_evt = interrupt_events.get(conn_id)
                        if cancel_evt:
                            cancel_evt.clear()

                        voice_force_final_language_for_rewrite = None
                        voice_history_snapshot = list(conversation_history.get(conn_id, []) or [])
                        rewritten_voice_comparison = _rewrite_bare_comparison_query_from_history(full_text, voice_history_snapshot, conn_id)
                        if rewritten_voice_comparison and rewritten_voice_comparison != full_text:
                            logger.info(
                                "[COMPARE FOLLOWUP REWRITE] original=%r rewritten=%r",
                                (full_text or "")[:160],
                                rewritten_voice_comparison[:160],
                            )
                            if lang in {"ar", "en"}:
                                voice_force_final_language_for_rewrite = lang
                            full_text = rewritten_voice_comparison

                        # ---- ABOUT-ENTITY STANDALONE REWRITE (voice path) ----
                        # Same shared helper as the typed-text path so behavior
                        # cannot drift between voice and text.
                        if not _is_memory_rewrite_query(full_text):
                            full_text = _maybe_rewrite_about_entity_question(full_text)

                        # ---- P12C-1: ARABIC FOLLOW-UP REFERENCE RESOLUTION (voice) --
                        try:
                            if not _is_memory_rewrite_query(full_text):
                                ar_resolved_v, ar_reason_v = _maybe_resolve_arabic_followup_reference(full_text, conn_id)
                                if ar_resolved_v and ar_resolved_v != full_text:
                                    logger.info(
                                        "[AR FOLLOWUP MEMORY] resolved_query=%s reason=%s original=%s",
                                        ar_resolved_v[:200],
                                        ar_reason_v,
                                        (full_text or "")[:200],
                                    )
                                    full_text = ar_resolved_v
                        except Exception:
                            logger.exception("[AR FOLLOWUP MEMORY] voice resolution failed; continuing")

                        # Voice answers follow the explicit UI language lock used for STT.
                        lang = requested_voice_lang

                        # ---- FOLLOW-UP ROUTING (voice path) ----
                        # Bypass full RAG retrieval/LLM pipeline for clarification
                        # queries spoken by the user.
                        try:
                            _fu_check_v = _is_followup_query(full_text, conn_id)
                        except Exception:
                            _fu_check_v = False
                        logger.error("🔥 WS RECEIVED TEXT (voice): %s", full_text)
                        logger.error("🔥 FOLLOWUP CHECK (voice): %s", _fu_check_v)
                        if _fu_check_v:
                            logger.error("🔥 FOLLOWUP ROUTE TRIGGERED (voice)")
                            logger.info("[FOLLOWUP ROUTE] triggered for query=%s", full_text)
                            fu_text, _ = await _handle_followup_query(full_text, conn_id)
                            fu_text = (fu_text or "").strip() or RAG_NO_MATCH_RESPONSE
                            try:
                                history = conversation_history[conn_id]
                                history.append({"role": "user", "content": full_text.strip()})
                                history.append({"role": "assistant", "content": fu_text})
                            except Exception:
                                pass
                            try:
                                # Phase 7B: ensure request_start exists & is monotonic so
                                # downstream perf metrics never go negative.
                                fu_t_meta = t_meta if isinstance(t_meta, dict) else {}
                                if not fu_t_meta.get("request_start"):
                                    fu_t_meta["request_start"] = time.perf_counter()
                                fu_perf_start = fu_t_meta["request_start"]
                                await send_final_response(
                                    conn_id,
                                    fu_text,
                                    "ar" if lang == "ar" else XTTS_LANGUAGE,
                                    not EFFECTIVE_DISABLE_TTS,
                                    websocket=conversation_ws,
                                    sources=0,
                                    arabic_mode=(lang == "ar"),
                                    t_meta=fu_t_meta,
                                    branch="followup_voice",
                                )
                                _emit_perf_report(fu_t_meta, fu_perf_start, full_text, fu_text, conn_id)
                            except Exception:
                                pass
                            logger.info("[FOLLOWUP ROUTE] complete for query=%s", full_text)
                            logger.error("🔥 FOLLOWUP ROUTE COMPLETE (voice)")
                            return

                        if voice_force_final_language_for_rewrite in {"ar", "en"}:
                            t_meta["force_final_language"] = voice_force_final_language_for_rewrite
                        await call_llm_streaming(
                            conversation_ws, full_text, conn_id,
                            user or {"username": "anon", "role": "user"},
                            cancel_evt,
                            t_meta,
                            language=lang,
                        )
                        persist_runtime_memory(conn_id, conversation_id_for_voice)


async def _process_ws_text_message(
    *,
    websocket,
    connection_id: str,
    payload: dict,
    user,
    session_language: str,
    ws_tenant_id: int,
    ws_owner,
    activate_conversation,
    conversation_ws_factory,
    set_session_language,
):
    nonlocal_session = [session_language]
                        elif "text" in payload:
                            # Handle typed text queries with streaming
                            text = payload["text"].strip()
                            stored_user_text = text
                            client_tts_enabled = bool(payload.get("tts_enabled", False))
                            query_tts = _client_tts_allowed(client_tts_enabled)
                            # Allow per-message language override; fall back to session setting
                            msg_lang = str(payload.get("language", session_language) or session_language).strip().lower()
                            if msg_lang in ("en", "ar"):
                                session_language = msg_lang  # update session preference
                            force_final_language_for_rewrite = None
                            if text:
                                _cancel_active_ws_tts(connection_id, "new_user_query")
                                cancel_evt_for_new_text = interrupt_events.get(connection_id)
                                if cancel_evt_for_new_text:
                                    cancel_evt_for_new_text.clear()
                                conversation_id_for_text = _activate_conversation(payload.get("conversation_id"))
                                conversation_ws = _conversation_ws(conversation_id_for_text)
                                try:
                                    append_conversation_message(conversation_id_for_text, "user", stored_user_text)
                                except Exception:
                                    logger.exception("[CONV] failed to persist user message id=%s", conversation_id_for_text)

                                # ---- P12C-1: ARABIC FOLLOW-UP RESOLUTION (earliest) ----
                                # Run before about-entity normalization; otherwise
                                # Arabic ordinal references like "اشرح الثانية" can
                                # be flattened into standalone "ما هي الثانية؟" and
                                # lose the previous-list target.
                                text, ar_reason_early = _resolve_and_mark_arabic_followup_for_ws(text, connection_id, "early")
                                if ar_reason_early and msg_lang in {"ar", "en"}:
                                    force_final_language_for_rewrite = msg_lang

                                # ---- ABOUT-ENTITY STANDALONE REWRITE (typed WS, pre-router) ----
                                # Run BEFORE the direct router so shapes like
                                # "What about X?" / "وماذا عن X" with a real new
                                # entity X are normalized to "What is X?" /
                                # "ما هي X؟" and don't get mis-classified as
                                # `unsupported_unclear`.
                                if not _is_memory_rewrite_query(text) and not _is_marked_arabic_resolved_followup(connection_id, text):
                                    text = _maybe_rewrite_about_entity_question(text)

                                # ---- LANGUAGE RESOLUTION (Phase 7C — TASK 1) ----
                                # Always trust the actual script of the user's
                                # query over the UI/session language flag so the
                                # router/follow-up/RAG branches all agree on the
                                # answer language. UI language remains a hint only.
                                _resolved_msg_lang = _resolve_user_language(stored_user_text or text, msg_lang)
                                if _resolved_msg_lang != msg_lang:
                                    logger.info(
                                        "[LANG ROUTE] original_language=%s ui_language=%s overriding=True branch=ws_typed",
                                        _resolved_msg_lang, msg_lang,
                                    )
                                msg_lang = _resolved_msg_lang
                                if _is_marked_arabic_resolved_followup(connection_id, text) and msg_lang in {"ar", "en"}:
                                    force_final_language_for_rewrite = msg_lang

                                # ---- P12C-1: ARABIC FOLLOW-UP REFERENCE RESOLUTION ----
                                # Must run before the direct unsupported/unclear
                                # router, otherwise short Arabic anaphora such as
                                # "وما علاقتها بالرقابة؟" is rejected before it can
                                # become an explicit grounded RAG query.
                                text, ar_reason_pre = _resolve_and_mark_arabic_followup_for_ws(text, connection_id, "pre-router")
                                if ar_reason_pre and msg_lang in {"ar", "en"}:
                                    force_final_language_for_rewrite = msg_lang

                                if _is_memory_rewrite_query(text):
                                    route_t0 = time.perf_counter()
                                    route_t_meta = {
                                        "request_start": route_t0,
                                        "query_translation_ms": 0,
                                        "query_translation_skipped": True,
                                        "retrieval_after_translation_ms": 0,
                                    }
                                    if msg_lang == "ar":
                                        ar_classify_t0 = time.perf_counter()
                                        ar_type = _classify_arabic_query_type(text)
                                        route_t_meta["ar_query_type"] = ar_type
                                        route_t_meta["ar_query_classification_ms"] = int(round((time.perf_counter() - ar_classify_t0) * 1000))
                                        logger.info("[AR QUERY TYPE] type=%s", ar_type)
                                    mem_text, _ = await _handle_memory_rewrite_query(text, connection_id)
                                    mem_text = (mem_text or "").strip() or RAG_NO_MATCH_RESPONSE
                                    try:
                                        history = conversation_history[connection_id]
                                        history.append({"role": "user", "content": text.strip()})
                                        history.append({"role": "assistant", "content": mem_text})
                                    except Exception:
                                        pass
                                    try:
                                        await send_final_response(
                                            connection_id,
                                            mem_text,
                                            "ar" if msg_lang == "ar" else XTTS_LANGUAGE,
                                            query_tts,
                                            websocket=conversation_ws,
                                            sources=0,
                                            arabic_mode=(msg_lang == "ar"),
                                            t_meta=route_t_meta,
                                            branch="memory_rewrite_text",
                                        )
                                        _emit_perf_report(route_t_meta, route_t0, text, mem_text, connection_id)
                                    except Exception:
                                        pass
                                    try:
                                        log_usage(
                                            username=(user or {}).get("username", "unknown"),
                                            user_role=(user or {}).get("role", "unknown"),
                                            query_text=stored_user_text,
                                            response_status="success",
                                            error_message=None,
                                            response_time_ms=int((time.perf_counter() - route_t0) * 1000),
                                            rag_docs_found=0,
                                            query_length=len(stored_user_text),
                                            response_length=len(mem_text or ""),
                                        )
                                    except Exception:
                                        pass
                                    persist_runtime_memory(connection_id, conversation_id_for_text)
                                    continue

                                route = classify_query_route(text)
                                if route in _ROUTER_DIRECT_ROUTES:
                                    route_lang = _route_response_language(text, msg_lang)
                                    direct_answer = _direct_route_answer(text, route, route_lang)
                                    _log_direct_route_handled(route, text, route_lang)
                                    if direct_answer == RAG_NO_MATCH_RESPONSE:
                                        try:
                                            _save_last_answer_state(connection_id, text, direct_answer, [])
                                        except Exception:
                                            logger.exception("[FOLLOWUP] save state failed (WS typed direct not-found)")
                                    try:
                                        _append_conversation_turn(connection_id, stored_user_text, direct_answer)
                                    except Exception:
                                        pass
                                    try:
                                        route_t0 = time.perf_counter()
                                        route_t_meta = {"request_start": route_t0}
                                        response_tts_lang = "ar" if (route_lang == "ar" and route != "unsupported_unclear") else XTTS_LANGUAGE
                                        await send_final_response(
                                            connection_id,
                                            direct_answer,
                                            response_tts_lang,
                                            query_tts,
                                            websocket=conversation_ws,
                                            sources=0,
                                            arabic_mode=(route_lang == "ar" and route != "unsupported_unclear"),
                                            t_meta=route_t_meta,
                                            branch=f"router_{route}",
                                        )
                                        _emit_perf_report(route_t_meta, route_t0, text, direct_answer, connection_id)
                                    except Exception:
                                        pass
                                    try:
                                        log_usage(
                                            username=(user or {}).get("username", "unknown"),
                                            user_role=(user or {}).get("role", "unknown"),
                                            query_text=stored_user_text,
                                            response_status="success",
                                            error_message=None,
                                            response_time_ms=0,
                                            rag_docs_found=0,
                                            query_length=len(stored_user_text),
                                            response_length=len(direct_answer or ""),
                                        )
                                    except Exception:
                                        pass
                                    persist_runtime_memory(connection_id, conversation_id_for_text)
                                    continue

                                if _is_weak_generic_request(text):
                                    direct_answer = _finalize_user_visible_answer(
                                        text, RAG_NO_MATCH_RESPONSE, msg_lang
                                    )
                                    logger.info("[ANSWER PERMISSION] allowed=False reason=weak_generic_entrypoint query=%s", text[:180])
                                    try:
                                        _save_last_answer_state(connection_id, text, direct_answer, [])
                                    except Exception:
                                        logger.exception("[FOLLOWUP] save state failed (WS weak generic not-found)")
                                    try:
                                        _append_conversation_turn(connection_id, stored_user_text, direct_answer)
                                    except Exception:
                                        pass
                                    try:
                                        route_t0 = time.perf_counter()
                                        route_t_meta = {"request_start": route_t0}
                                        await send_final_response(
                                            connection_id,
                                            direct_answer,
                                            XTTS_LANGUAGE,
                                            query_tts,
                                            websocket=conversation_ws,
                                            sources=0,
                                            arabic_mode=False,
                                            t_meta=route_t_meta,
                                            branch="weak_generic_entrypoint",
                                        )
                                        _emit_perf_report(route_t_meta, route_t0, text, direct_answer, connection_id)
                                    except Exception:
                                        pass
                                    try:
                                        log_usage(
                                            username=(user or {}).get("username", "unknown"),
                                            user_role=(user or {}).get("role", "unknown"),
                                            query_text=stored_user_text,
                                            response_status="success",
                                            error_message=None,
                                            response_time_ms=0,
                                            rag_docs_found=0,
                                            query_length=len(stored_user_text),
                                            response_length=len(direct_answer or ""),
                                        )
                                    except Exception:
                                        pass
                                    persist_runtime_memory(connection_id, conversation_id_for_text)
                                    continue

                                # Generic conversational definition normalization
                                # (e.g. "ok so what about the definition of X?" ->
                                # "what is X?"). Run only for document questions so
                                # meta/smalltalk is never typo-corrected into RAG.
                                try:
                                    _norm_text = _normalize_conversational_definition_query(text)
                                except Exception:
                                    _norm_text = text
                                if _norm_text and _norm_text != text:
                                    logger.info(
                                        "[CONV NORM] '%s' -> '%s'",
                                        text[:160], _norm_text[:160],
                                    )
                                    text = _norm_text
                                _spell_norm_text = _spelling_correction_preserving_exact_terms(text)
                                if _spell_norm_text and _spell_norm_text.strip().lower() != (text or "").strip().lower():
                                    text = _spell_norm_text
                                # ---- KB READY GATE (must be before follow-up or RAG) ----
                                # Block all queries while a new document is being indexed
                                # so no old-document content leaks and no answer is given
                                # before the new KB is fully ready.
                                _kb_ready, _kb_not_ready_reason = _kb_is_ready_for_queries()
                                if not _kb_ready:
                                    _loading_msg = "System is loading the document. Please wait..."
                                    logger.info(
                                        "[KB GATE] WS query blocked during indexing | state=%s query='%s'",
                                        _kb_pipeline_state.get("state"),
                                        text[:80],
                                    )
                                    try:
                                        await send_final_response(
                                            connection_id,
                                            _loading_msg,
                                            XTTS_LANGUAGE,
                                            query_tts,
                                            websocket=conversation_ws,
                                            sources=0,
                                            arabic_mode=False,
                                            t_meta={"request_start": time.perf_counter()},
                                            branch="kb_loading_gate",
                                        )
                                    except Exception:
                                        pass
                                    continue
                                history_snapshot = list(conversation_history.get(connection_id, []) or [])
                                rewritten_comparison_query = _rewrite_bare_comparison_query_from_history(text, history_snapshot, connection_id)
                                if rewritten_comparison_query and rewritten_comparison_query != text:
                                    logger.info(
                                        "[COMPARE FOLLOWUP REWRITE] original=%r rewritten=%r",
                                        (text or "")[:160],
                                        rewritten_comparison_query[:160],
                                    )
                                    if msg_lang in {"ar", "en"}:
                                        force_final_language_for_rewrite = msg_lang
                                    text = rewritten_comparison_query

                                # ---- P12C-1: ARABIC FOLLOW-UP REFERENCE RESOLUTION ----
                                # Rewrite Arabic pronoun/ordinal references
                                # ("وما علاقتها بالرقابة؟", "اشرح الثانية",
                                # "كيف ترتبط بالأخيرة؟") into explicit
                                # grounded queries using the previous saved
                                # answer state. The rewritten query then
                                # flows through the normal /ws routing
                                # (followup vs RAG) so retrieval grounds
                                # the final answer.
                                text, ar_reason = _resolve_and_mark_arabic_followup_for_ws(text, connection_id, "post-kb")
                                if ar_reason and msg_lang in {"ar", "en"}:
                                    force_final_language_for_rewrite = msg_lang

                                # ---- HARD DEBUG: prove the WS entrypoint is reached ----
                                try:
                                    _fu_check = _is_followup_query(text, connection_id)
                                    _ar_marker_reason = _get_marked_arabic_resolved_followup_reason(connection_id, text)
                                    if _ar_marker_reason == "ar_ordinal_explain":
                                        logger.info("[AR FOLLOWUP MEMORY] ordinal_explain_followup_route=True resolved_query=%s", text[:200])
                                        _fu_check = True
                                    elif _fu_check and _ar_marker_reason:
                                        logger.info("[AR FOLLOWUP MEMORY] followup_shortcut_bypassed=True resolved_query=%s", text[:200])
                                        _fu_check = False
                                except Exception:
                                    _fu_check = False
                                logger.error("🔥 WS RECEIVED TEXT: %s", text)
                                logger.error("🔥 FOLLOWUP CHECK: %s", _fu_check)
                                logger.info(f"{connection_id} text query [{msg_lang}]: {text}")
                                logger.info("[FLOW] entering rag_ws_endpoint (typed text path)")
                                logger.info("[FLOW] query_before = %s", (text or "")[:400])
                                cancel_evt = interrupt_events.get(connection_id)
                                if cancel_evt:
                                    cancel_evt.clear()
                                # ---- FOLLOW-UP ROUTING (highest priority) ----
                                # Intercept clarification queries BEFORE any
                                # retrieval / LLM call so they never hit the
                                # full RAG pipeline.
                                if _fu_check:
                                    logger.error("🔥 FOLLOWUP ROUTE TRIGGERED")
                                    logger.info("[FOLLOWUP ROUTE] triggered for query=%s", text)
                                    fu_text, _ = await _handle_followup_query(text, connection_id)
                                    fu_text = (fu_text or "").strip() or RAG_NO_MATCH_RESPONSE
                                    try:
                                        history = conversation_history[connection_id]
                                        history.append({"role": "user", "content": text.strip()})
                                        history.append({"role": "assistant", "content": fu_text})
                                    except Exception:
                                        pass
                                    try:
                                        fu_t_meta = {"request_start": time.perf_counter()}
                                        await send_final_response(
                                            connection_id,
                                            fu_text,
                                            "ar" if msg_lang == "ar" else XTTS_LANGUAGE,
                                            query_tts,
                                            websocket=conversation_ws,
                                            sources=0,
                                            arabic_mode=(msg_lang == "ar"),
                                            t_meta=fu_t_meta,
                                            branch="followup_text",
                                        )
                                        _emit_perf_report(fu_t_meta, fu_t_meta["request_start"], text, fu_text, connection_id)
                                    except Exception:
                                        pass
                                    logger.info("[FOLLOWUP ROUTE] complete for query=%s", text)
                                    logger.error("🔥 FOLLOWUP ROUTE COMPLETE")
                                    continue
                                _ws_perf_t_meta: Dict[str, Any] = {"request_start": time.perf_counter()}
                                if force_final_language_for_rewrite in {"ar", "en"}:
                                    _ws_perf_t_meta["force_final_language"] = force_final_language_for_rewrite
                                await call_llm_streaming(
                                    conversation_ws, text, connection_id,
                                    user or {"username": "anon", "role": "user"},
                                    cancel_evt,
                                    t_meta=_ws_perf_t_meta,
                                    language=msg_lang,
                                    client_tts_enabled=client_tts_enabled,
                                )
                                persist_runtime_memory(connection_id, conversation_id_for_text)

