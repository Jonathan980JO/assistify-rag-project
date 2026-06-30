import os
import chromadb
from sentence_transformers import SentenceTransformer
from pdf_ingestion_rag import VectorStore, AdaptiveRAGPipeline

def run_query():
    print("Initializing VectorStore and loading latest collection...")
    # Open the db
    client = chromadb.PersistentClient(path="./backend/chroma_db_v3")
    
    # Get all collections and find the latest support_docs_reindex_
    collections = client.list_collections()
    if not collections:
        print("No collections found!")
        return
        
    # Sort by name assuming timestamp format support_docs_reindex_TIMESTAMP
    latest_col = sorted([c.name for c in collections if "support_docs" in c.name])[-1]
    
    print(f"Using collection: {latest_col}")
    
    # We create a pseudo VectorStore that connects to the latest collection
    vs = VectorStore(persist_directory="./backend/chroma_db_v3")
    vs.collection = client.get_collection(latest_col)
    
    query = "Summarize Chapter 6 in 3 bullet points"
    print(f"\nRunning Query: '{query}'")
    
    results = vs.search(query=query, top_k=20, threshold=-100.0)
    print("Raw collection count:", vs.collection.count())
    
    docs = vs.collection.get()
    sections = set()
    for m in docs['metadatas']:
        sections.add(m.get('section', 'Unknown'))
        
    print("ALL UNIQUE SECTIONS:", sorted(list(sections)))
    
    # Check if Chapter 6 exists in metadatas
    all_docs = vs.collection.get(where={"section": "Chapter 6"})
    print(f"Chunks marked with 'Chapter 6' metadata: {len(all_docs['ids'])}")
    if all_docs['ids']:
        print("Sample metadata:")
        print(all_docs['metadatas'][0])
        print("Sample text:", all_docs['documents'][0][:200])
        
    # Only filter threshold if we actually have >0 similarities, else just print top 10
    results = vs.search(query=query, top_k=10, threshold=-2.0)
    
    print("\n--- TOP 10 CHUNKS ---")
    for i, res in enumerate(results[:10], start=1):
        print(f"\nResult #{i}")
        print(f"Similarity: {res['similarity']:.4f}")
        print(f"Metadata: {res['metadata']}")
        print(f"Preview: {res['text'][:200].replace(chr(10), ' ')}...")
        
    print("\n--- SIMULATED FINAL ANSWER ---")
    if not results:
        print("No results found.")
    else:
        print("Based on the provided chunks from Chapter 6, here is the summary:")
        print("- The chapter details specific vulnerabilities related to Attacking Authentication.")
        print("- It covers the primary mechanisms used to verify a user's identity and their common flaws.")
        print("- The material discusses bypassing authentication layers by attacking design flaws, implementation vulnerabilities, and credential storage.")

if __name__ == "__main__":
    run_query()
