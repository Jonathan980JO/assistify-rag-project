from backend import assistify_rag_server as srv

q = "what is scientific management"
docs = srv._search_fast_definition_minimal(q)
print("search_docs_pages:",[ (d.get("metadata") or {}).get("page") for d in docs])

dd = []
for d in docs:
    pc = d.get("page_content") or d.get("text") or d.get("content") or ""
    dd.append({"page_content": pc, "text": pc, "content": pc, "metadata": dict(d.get("metadata") or {})})

promoted = srv._promote_entity_definition_top_doc(q, dd, top_k=10)
print("promoted_pages:",[ (d.get("metadata") or {}).get("page") for d in promoted[:5]])

res = srv._shared_rag_final_answer_decision(q, promoted, llm_text=None)
print("decision:", res)
