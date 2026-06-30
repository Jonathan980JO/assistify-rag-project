
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
    res = col.get(ids=['upload_Principles_of_Management.pdf_chunk_6'], include=['documents'])
    print(res['documents'][0])

if __name__ == "__main__":
    asyncio.run(test())
