import asyncio
import time
import sys
import os
import logging

logging.basicConfig(level=logging.INFO, format="%(message)s")

sys.path.append(os.path.abspath('..'))
import assistify_rag_server as ars

QUERIES = [
    "What is psychology?",
    "Who established the first psychological laboratory and in what year?",
    "List the six goals of psychology.",
    "What is blockchain?"
]

async def run():
    for q in QUERIES:
        print("\n" + "="*80)
        print("QUERY:", q)
        print("="*80)
        
        # Reset total calls
        ars._RETR_CALLS = 0
        
        user_stub = {"username": "test_user", "role": "admin"}
        
        # Call RAG pipeline
        response, docs = await ars.call_llm_with_rag(
            text=q,
            user=user_stub,
            connection_id="test_conn"
        )
        
        print("\n[RESULT]")
        if isinstance(response, str):
            print("Response length:", len(response))
        else:
            print("Response:", str(response)[:100])
        print("Total Retrieval Calls Tracked:", ars._RETR_CALLS)
        print("Docs retrieved:", len(docs) if docs else 0)

if __name__ == '__main__':
    asyncio.run(run())
