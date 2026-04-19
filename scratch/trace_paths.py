import sys, os
sys.path.insert(0, os.getcwd())
from backend import assistify_rag_server as srv
from backend.assistify_rag_server import live_rag

live_rag.search("", top_k=1)
col = live_rag.vs.collection

# get chunks 7..14
docs = []
for idx in [7,8,9,10,11,12,13,14]:
    r = col.get(where={"chunk_index": idx}, include=["documents","metadatas"])
    if r.get("ids"):
        docs.append({"page_content": r["documents"][0], "metadata": r["metadatas"][0], "text": r["documents"][0]})

q = "What are the characteristics of management?"

# Check which extractor produces the 8-item contamination
print("=== _extract_simple_list_from_docs ===")
print(repr(srv._extract_simple_list_from_docs(docs, query_text=q)))

print("\n=== _extract_list_route_answer ===")
print(repr(srv._extract_list_route_answer(q, docs)))

# extract_inline_concept_items lives inside _assess_list_coherence, not reachable directly. Test via _assess_list_coherence:
print("\n=== _assess_list_coherence (force fast deterministic, with chunk 9 alone as text) ===")
chunk9 = next((d['page_content'] for d in docs if d['metadata'].get('chunk_index')==9), '')
ls = srv._collect_local_window_support(docs)
ok, reason, shaped = srv._assess_list_coherence(q, chunk9, strict_fast=True, local_support=ls)
print("ok=", ok, "reason=", reason)
print("shaped=", repr(shaped))

# Also try running with route extractor docs
print("\n=== _assess_list_coherence on '- Management\\n- money\\n- machine...' ===")
prefab = "- Management\n- money\n- machine\n- material\n- methods\n- Planning\n- Staffing\n- Directing"
ok, reason, shaped = srv._assess_list_coherence(q, prefab, strict_fast=True, local_support=ls)
print("ok=", ok, "reason=", reason)
print("shaped=", repr(shaped))
