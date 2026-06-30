import asyncio
import os
import sys

sys.path.append(os.getcwd())
sys.path.append(os.path.join(os.getcwd(), "backend"))

from backend.assistify_rag_server import live_rag

async def inspect():
    kb = live_rag
    # Force lazy init
    kb.search("", top_k=1)
    col = kb.vs.collection
    
    for idx in [8, 9, 10]:
        print(f"\n--- Chunk {idx} ---")
        results = col.get(
            where={"chunk_index": idx},
            include=["documents", "metadatas"]
        )
        ids = results.get("ids", [])
        if not ids:
            print("NOT FOUND")
        else:
            doc = results["documents"][0]
            meta = results["metadatas"][0]
            print(f"Metadata: {meta}")
            print("Text:")
            print(doc)

if __name__ == '__main__':
    asyncio.run(inspect())
