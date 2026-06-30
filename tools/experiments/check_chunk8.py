
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
    print(f"Collection count: {col.count()}")
    
    # Get chunk 8 from the PDF
    results = col.get(
        where={"chunk_index": 8},
        include=["documents", "metadatas", "embeddings"]
    )
    
    ids = results.get("ids", [])
    if not ids:
        print("Chunk 8 NOT FOUND in collection!")
    else:
        for i, doc in enumerate(results["documents"]):
            print(f"Found Chunk 8 (ID={ids[i]}): {doc[:100]}...")
            print(f"Metadata: {results['metadatas'][i]}")

if __name__ == "__main__":
    asyncio.run(test())
