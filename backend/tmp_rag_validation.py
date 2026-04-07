import asyncio
from backend import assistify_rag_server as ars

QUERIES = [
    "What are the phases of the pre-scientific management period?",
    "What are the steps in the planning process?",
    "What are the advantages of scientific management?",
    "What are the disadvantages of scientific management?",
    "What are the five levels in Maslow’s hierarchy?",
]

async def run():
    for q in QUERIES:
        print("\n--- QUERY:", q)
        results = ars.live_rag.search(q, top_k=10, return_dicts=True)
        print("Retrieved:", len(results))
        if results:
            top = results[0]
            meta = top.get('metadata') or {}
            print("Top meta:", meta)
            preview = (top.get('text') or top.get('page_content') or '')[:400]
            print("Top preview:", preview.replace('\n',' ')[:300])
        lc = ars._count_list_like_items_in_docs(results)
        print("Detected list-like items across docs:", lc)

if __name__ == '__main__':
    asyncio.run(run())
