#!/usr/bin/env python3
"""
Validate structure queries with freshly reindexed metadata.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from pdf_ingestion_rag import VectorStore

print("=" * 80)
print("STRUCTURE QUERY VALIDATION - REINDEXED WITH FIXED ROLES")
print("=" * 80)

store = VectorStore()

# Structure queries that were failing before
queries = [
    ("List all chapters in the book", "structure"),
    ("What is Chapter 6 about?", "structure"),
    ("What topics are covered in Chapter 6?", "structure"),
    ("What are the sections in Chapter 7?", "structure"),
    ("What is discussed in Chapter 10?", "structure"),
    ("What is the difference between the manifest image and the scientific image?", "conceptual"),
]

for query_text, category in queries:
    print(f"\n{'='*80}")
    print(f"Query: {query_text}")
    print(f"Category: {category}")
    print(f"{'='*80}")
    
    try:
        results = store.search(query_text, top_k=10, threshold=0.3)
        
        if not results:
            print("❌ NO RESULTS RETURNED (empty retrieval)")
            continue
        
        print(f"\n✓ Retrieved {len(results)} chunks:\n")
        
        for i, (chunk_id, chunk_text, similarity, metadata) in enumerate(results, 1):
            chapter = metadata.get('chapter', 'N/A')
            section = metadata.get('section', 'N/A')
            role = metadata.get('chunk_role', 'unknown')
            
            # Truncate long text
            text_preview = (chunk_text[:150] + "...") if len(chunk_text) > 150 else chunk_text
            text_preview = text_preview.replace('\n', ' ')
            
            print(f"  [{i}] Similarity: {similarity:.3f} | Role: {role:15s} | Ch: {chapter:15s} | Sec: {section:20s}")
            print(f"      {text_preview}")
            print()
        
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()

print(f"\n{'='*80}")
print("✓ Validation complete!")
