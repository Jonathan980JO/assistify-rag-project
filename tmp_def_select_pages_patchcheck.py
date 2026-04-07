import json
from pathlib import Path

from backend import assistify_rag_server as srv

query = "what is scientific management"

docs = srv.live_rag.search(
    query,
    top_k=10,
    distance_threshold=srv._distance_threshold_for_query(query),
    return_dicts=True,
)
docs = srv._rerank_docs_for_query_intent(query, docs)

prepared = []
for d in docs:
    pc = d.get("page_content") or d.get("text") or d.get("content") or ""
    prepared.append({"page_content": pc, "metadata": dict(d.get("metadata") or {})})

before_pages = [(x.get("metadata") or {}).get("page") for x in prepared[:3]]
after_docs = srv._promote_entity_definition_top_doc(query, prepared, top_k=10)
after_pages = [(x.get("metadata") or {}).get("page") for x in after_docs[:3]]

out = {
    "query": query,
    "before_selected_pages_top3": before_pages,
    "after_selected_pages_top3": after_pages,
}

Path("def_doc_select_pages_patchcheck.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=2),
    encoding="utf-8",
)
print(json.dumps(out, ensure_ascii=False, indent=2))
