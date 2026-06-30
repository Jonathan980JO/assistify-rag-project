
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
    
    # Get ALL chunks (batch of 100)
    total = col.count()
    print(f"Total chunks: {total}")
    
    for start in range(0, total, 100):
        batch = col.get(
            limit=100,
            offset=start,
            include=["documents", "metadatas"]
        )
        for i, doc in enumerate(batch["documents"]):
            if "six ms" in doc.lower() or "6 ms" in doc.lower() or "6ms" in doc.lower():
                meta = batch["metadatas"][i]
                print(f"FOUND MATCH in Chunk {meta.get('chunk_index')} ID={batch['ids'][i]}")
                print(f"Text Preview: {doc[:300]}")
                print(f"Metadata: {meta}")

if __name__ == "__main__":
    asyncio.run(test())
