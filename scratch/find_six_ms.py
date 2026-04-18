import os
import sys
import chromadb
from chromadb.config import Settings

# Correcting path based on log check
path = "g:/Grad_Project/assistify-rag-project-main/backend/chroma_db_v3"
client = chromadb.PersistentClient(path=path)

try:
    cols = client.list_collections()
    print("Available collections:", [c.name for c in cols])
    
    collection = client.get_collection("support_docs_v3_latest")
    
    # Try searching for the text directly
    res = collection.get(
        where_document={"$contains": "six Ms"},
        include=["documents", "metadatas"]
    )
    
    print(f"Found {len(res['documents'])} chunks with 'six Ms' in text")
    for i in range(len(res['documents'])):
        print(f"--- Chunk index {res['metadatas'][i].get('chunk_index')} | Page {res['metadatas'][i].get('page')} ---")
        print(res['documents'][i][:400])
        
    # Also search for 'money' and 'machines'
    res2 = collection.get(
        where_document={"$contains": "Money, Materials"},
        include=["documents", "metadatas"]
    )
    print(f"\nFound {len(res2['documents'])} chunks with 'Money, Materials' in text")
    for i in range(len(res2['documents'])):
        print(f"--- Chunk index {res2['metadatas'][i].get('chunk_index')} | Page {res2['metadatas'][i].get('page')} ---")
        print(res2['documents'][i][:400])

except Exception as e:
    print(f"Error: {e}")
