#!/usr/bin/env python3
"""Extract full chunk texts from the active knowledge base collection."""
import chromadb
from pathlib import Path
from sentence_transformers import SentenceTransformer

print("=== EXTRACTING CHUNK TEXTS FROM CHROMA ===\n")

try:
    # Use the active database path from the startup logs
    db_path = Path(r'G:\Grad_Project\assistify-rag-project-main\backend\chroma_db_v3')
    
    if not db_path.exists():
        print(f"Error: {db_path} not found")
        exit(1)
    
    # Initialize the embedding model (same as server uses - 768 dimensions)
    embedder = SentenceTransformer('intfloat/multilingual-e5-base')
    
    def _e5_passage(text: str) -> str:
        cleaned = " ".join((text or "").split())
        return f"passage: {cleaned}" if cleaned else "passage:"
    
    def _e5_query(text: str) -> str:
        cleaned = " ".join((text or "").split())
        return f"query: {cleaned}" if cleaned else "query:"
    
    # Connect to ChromaDB
    client = chromadb.PersistentClient(path=str(db_path))
    
    # Get the active collection (support_docs_v3_latest)
    collection = client.get_collection(name="support_docs_v3_latest")
    print(f"[INFO] Connected to collection: support_docs_v3_latest")
    print(f"[INFO] Total chunks in collection: {collection.count()}\n")
    
    # The top 3 chunks from the log are: 7, 37, 84
    top_chunks = [7, 37, 84]
    
    print("=== TOP 3 RETRIEVED CHUNKS ===")
    
    # First, let's get all chunks and find the ones by index
    all_chunks = collection.get(include=['documents', 'metadatas'])
    
    chunk_map = {}
    for chunk_id, doc, meta in zip(all_chunks['ids'], all_chunks['documents'], all_chunks['metadatas']):
        # The chunk_id is usually like "chunk_0", "chunk_1", etc
        if chunk_id.startswith('chunk_'):
            idx = int(chunk_id.replace('chunk_', ''))
            chunk_map[idx] = (doc, meta)
    
    print(f"[INFO] Found {len(chunk_map)} chunks with valid IDs\n")
    
    for chunk_idx in top_chunks:
        if chunk_idx in chunk_map:
            doc, meta = chunk_map[chunk_idx]
            print(f"\n[Chunk {chunk_idx}]")
            print(f"  Page: {meta.get('page', 'N/A')}")
            print(f"  Source: {meta.get('source', 'N/A')}")
            print(f"  Full Text:\n{doc}\n")
        else:
            print(f"\n[Chunk {chunk_idx}] - NOT FOUND in collection")
    
    # Now search for best-match chunks about goals/aims/objectives of psychology
    print("\n\n=== SEARCHING FOR BEST CANDIDATE CHUNKS ===")
    
    search_queries = [
        "goals of psychology",
        "aims of psychology", 
        "objectives of psychology",
        "purposes of psychology",
    ]
    
    found_chunks = {}
    
    for query in search_queries:
        print(f"\nSearching for: '{query}'")
        try:
            # Use the e5 formatted query
            query_embedding = embedder.encode([_e5_query(query)])[0]
            
            results = collection.query(
                query_embeddings=[query_embedding.tolist()],
                n_results=5,
                include=['documents', 'metadatas', 'distances']
            )
            
            if results and results['ids'] and len(results['ids']) > 0:
                for i, (chunk_id, doc, meta, distance) in enumerate(zip(
                    results['ids'][0],
                    results['documents'][0],
                    results['metadatas'][0],
                    results['distances'][0]
                )):
                    chunk_num = chunk_id.replace('chunk_', '')
                    if chunk_num not in found_chunks:
                        found_chunks[chunk_num] = {
                            'document': doc,
                            'metadata': meta,
                            'distance': distance
                        }
                    print(f"  [{i+1}] chunk_index={chunk_num}, distance={distance:.4f}, page={meta.get('page', 'N/A')}")
                    if i == 0:  # Print first result text
                        print(f"       First 200 chars: {doc[:200]}...")
        except Exception as e:
            print(f"Error searching for '{query}': {e}")
            import traceback
            traceback.print_exc()
    
    # Print the best candidates
    if found_chunks:
        print("\n\n=== BEST CANDIDATE CHUNK(S) IN ACTIVE COLLECTION ===")
        # Sort by distance (lower is better)
        sorted_chunks = sorted(found_chunks.items(), key=lambda x: x[1]['distance'])
        
        for chunk_num, info in sorted_chunks[:5]:  # Top 5
            print(f"\n[Chunk {chunk_num}]")
            print(f"  Distance: {info['distance']:.4f}")
            print(f"  Page: {info['metadata'].get('page', 'N/A')}")
            print(f"  Source: {info['metadata'].get('source', 'N/A')}")
            print(f"  Full Text:\n{info['document']}\n")
            print("  " + "="*80)
    
except Exception as e:
    print(f"Fatal error: {e}")
    import traceback
    traceback.print_exc()


