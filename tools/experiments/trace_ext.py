import sys
import os
import json

# Add project root to sys.path
sys.path.append(os.getcwd())

from backend.assistify_rag_server import live_rag
import backend.assistify_rag_server as srv

# Lazy-init the RAG server
live_rag.search("", top_k=1)

# Get collection
collection = live_rag.vs.collection

# Fetch chunks 7, 8, 9, 10, 11
results = collection.get(
    where={"chunk_index": {"$in": [7, 8, 9, 10, 11]}}
)

# Build list of doc dicts
docs = []
for i in range(len(results['ids'])):
    docs.append({
        "page_content": results['documents'][i],
        "metadata": results['metadatas'][i]
    })

# Ensure they are sorted by chunk_index for consistency
docs.sort(key=lambda x: x['metadata']['chunk_index'])

query = "What are the characteristics of management?"

print("--- _extract_simple_list_from_docs ---")
try:
    res1 = srv._extract_simple_list_from_docs(docs, query_text=query)
    print(res1)
except Exception as e:
    print(f"Error: {e}")

print("\n--- _extract_list_from_context ---")
try:
    context = "\n\n".join(d["page_content"] for d in docs)
    res2 = srv._extract_list_from_context(query, context, max_candidate_blocks=4)
    print(res2)
except Exception as e:
    print(f"Error: {e}")

print("\n--- _extract_structured_list_from_context ---")
try:
    contents = [d["page_content"] for d in docs]
    res3 = srv._extract_structured_list_from_context(contents, query_text=query)
    print(res3)
except Exception as e:
    print(f"Error: {e}")

print("\n--- _extract_list_route_answer ---")
try:
    res4 = srv._extract_list_route_answer(query, docs)
    print(res4)
except Exception as e:
    print(f"Error: {e}")
