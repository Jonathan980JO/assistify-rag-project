"""Directly query ChromaDB to see what chunks contain 'goals of psychology'"""
import sys
sys.path.insert(0, r'G:\Grad_Project\assistify-rag-project-main')

from backend.database import KnowledgeBase

kb = KnowledgeBase()
kb.ensure_collection()

# Search for the goals query
results = kb.search("List the goals of psychology", top_k=5)

print("="*60)
print("Top 5 results for 'List the goals of psychology':")
print("="*60)

for i, doc in enumerate(results, 1):
    print(f"\n--- Result {i} ---")
    print(f"Source: {doc.get('metadata', {}).get('source', 'N/A')}")
    print(f"Chunk index: {doc.get('metadata', {}).get('chunk_index', 'N/A')}")
    print(f"Distance: {doc.get('distance', 'N/A')}")
    content = doc.get('page_content', doc.get('text', ''))
    print(f"Content (first 300 chars):")
    print(content[:300])
    print("...")
