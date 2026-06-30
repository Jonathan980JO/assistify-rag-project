
import sys
import os
import asyncio
from backend.assistify_rag_server import LiveRAGManager

def verify_six_ms():
    print("--- STANDALONE RAG VERIFICATION ---")
    # Initialize the manager
    manager = LiveRAGManager()
    
    # Simulate a query
    query_text = "What are the six Ms of management?"
    print(f"Query: {query_text}")
    
    # search() is NOT async in LiveRAGManager
    docs = manager.search(query_text, top_k=10, return_dicts=True)
    
    print(f"\nRetrieved {len(docs)} chunks.")
    target_found = False
    for i, doc in enumerate(docs):
        meta = doc.get('metadata') or {}
        page = meta.get('page')
        chunk = meta.get('chunk_index')
        score = doc.get('score', 0)
        text_content = str(doc.get('page_content') or doc.get('text') or "")
        text_preview = text_content[:200]
        
        print(f"\n[Doc {i}] Score: {score:.4f} | Page: {page} | Chunk: {chunk}")
        print(f"Text: {text_preview}...")
        
        # Check if this is the target chunk (Chunk 6 in Page 8 roughly)
        if any(k in text_content.lower() for k in ["six ms", "6 ms", "6ms"]):
             print(">>> TARGET LIST FOUND!")
             target_found = True
             if "classification" in text_content.lower() and "fayol" in text_content.lower():
                 print("!!! WARNING: Fayol distraction present in this chunk.")
                 # Check if my cleaning regexes applied (they should have)
                 if "ISBN" in text_content or "http" in text_content:
                     print("!!! ERROR: Cleaning regexes NOT applied.")
                 else:
                     print(">>> SUCCESS: Noise cleaned.")

    if target_found:
        print("\nOVERALL STATUS: SUCCESS")
    else:
        print("\nOVERALL STATUS: FAILURE (Target not in top 10)")

if __name__ == "__main__":
    verify_six_ms()
