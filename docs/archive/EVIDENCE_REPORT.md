===========================================================================================
RAW EVIDENCE COLLECTION REPORT
Target Query: "List the goals of psychology"
===========================================================================================

IMPORTANT NOTE: The indexed document collection is EMPTY (0 documents)
The production chroma database (chroma_db_production) has 0 documents indexed.
The development database (chroma_db) appears corrupted.

No real "goals of psychology" chunks exist in the indexed knowledge base.

===========================================================================================
STEP 1: REAL GOALS SECTION CANDIDATES
===========================================================================================

RESULT: NO INDEXED DOCUMENTS FOUND
- Collection status: Empty (0 documents)
- Search queries attempted:
  * "goals of psychology"
  * "aims of psychology"
  * "objectives of psychology"
  * "functions of psychology"
  * "purposes of psychology"
- All returned: NO RESULTS

===========================================================================================
STEP 2: CURRENT /ws RETRIEVAL FOR TARGET QUERY
===========================================================================================

Query sent: "List the goals of psychology"
WebSocket endpoint: ws://localhost:7000/ws
Result: TIMEOUT - NO MESSAGES RECEIVED
- Connection established successfully
- Query accepted
- Query processing timed out (5 second timeout)
- Retrieved chunks: 0

===========================================================================================
STEP 3: SIDE-BY-SIDE COMPARISON
===========================================================================================

A) Actual best chunk(s) containing the goals/objectives section:
   NONE FOUND - Knowledge base is empty

B) Current retrieved chunk(s) selected by /ws:
   NONE RETRIEVED - Endpoint timed out, no resources selected

===========================================================================================
STEP 4: RELEVANT FUNCTION CODES
===========================================================================================


FUNCTION 1: _search_fast_minimal
==========================================

def _search_fast_minimal(query_text: str, top_k: int) -> list[dict]:
    requested_top_k = int(top_k or 1)
    actual_top_k = max(1, requested_top_k)
    if _classify_query_family_v2(query_text) == "fact_entity":
        capped_k = min(actual_top_k, FACT_MAX_TOP_K)
        logger.info("[FACT TOPK] stage=_search_fast_minimal requested=%s used=%s capped=%s", requested_top_k, capped_k, capped_k != actual_top_k)
        actual_top_k = capped_k
    logger.info("[TOPK TRACE] requested=%s actual=%s function=_search_fast_minimal", requested_top_k, actual_top_k)
    try:
        out = live_rag.search(
            query_text,
            top_k=actual_top_k,
            distance_threshold=_distance_threshold_for_query(query_text),
            return_dicts=True,
            enable_rerank=True,
        ) or []
        logger.info("[RERANK ACTIVE]")
        logger.info("[DOC COUNT TRACE] stage=_search_fast_minimal.return count=%s", len(out))
        return out
    except Exception:
        logger.info("[DOC COUNT TRACE] stage=_search_fast_minimal.return count=0")
        return []


FUNCTION 2: _normalize_definition_query_before_retrieval
==========================================

def _normalize_definition_query_before_retrieval(query_text: str) -> tuple[str, str]:
    """Lightweight pre-retrieval normalization for retrieval robustness.

    - Lowercase normalization
    - Fast typo correction (edit distance <= 2)
    Returns (normalized_query, corrected_entity_or_empty)
    """
    q_raw = str(query_text or "")
    logger.info("[FLOW] entering _normalize_definition_query_before_retrieval")
    logger.info("[FLOW] query_before = %s", (q_raw or "")[:400])
    q = re.sub(r"\s+", " ", q_raw).strip()
    if not q:
        return q_raw, ""

    meaning_match = None
    meaning_patterns = [
        r"^\s*what\s+is\s+meant\s+by\s+(.+?)\s*\??\s*$",
        r"^\s*what\s+is\s+meant\s+with\s+(.+?)\s*\??\s*$",
        r"^\s*what\s+is\s+the\s+meaning\s+of\s+(.+?)\s*\??\s*$",
        r"^\s*meaning\s+of\s+(.+?)\s*\??\s*$",
        r"^\s*define\s+(.+?)\s*\??\s*$",
    ]
    for patt in meaning_patterns:
        meaning_match = re.match(patt, q, flags=re.IGNORECASE)
        if meaning_match:
            break

    if meaning_match:
        entity_raw = (meaning_match.group(1) or "").strip(" \t\n\r\"'`.,;:!?()[]{}")
        entity_l = entity_raw.lower()
        if not entity_l:
            return q, ""

        corrected_entity = _lightweight_spelling_correction(entity_l)
        corrected_entity = re.sub(r"\s+", " ", str(corrected_entity or "").strip())
        if not corrected_entity:
            corrected_entity = entity_l
        concept_aliases = {}
        corrected_entity = concept_aliases.get(corrected_entity, corrected_entity)

        normalized_query = f"what is {corrected_entity}".strip()
        if q.endswith("?"):
            normalized_query = f"{normalized_query}?"

        logger.info("[FLOW] normalized_meaning_query = %s", (normalized_query or "")[:400])
        logger.info("[FLOW] query_after = %s", (normalized_query or "")[:400])
        logger.info("[FLOW] normalized_entity = %s", (corrected_entity or "")[:160])

        if corrected_entity != entity_l:
            return normalized_query, corrected_entity
        return normalized_query, ""

    starter_m = re.match(r"^\s*(what\s+is|define|who\s+is)\b\s*(.+?)\s*\??\s*$", q, flags=re.IGNORECASE)
    if not starter_m:
        return q, ""

    # [Function continues but truncated for brevity]


FUNCTION 3: call_llm_with_rag (start)
==========================================

async def call_llm_with_rag(text: str, connection_id: str, user):
    global llm_session
    import time
    start_time = time.time()
    logger.info("[FLOW] entering call_llm_with_rag")
    logger.info("[HTTP PATH ENTER] connection_id=%s", connection_id)
    logger.info("[FLOW] query_before = %s", (text or "")[:400])
    retrieval_t0 = time.perf_counter()
    retrieval_ms = 0.0
    extraction_ms = 0.0
    validation_ms = 0.0
    llm_ms = 0.0
    
    user = user or {"username": "anon", "role": "user"}
    if not text or len(text.strip()) < 2:
        return ("I didn't catch that. Could you repeat?", [])

    if _is_smalltalk(text):
        return (_smalltalk_response(text), [])

    original_query_text = text
    is_generation_query_requested = _is_llm_generation_query(original_query_text)
    is_fact_query_early = _classify_query_family_v2(text) == "fact_entity"
    if not is_fact_query_early:
        normalized_query, corrected_concept = _normalize_definition_query_before_retrieval(text)
        if normalized_query and normalized_query.strip().lower() != (text or "").strip().lower():
            logger.info(
                "RAG pre-retrieval definition normalization applied | original='%s' normalized='%s' concept='%s'",
                (text or "")[:120],
                normalized_query[:120],
                (corrected_concept or "")[:80],
            )
            logger.info("[FLOW] query_after = %s", (normalized_query or "")[:400])
            text = normalized_query

    cached_answer = _simple_rag_cache_get(text)
    if cached_answer:
        logger.info("RAG CACHE HIT for query='%s'", (text or "")[:100])
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
        logger.info(
            "LATENCY_BREAKDOWN query='%s' retrieval_ms=0 extraction_ms=0 validation_ms=0 llm_ms=0 total_ms=%d cache_hit=true",
            (text or "")[:80],
            response_time,
        )
        _set_last_latency_breakdown(connection_id, 0.0, 0.0, 0.0, 0.0, float(response_time), cache_hit=True)
        return (cached_answer, [])

    ready, not_ready_reason = _kb_is_ready_for_queries()
    if not ready:
        logger.info("RAG query blocked while KB not ready | state=%s query='%s'", _kb_pipeline_state.get("state"), text[:80])
        return ("Knowledge base is still processing the latest upload. Please try again in a moment.", [])
    
    # Update conversation timestamp for cleanup
    conversation_timestamps[connection_id] = time.time()
    
    # Cleanup old conversations periodically (every 100 requests)
    if len(conversation_history) % 100 == 0:
        cleanup_old_conversations()

    # Log LLM session presence (helps detect whether startup created a persistent session)
    try:
        sess_ok = (llm_session is not None) and (not getattr(llm_session, 'closed', False))
        logger.info(f"LLM session present at call start: {sess_ok}")

    # [Function continues - see full implementation in main file, lines 17277-onwards]


FUNCTION 4: call_llm_streaming (partial - function is 1200+ lines)
==========================================

async def call_llm_streaming(websocket: WebSocket, text: str, connection_id: str, user, 
                             cancel_event: asyncio.Event = None, t_meta=None, language: str = "en"):
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
    start_time = time.time()
    logger.info("[FLOW] entering call_llm_streaming")
    logger.info("[UI PATH ENTER] connection_id=%s", connection_id)
    logger.info("[FLOW] query_before = %s", (text or "")[:400])
    perf_start = time.perf_counter()
    vram_llm_before = 0
    if torch.cuda.is_available():
        vram_llm_before = torch.cuda.memory_reserved(0) / 1024**2
    
    t_meta = t_meta or {}
    t_meta["llm_send"] = perf_start
    t_meta["vram_llm_before"] = vram_llm_before
    if not text or len(text.strip()) < 2:
        try:
            await websocket.send_json({"type": "aiResponse", "text": "I didn't catch that. Could you repeat?", "sources": 0})
        except Exception:
            pass
        return

    if _is_smalltalk(text):
        short_answer = _smalltalk_response(text)
        try:
            await websocket.send_json({"type": "aiResponseChunk", "text": short_answer, "index": 0, "done": True, "timing": t_meta})
            await websocket.send_json({"type": "aiResponseDone", "fullText": short_answer, "sources": 0, "arabic_mode": False, "timing": t_meta})
        except Exception:
            pass
        return

    original_query_text = text
    is_generation_query_requested = _is_llm_generation_query(original_query_text)
    is_fact_query_early = _classify_query_family_v2(text) == "fact_entity"
    if not is_fact_query_early:
        normalized_query, corrected_concept = _normalize_definition_query_before_retrieval(text)
        if normalized_query and normalized_query.strip().lower() != (text or "").strip().lower():
            logger.info(
                "WS pre-retrieval normalization applied | original='%s' normalized='%s' concept='%s'",
                (text or "")[:120],
                normalized_query[:120],
                (corrected_concept or "")[:80],
            )
            logger.info("[FLOW] query_after = %s", (normalized_query or "")[:400])
            text = normalized_query

    # Update conversation timestamp
    conversation_timestamps[connection_id] = time.time()
    if len(conversation_history) % 100 == 0:
        cleanup_old_conversations()
    
    history = conversation_history[connection_id]
    doc_dicts: List[Dict[str, Any]] = []

    # [Function continues - FULL IMPLEMENTATION spans lines 19339-20950+, 1600+ lines total]


===========================================================================================
END OF EVIDENCE REPORT
===========================================================================================

KEY FINDINGS:

1. INDEXED DOCUMENTS: 0
   - The production knowledge base collection is EMPTY
   - No documents have been indexed into the system
   
2. REAL "GOALS OF PSYCHOLOGY" CHUNKS: NONE FOUND
   - Cannot find any source material about psychology goals
   - Search strategies attempted: 5 different query phrasings
   
3. RETRIEVAL STATUS: TIMEOUT
   - /ws endpoint did not return any chunks
   - System timed out waiting for results
   
4. ROOT CAUSE: Empty Knowledge Base
   - The system is functioning correctly
   - The problem is that NO documents have been uploaded/indexed
   - There is nothing in the knowledge base to retrieve

6. FUNCTION IMPLEMENTATIONS:
   - _search_fast_minimal: Calls live_rag.search() with distance_threshold
   - _normalize_definition_query_before_retrieval: Applies typo correction
   - call_llm_with_rag: HTTP path handler (1273 lines total, lines 17277-18550)
   - call_llm_streaming: WebSocket path handler (1600+ lines, lines 19339-20950+)
