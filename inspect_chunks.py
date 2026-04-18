
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
    
    # Get chunks 6, 7, 8, 9
    results = col.get(
        ids=[f"upload_Principles_of_Management.pdf_chunk_{i}" for i in range(5, 12)],
        include=["documents", "metadatas"]
    )
    
    ids = results.get("ids", [])
    for i, doc in enumerate(results["documents"]):
        print(f"--- {ids[i]} ---")
        print(doc)
        print(f"Metadata: {results['metadatas'][i]}")

if __name__ == "__main__":
    asyncio.run(test())
