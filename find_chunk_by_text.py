
import asyncio
import os
import sys

# Add backend to path
sys.path.append(os.getcwd())
sys.path.append(os.path.join(os.getcwd(), "backend"))

from backend.assistify_rag_server import live_rag

async def test():
    kb = live_rag
    kb.search("", top_k=1)
    col = kb.vs.collection
    
    target_sentence = "A more technical definition of management would include the six Ms"
    
    # Query Chroma for chunks containing this sentence
    results = col.query(
        query_texts=[target_sentence],
        n_results=5,
        include=["documents", "metadatas", "distances"]
    )
    
    print(f"Searching for chunk matching: '{target_sentence}'")
    for i, doc in enumerate(results["documents"][0]):
        dist = results["distances"][0][i]
        meta = results["metadatas"][0][i]
        print(f"--- Rank {i+1} Distance: {dist:.4f} ---")
        print(f"Chunk Index: {meta.get('chunk_index')} Page: {meta.get('page')}")
        print(f"Text Preview: {doc[:200]}...")

if __name__ == "__main__":
    asyncio.run(test())
