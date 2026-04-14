#!/usr/bin/env python
"""Extract full chunk content from ChromaDB for chunks 37, 84, and 38"""
import sys
sys.path.insert(0, '/root')

import chromadb
from pathlib import Path

# Initialize ChromaDB
chroma_path = r"g:\Grad_Project\assistify-rag-project-main\backend\chroma_db_v3"
client = chromadb.PersistentClient(path=chroma_path)

# Get the collection
collection_name = "support_docs_v3_latest"
try:
    collection = client.get_collection(name=collection_name)
    print(f"Collection: {collection_name}")
    print(f"Collection count: {collection.count()}")
except Exception as e:
    print(f"ERROR getting collection: {e}")
    sys.exit(1)

# Retrieve chunks 37, 84, 38
chunk_indices = [37, 84, 38]

for chunk_idx in chunk_indices:
    try:
        # Query by ID (chunk indices are typically used as IDs)
        result = collection.get(ids=[str(chunk_idx)], include=["documents", "metadatas"])
        
        if result and result['documents'] and len(result['documents']) > 0:
            doc = result['documents'][0]
            meta = result['metadatas'][0] if result['metadatas'] else {}
            
            print("\n" + "="*80)
            print(f"CHUNK INDEX: {chunk_idx}")
            print("="*80)
            print(f"PAGE: {meta.get('page', 'N/A')}")
            print(f"SOURCE: {meta.get('source', 'N/A')}")
            print("-"*80)
            print("FULL TEXT:")
            print("-"*80)
            print(doc)
            print("="*80)
        else:
            print(f"\nChunk {chunk_idx}: Not found by direct ID lookup")
            
    except Exception as e:
        print(f"Error retrieving chunk {chunk_idx}: {e}")

print("\nAttempting alternative retrieval method via chromadb query API...")
for chunk_idx in chunk_indices:
    try:
        # Try query with where filter
        result = collection.get(
            where={"chunk_index": {"$eq": chunk_idx}},
            include=["documents", "metadatas"]
        )
        if result and result['documents']:
            for i, doc in enumerate(result['documents']):
                meta = result['metadatas'][i] if result['metadatas'] else {}
                print(f"\nChunk {chunk_idx} (via where filter):")
                print(f"PAGE: {meta.get('page')}, SOURCE: {meta.get('source')}")
                print(f"TEXT: {doc[:200]}...")
    except:
        pass
