import sys
import os
from backend.assistify_rag_server import live_rag
import backend.assistify_rag_server as srv

query = "What are the characteristics of management?"
top_k = 12

print("--- Searching live_rag ---")
retrieved_docs = live_rag.search(query, top_k=top_k)

# Handling string results from search
formatted_docs = []
for i, doc in enumerate(retrieved_docs):
    if isinstance(doc, str):
        print(f"[{i}] String: {doc[:80]}")
        formatted_docs.append({"page_content": doc, "text": doc})
    else:
        chunk_idx = doc.get("chunk_index", "N/A")
        text = doc.get("page_content", "") or doc.get("text", "")
        snippet = text.replace('\n', ' ')[:80]
        print(f"[{i}] Chunk {chunk_idx}: {snippet}")
        formatted_docs.append(doc)

print("\n--- _extract_list_route_answer ---")
try:
    res1 = srv._extract_list_route_answer(query, formatted_docs)
    print(res1)
except Exception as e:
    import traceback
    traceback.print_exc()

print("\n--- _extract_simple_list_from_docs ---")
try:
    res2 = srv._extract_simple_list_from_docs(formatted_docs, query_text=query)
    print(res2)
except Exception as e:
    import traceback
    traceback.print_exc()

print("\n--- _extract_list_from_context ---")
try:
    context = "\n\n".join(d.get("page_content","") or d.get("text","") for d in formatted_docs)
    res3 = srv._extract_list_from_context(query, context)
    print(res3)
except Exception as e:
    import traceback
    traceback.print_exc()
