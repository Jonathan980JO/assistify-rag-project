
import asyncio
import os
import sys

# Add backend to path
sys.path.append(os.getcwd())
sys.path.append(os.path.join(os.getcwd(), "backend"))

from backend.assistify_rag_server import live_rag

async def test():
    kb = live_rag
    # Force lazy init
    kb.search("", top_k=1)
    # Access the collection directly
    col = kb.vs.collection
    
    # Get all chunks from Page 2
    results = col.get(
        where={"page": 2},
        include=["documents", "metadatas", "embeddings"]
    )
    
    ids = results.get("ids", [])
    if not ids:
        print("Page 2 NOT FOUND in collection!")
    else:
        print(f"Found {len(ids)} chunks on Page 2")
        for i, doc in enumerate(results["documents"]):
            print(f"--- Chunk ID: {ids[i]} ---")
            print(f"{doc[:500]}...")
            print(f"Metadata: {results['metadatas'][i]}")

if __name__ == "__main__":
    asyncio.run(test())
