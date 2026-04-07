import re
from backend import assistify_rag_server as srv

q = "what is scientific management"
docs = srv.live_rag.search(q, top_k=20, distance_threshold=srv._distance_threshold_for_query(q), return_dicts=True)
docs = srv._rerank_docs_for_query_intent(q, docs)

for i, d in enumerate(docs[:20], 1):
    m = d.get("metadata") or {}
    txt = d.get("page_content") or d.get("text") or ""
    sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", txt) if s.strip()]
    hits = [s for s in sents if re.search(r"\bscientific\s+management\b", s, flags=re.IGNORECASE)]
    if not hits:
        continue
    print("="*80)
    print(f"doc[{i}] page={m.get('page')} chunk={m.get('chunk_index')}")
    for h in hits[:5]:
        has_verb = bool(re.search(r"\b(is|refers to|means|defined as|was|known as)\b", h, flags=re.IGNORECASE))
        print(f"verb={has_verb} | {h[:220]}")
