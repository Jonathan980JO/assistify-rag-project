from backend import assistify_rag_server as srv

queries = [
    "Who is Frederick Taylor?",
    "Disadvantages of scientific management",
    "Steps in planning process",
]

for q in queries:
    print("="*80)
    print("Q:", q)
    docs = srv.live_rag.search(q, top_k=10, distance_threshold=srv._distance_threshold_for_query(q), return_dicts=True)
    docs = srv._rerank_docs_for_query_intent(q, docs)
    print("retrieved:", len(docs))
    for i, d in enumerate(docs[:5], 1):
        m = d.get("metadata") or {}
        t = (d.get("page_content") or d.get("text") or d.get("content") or "")
        print(f"  raw[{i}] page={m.get('page')} preview={(t[:110]).replace(chr(10),' ')}")

    dd = []
    for d in docs:
        pc = d.get("page_content") or d.get("text") or d.get("content") or ""
        dd.append({"page_content": pc, "metadata": dict(d.get("metadata") or {})})

    before = (dd[0].get("metadata") or {}).get("page") if dd else None
    dd2 = srv._promote_entity_definition_top_doc(q, dd, top_k=6)
    after = (dd2[0].get("metadata") or {}).get("page") if dd2 else None
    print("before_page:", before, "after_page:", after)
    if dd2:
        print("final_top_preview:", (dd2[0].get("page_content") or "")[:180].replace("\n", " "))
