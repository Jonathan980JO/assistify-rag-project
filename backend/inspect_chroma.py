"""Inspect ChromaDB to find the goals of psychology chunk"""
import sys
sys.path.insert(0, r'G:\Grad_Project\assistify-rag-project-main')

import chromadb
from pathlib import Path

# Find the chroma database
db_paths = [
    Path(r'G:\Grad_Project\assistify-rag-project-main\chroma_db'),
    Path(r'G:\Grad_Project\assistify-rag-project-main\chroma_db_production'),
]

for db_path in db_paths:
    if db_path.exists():
        print(f"\n{'='*60}")
        print(f"Checking: {db_path}")
        print(f"{'='*60}")
        
        try:
            client = chromadb.PersistentClient(path=str(db_path))
            collections = client.list_collections()
            
            for coll in collections:
                print(f"\nCollection: {coll.name}")
                count = coll.count()
                print(f"  Document count: {count}")
                
                # Search for goals
                results = coll.query(
                    query_texts=["goals of psychology"],
                    n_results=5
                )
                
                print(f"\n  Top 5 results for 'goals of psychology':")
                for i, (doc_id, doc, dist) in enumerate(zip(
                    results['ids'][0], 
                    results['documents'][0],
                    results['distances'][0]
                ), 1):
                    print(f"\n  {i}. ID: {doc_id}, Distance: {dist:.4f}")
                    print(f"     Content (first 200 chars): {doc[:200]}")
                    
        except Exception as e:
            print(f"  Error: {e}")
