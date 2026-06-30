#!/usr/bin/env python3
"""
RAW EVIDENCE COLLECTION SCRIPT
Goal: Find real chunks about "goals of psychology" and compare with /ws retrieval
"""

import json
import sys
import os
import asyncio
import websockets
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent / "backend"))

# Silence chroma telemetry
os.environ['ANONYMIZED_TELEMETRY'] = 'False'
os.environ['CHROMA_TELEMETRY_IMPL'] = 'none'

import chromadb
from sentence_transformers import SentenceTransformer

# ===== STEP 1: DIRECT CHROMA DATABASE QUERY =====
print("=" * 90)
print("STEP 1: SEARCHING INDEXED CHUNKS FOR 'GOALS OF PSYCHOLOGY'")
print("=" * 90)

# Connect to the production chroma database
chroma_path = Path(__file__).parent / "chroma_db"  # Try non-production first
if not (chroma_path / "chroma.sqlite3").exists():
    chroma_path = Path(__file__).parent / "chroma_db_production"

print(f"Using chroma database: {chroma_path}")
client = chromadb.PersistentClient(path=str(chroma_path))

# Get the collection name (same as server uses)
collection_name = os.environ.get("ASSISTIFY_COLLECTION_NAME", "").strip() or "support_docs_v3_production_latest"

try:
    collection = client.get_collection(name=collection_name)
    doc_count = collection.count()
    print(f"\nOK Connected to collection: '{collection_name}'")
    print(f"  Total documents in collection: {doc_count}")
except Exception as e:
    print(f"\nERROR Could not get collection '{collection_name}': {e}")
    print("  Available collections:")
    available_cols = [col.name for col in client.list_collections()]
    for col_name in available_cols:
        print(f"    - {col_name}")
    
    # Try adaptive_rag_collection if available
    if "adaptive_rag_collection" in available_cols:
        print(f"\nTrying 'adaptive_rag_collection' instead...")
        collection_name = "adaptive_rag_collection"
        collection = client.get_collection(name=collection_name)
        doc_count = collection.count()
        print(f"OK Connected to collection: '{collection_name}'")
        print(f"  Total documents in collection: {doc_count}")
    else:
        sys.exit(1)

# Load embedding model (same as server)
embedding_model = SentenceTransformer('intfloat/multilingual-e5-base')

# Search queries for "goals of psychology"
search_queries = [
    "goals of psychology",
    "aims of psychology",
    "objectives of psychology",
    "functions of psychology", 
    "purposes of psychology",
]

print(f"\n\nSearching for: {search_queries}\n")

all_candidates = {}

for query_text in search_queries:
    # Embed the query
    query_embedding = embedding_model.encode(f"query: {query_text}").tolist()
    
    # Search in collection
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=5,
        include=["metadatas", "documents", "distances"]
    )
    
    print(f"\n--- Query: '{query_text}' ---")
    if results and results['documents'] and len(results['documents'][0]) > 0:
        for i, (doc, meta, distance) in enumerate(zip(
            results['documents'][0],
            results['metadatas'][0],
            results['distances'][0]
        )):
            chunk_id = meta.get('chunk_index', 'UNKNOWN')
            page = meta.get('page', 'UNKNOWN')
            source = meta.get('source_file', meta.get('source', 'UNKNOWN'))
            
            print(f"\n  [{i+1}] chunk_index={chunk_id}, page={page}, source={source}")
            print(f"      distance={distance:.4f}")
            print(f"      TEXT: {doc[:200]}...")
            
            all_candidates[f"{query_text}_{i}"] = {
                'chunk_index': chunk_id,
                'page': page,
                'source': source,
                'distance': distance,
                'full_text': doc,
                'query': query_text,
            }
    else:
        print(f"  [NO RESULTS]")

# ===== STEP 2: LIVE /ws QUERY TEST =====
print("\n\n" + "=" * 90)
print("STEP 2: TESTING LIVE /ws ENDPOINT")
print("=" * 90)

async def test_ws_query():
    """Test the live /ws endpoint with target query"""
    target_query = "List the goals of psychology"
    
    print(f"\nTarget query: '{target_query}'")
    print("Connecting to ws://localhost:7000/ws...")
    
    retrieved_chunks = []
    
    try:
        async with websockets.connect("ws://localhost:7000/ws") as ws:
            print("OK Connected to WebSocket\n")
            
            # Send the query
            payload = {
                "type": "textQuery",
                "text": target_query
            }
            await ws.send(json.dumps(payload))
            print(f"OK Sent query: {json.dumps(payload)}\n")
            
            # Collect responses
            response_count = 0
            while response_count < 10:  # Collect up to 10 messages
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
                    response = json.loads(msg)
                    response_count += 1
                    
                    # Log the response type
                    msg_type = response.get('type', 'unknown')
                    print(f"[{response_count}] type={msg_type}")
                    
                    # Extract sources/chunks if present
                    if 'sources' in response:
                        print(f"     sources count: {len(response.get('sources', []))}")
                        for src_idx, src in enumerate(response.get('sources', [])):
                            print(f"       [{src_idx}] {json.dumps(src)[:100]}...")
                            retrieved_chunks.append(src)
                    
                    if 'retrievedChunks' in response:
                        print(f"     retrievedChunks: {len(response.get('retrievedChunks', []))}")
                        for chunk_idx, chunk in enumerate(response.get('retrievedChunks', [])):
                            print(f"       [{chunk_idx}] {json.dumps(chunk)[:100]}...")
                            retrieved_chunks.append(chunk)
                    
                    if response_count > 1:
                        print(f"\n{json.dumps(response)[:300]}...")
                    
                    # Stop on final response
                    if msg_type in ('aiResponseDone', 'error'):
                        break
                        
                except asyncio.TimeoutError:
                    print("  [TIMEOUT - no more messages]")
                    break
                except Exception as e:
                    print(f"  [ERROR receiving message: {e}]")
                    break
    
    except Exception as e:
        print(f"ERROR connecting to WebSocket: {e}")
        print("  Is the server running on port 7000?")
    
    return retrieved_chunks

# Run the async test
retrieved = asyncio.run(test_ws_query())

print("\n\n" + "=" * 90)
print("STEP 3: SIDE-BY-SIDE COMPARISON")
print("=" * 90)

print("\n=== BEST CANDIDATES FROM CHROMA (Raw Search) ===\n")
for key, candidate in sorted(all_candidates.items()):
    print(f"Query: {candidate['query']}")
    print(f"  chunk_index={candidate['chunk_index']}")
    print(f"  page={candidate['page']}")
    print(f"  source={candidate['source']}")
    print(f"  similarity_distance={candidate['distance']:.4f}")
    print(f"  FULL TEXT:\n{candidate['full_text']}\n")
    print("-" * 90)

print("\n\n=== CURRENT /ws RETRIEVAL ===\n")
print(f"Number of retrieved chunks from /ws: {len(retrieved)}\n")
for i, chunk in enumerate(retrieved):
    print(f"[{i}] {json.dumps(chunk)[:500]}...\n")

print("\n\n=== FUNCTION CODE EXTRACTION ===\n")
print("Extracting required function code...")
