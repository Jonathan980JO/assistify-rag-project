import sys
import os

# Add project root to sys.path
sys.path.append(os.getcwd())

from backend.assistify_rag_server import live_rag

# Lazy-init
live_rag.search("", top_k=1)
collection = live_rag.vs.collection

# Fetch chunks 7, 8, 9, 10, 11
results = collection.get(
    where={"chunk_index": {"$in": [7, 8, 9, 10, 11]}}
)

for i in range(len(results['ids'])):
    print(f"--- Chunk {results['metadatas'][i]['chunk_index']} ---")
    print(results['documents'][i])
    print("\n")
