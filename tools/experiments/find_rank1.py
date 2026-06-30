
import asyncio
import os
import sys

# Add backend to path
sys.path.append(os.getcwd())
sys.path.append(os.path.join(os.getcwd(), "backend"))

from backend.assistify_rag_server import live_rag

async def test():
    kb = live_rag
    # Access the collection directly
    # Lazy init manually
    if kb.vs is None:
        from backend.pdf_ingestion_rag import VectorStore
        kb.vs = VectorStore(persist_directory=kb._init_args.get("persist_directory"))
        
    col = kb.vs.collection
    
    target_sentence = "A more technical definition of management would include the six Ms"
    
    # Query Chroma
    results = col.query(
        query_texts=[target_sentence],
        n_results=2,
        include=["documents", "metadatas", "distances"]
    )
    
    for i, doc in enumerate(results["documents"][0]):
        dist = results["distances"][0][i]
        meta = results["metadatas"][0][i]
        print(f"RANK_{i+1} DIST={dist:.4f} CHUNK={meta.get('chunk_index')} PAGE={meta.get('page')}")
        print(f"TEXT: {doc[:300]}")

if __name__ == "__main__":
    asyncio.run(test())
