#!/usr/bin/env python
"""Retrieve chunks by various metadata approaches"""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_ROOT))

import chromadb

db_path = _ROOT / "backend" / "chroma_db_v3"

if db_path.exists():
    client = chromadb.PersistentClient(path=str(db_path))
    collections = client.list_collections()
    
    for coll in collections:
        print(f"\nCollection: {coll.name}")
        print(f"Total in collection: {coll.count()}")
        
        # Try to get all and find goals of psychology
        try:
            all_results = coll.get(limit=500, include=["documents", "metadatas"])
            
            print(f"\nSearching for 'Goals of Psychology'...")
            
            for doc_text, metadata in zip(all_results['documents'], all_results['metadatas']):
                if 'Goals of Psychology' in doc_text or 'goals of psychology' in doc_text.lower():
                    chunk_idx = metadata.get('chunk_index', 'N/A')
                    print(f"\n{'='*80}")
                    print(f"FOUND: chunk_index={chunk_idx}")
                    print(f"{'='*80}")
                    print(f"Source: {metadata.get('source', 'N/A')}")
                    print(f"Page: {metadata.get('page', 'N/A')}")
                    print(f"Heading: {metadata.get('heading', 'N/A')}")
                    print(f"Section: {metadata.get('section', 'N/A')}")
                    print(f"\nFULL TEXT:\n{doc_text}\n")
                    
            # Also show chunks 36, 37, 38 if they exist
            for doc_text, metadata in zip(all_results['documents'], all_results['metadatas']):
                chunk_idx = metadata.get('chunk_index')
                if chunk_idx in [36, 37, 38]:
                    print(f"\n{'='*80}")
                    print(f"CHUNK {chunk_idx}")
                    print(f"{'='*80}")
                    print(f"Source: {metadata.get('source', 'N/A')}")
                    print(f"Page: {metadata.get('page', 'N/A')}")
                    print(f"Heading: {metadata.get('heading', 'N/A')}")
                    print(f"Section: {metadata.get('section', 'N/A')}")
                    print(f"\nFULL TEXT:\n{doc_text}\n")
                    
        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
