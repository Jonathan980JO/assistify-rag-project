#!/usr/bin/env python3
"""
Validate structure queries using the knowledge_base collection directly.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from knowledge_base import get_or_create_collection, embedder, _e5_query

print("=" * 80)
print("STRUCTURE QUERY VALIDATION - DIRECT COLLECTION QUERY")
print("=" * 80)

collection = get_or_create_collection()
print(f"\nUsing collection: {collection.name}")
print(f"Total chunks in collection: {collection.count()}\n")

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
    print(f"{'='*80}")
    print(f"Query: {query_text}")
    print(f"Category: {category}")
    print(f"{'='*80}")
    
    try:
        # Embed query
        query_embedding = embedder.encode(_e5_query(query_text), show_progress_bar=False).tolist()
        
        # Search
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=10,
            include=['documents', 'metadatas', 'distances']
        )
        
        if not results or not results.get('documents') or len(results['documents'][0]) == 0:
            print("❌ NO RESULTS RETURNED (empty retrieval)")
            continue
        
        documents = results['documents'][0]
        metadatas = results['metadatas'][0]
        distances = results['distances'][0]
        
        # Convert distances to similarity (1 - cosine_distance for cosine metric)
        similarities = [1 - d if d is not None else 0 for d in distances]
        
        print(f"\n✓ Retrieved {len(documents)} chunks:\n")
        
        for i, (doc, meta, sim) in enumerate(zip(documents, metadatas, similarities), 1):
            chapter = meta.get('chapter', 'N/A') if isinstance(meta, dict) else 'N/A'
            section = meta.get('section', 'N/A') if isinstance(meta, dict) else 'N/A'
            role = meta.get('chunk_role', 'unknown') if isinstance(meta, dict) else 'unknown'
            
            # Truncate long text
            text_preview = (doc[:150] + "...") if len(doc) > 150 else doc
            text_preview = text_preview.replace('\n', ' ')
            
            print(f"  [{i}] Sim: {sim:.3f} | Role: {role:15s} | Ch: {chapter:15s} | Sec: {section:20s}")
            print(f"      {text_preview}")
            print()
        
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()

print(f"{'='*80}")
print("✓ Validation complete!")
