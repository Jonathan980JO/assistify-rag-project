#!/usr/bin/env python
"""Extract FULL chunk content from ChromaDB for chunks 37, 84, and 38"""
import sys
sys.path.insert(0, '/root')

import chromadb
import json

# Suppress telemetry error
import os
os.environ['ANONYMIZED_TELEMETRY'] = 'False'

# Initialize ChromaDB
chroma_path = r"g:\Grad_Project\assistify-rag-project-main\backend\chroma_db_v3"
client = chromadb.PersistentClient(path=chroma_path)

# Get the collection
collection_name = "support_docs_v3_latest"
collection = client.get_collection(name=collection_name)

# Retrieve chunks 37, 84, 38 with full text
chunk_indices = [37, 84, 38]

for chunk_idx in chunk_indices:
    try:
        # Query by where filter using chunk_index
        result = collection.get(
            where={"chunk_index": {"$eq": chunk_idx}},
            include=["documents", "metadatas"]
        )
        
        if result and result['documents'] and len(result['documents']) > 0:
            doc_text = result['documents'][0]
            meta = result['metadatas'][0] if result['metadatas'] else {}
            
            print("\n" + "="*100)
            print(f"CHUNK_INDEX: {chunk_idx}")
            print("="*100)
            print(f"PAGE: {meta.get('page', 'N/A')}")
            print(f"SOURCE: {meta.get('source', 'N/A')}")
            print("="*100)
            print("FULL TEXT:")
            print("-"*100)
            print(doc_text)
            print("-"*100)
            
    except Exception as e:
        print(f"Error retrieving chunk {chunk_idx}: {e}")
        import traceback
        traceback.print_exc()
