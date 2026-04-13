import re

file_path = "g:/Grad_Project/assistify-rag-project-main/backend/assistify_rag_server.py"

with open(file_path, "r", encoding="utf-8") as f:
    code = f.read()

# 1. _search_fast_definition_minimal
c1_target = """    if is_concept_query and concept_text:
        probes.extend([
            (query_text or "").strip(),
            f"definition of {concept_text}",
            f"{concept_text} is",
        ])
    else:
        probes.append((query_text or "").strip())

    for q in probes[:3]:"""
c1_repl = """    probes = [(query_text or "").strip()]
    logger.info("[DEFINITION PROBE DISABLED]")
    for q in probes:"""
code = code.replace(c1_target, c1_repl)

# 2. _search_with_query_expansion
c2_target = """def _search_with_query_expansion(query_text: str, top_k: int, distance_threshold: float, return_dicts: bool = True, enable_rerank: bool = True) -> list[dict]:
    expanded = _expand_query(query_text)"""
c2_repl = """def _search_with_query_expansion(query_text: str, top_k: int, distance_threshold: float, return_dicts: bool = True, enable_rerank: bool = True) -> list[dict]:
    q_fam = _classify_query_family_v2(query_text)
    if q_fam in {"definition_entity", "fact_entity", "list_entity"}:
        logger.info("[DIRECT ROUTE] family=%s", q_fam)
        logger.info("[EXPANSION SKIPPED]")
        return _search_fast_minimal(query_text, top_k=top_k)

    expanded = _expand_query(query_text)"""
code = code.replace(c2_target, c2_repl)

# 3. call_llm_with_rag routing
c3_target = """        if is_definition_fast:
            relevant_docs = _search_fast_definition_minimal(text)
        else:
            relevant_docs = _search_fast_minimal(text, top_k=top_k_req)"""
c3_repl = """        family_v2 = _classify_query_family_v2(text)
        if family_v2 in {"definition_entity", "fact_entity", "list_entity"}:
            logger.info("[DIRECT ROUTE] family=%s", family_v2)
            logger.info("[PRIMARY SEARCH] used=_search_fast_minimal")
            relevant_docs = _search_fast_minimal(text, top_k=top_k_req)
        elif is_definition_fast:
            relevant_docs = _search_fast_definition_minimal(text)
        else:
            relevant_docs = _search_fast_minimal(text, top_k=top_k_req)"""
code = code.replace(c3_target, c3_repl)

# 4. call_llm_with_rag FACT RESCUE
c4_target = """        if _classify_query_family_v2(text) == "fact_entity":
            try:
                fact_rescue_queries = _build_fact_rescue_queries(text, history)
                rescue_collected: list[dict] = []
                for retry_count, rq in enumerate((fact_rescue_queries or [])[:MAX_FACT_RETRIES], start=1):
                    logger.info("[FACT RETRY] count=%s", retry_count)
                    logger.info("[FACT RESCUE QUERY] %s", rq)
                    rescue_collected.extend(_search_fast_minimal(rq, top_k=8) or [])
                if len(fact_rescue_queries or []) >= MAX_FACT_RETRIES:
                    logger.info("[FACT RETRY] max_reached=True")
                if rescue_collected:"""
c4_repl = """        if _classify_query_family_v2(text) == "fact_entity":
            if relevant_docs:
                logger.info("[FACT RESCUE USED]=False")
            else:
                try:
                    fact_rescue_queries = _build_fact_rescue_queries(text, history)
                    rescue_collected: list[dict] = []
                    for rq in (fact_rescue_queries or [])[:1]:
                        if rq == text: continue
                        logger.info("[FACT RESCUE USED]=True")
                        logger.info("[FACT RETRY] count=1")
                        logger.info("[FACT RESCUE QUERY] %s", rq)
                        rescue_collected.extend(_search_fast_minimal(rq, top_k=8) or [])
                    if rescue_collected:"""
code = code.replace(c4_target, c4_repl)

# 5. call_llm_streaming routing
c5_target = """        if family_v2 != "fact_entity" and _is_safe_definition_fast_path_query(text):
            relevant_docs = _search_fast_definition_minimal(text)
        else:
            relevant_docs = _search_fast_minimal(text, top_k=top_k_req)"""
c5_repl = """        if family_v2 in {"definition_entity", "fact_entity", "list_entity"}:
            logger.info("[DIRECT ROUTE] family=%s", family_v2)
            logger.info("[PRIMARY SEARCH] used=_search_fast_minimal")
            relevant_docs = _search_fast_minimal(text, top_k=top_k_req)
        elif family_v2 != "fact_entity" and _is_safe_definition_fast_path_query(text):
            relevant_docs = _search_fast_definition_minimal(text)
        else:
            relevant_docs = _search_fast_minimal(text, top_k=top_k_req)"""
code = code.replace(c5_target, c5_repl)

# 6. call_llm_streaming FACT RESCUE
c6_target = """    if (not is_greeting) and (_classify_query_family_v2(text) == "fact_entity") and relevant_docs:
        try:
            fact_rescue_queries = _build_fact_rescue_queries(text, history)
            rescue_collected: list[dict] = []
            for retry_count, rq in enumerate((fact_rescue_queries or [])[:MAX_FACT_RETRIES], start=1):
                logger.info("[FACT RETRY] count=%s", retry_count)
                logger.info("[FACT RESCUE QUERY] %s", rq)
                rescue_collected.extend(_search_fast_minimal(rq, top_k=8) or [])
            if len(fact_rescue_queries or []) >= MAX_FACT_RETRIES:
                logger.info("[FACT RETRY] max_reached=True")
            if rescue_collected:"""
c6_repl = """    if (not is_greeting) and (_classify_query_family_v2(text) == "fact_entity"):
        if relevant_docs:
            logger.info("[FACT RESCUE USED]=False")
        else:
            try:
                fact_rescue_queries = _build_fact_rescue_queries(text, history)
                rescue_collected: list[dict] = []
                for rq in (fact_rescue_queries or [])[:1]:
                    if rq == text: continue
                    logger.info("[FACT RESCUE USED]=True")
                    logger.info("[FACT RETRY] count=1")
                    logger.info("[FACT RESCUE QUERY] %s", rq)
                    rescue_collected.extend(_search_fast_minimal(rq, top_k=8) or [])
                if rescue_collected:"""
code = code.replace(c6_target, c6_repl)

# Logging total calls - intercept _search_fast_minimal
c7_target = """def _search_fast_minimal(query_text: str, top_k: int) -> list[dict]:"""
c7_repl = """_RETR_CALLS = 0
def _search_fast_minimal(query_text: str, top_k: int) -> list[dict]:
    global _RETR_CALLS
    _RETR_CALLS += 1
    logger.info("[TOTAL RETRIEVAL CALLS]=%s", _RETR_CALLS)"""
code = code.replace(c7_target, c7_repl)

# Reset hooks
c8_target = """    greeting_patterns = ['hi', 'hello', 'hey', 'how are you', 'good morning', 'good afternoon', 'good evening', 'thanks', 'thank you']"""
c8_repl = """    global _RETR_CALLS
    _RETR_CALLS = 0
    greeting_patterns = ['hi', 'hello', 'hey', 'how are you', 'good morning', 'good afternoon', 'good evening', 'thanks', 'thank you']"""
code = code.replace(c8_target, c8_repl)

with open(file_path, "w", encoding="utf-8") as f:
    f.write(code)

print("Patch applied successfully.")
