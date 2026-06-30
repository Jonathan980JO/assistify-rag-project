"""Query ChromaDB directly for perspective-related chunks."""
import sys
sys.path.insert(0, ".")
import chromadb
from sentence_transformers import SentenceTransformer

DB_PATH = "backend/chroma_db_v3"
COL_NAME = "support_docs_v3_latest"
EMBED_MODEL = "intfloat/multilingual-e5-base"

print("Loading embedding model...")
model = SentenceTransformer(EMBED_MODEL)

client = chromadb.PersistentClient(path=DB_PATH)
col = client.get_collection(COL_NAME)
print(f"Collection: {col.name}, count: {col.count()}")

def embed(text):
    # e5 models use "query: " prefix for queries
    return model.encode("query: " + text).tolist()

# Query for perspectives
print("\n=== TOP 8 results for 'What are the main perspectives of psychology' ===")
emb = embed("What are the main perspectives of psychology")
results = col.query(
    query_embeddings=[emb],
    n_results=8,
    include=["documents", "metadatas", "distances"]
)
docs = results["documents"][0]
dists = results["distances"][0]
metas = results["metadatas"][0]
for i, (doc, dist, meta) in enumerate(zip(docs, dists, metas)):
    print(f"\n--- Rank {i+1} | dist={dist:.4f} | section={meta.get('section','?')} ---")
    print(doc[:400])

# Also search for "biological psychodynamic" specifically
print("\n\n=== TOP 5 for 'biological psychodynamic cognitive humanistic' ===")
emb2 = embed("biological psychodynamic cognitive behavioral humanistic perspectives")
results2 = col.query(
    query_embeddings=[emb2],
    n_results=5,
    include=["documents", "metadatas", "distances"]
)
for i, (doc, dist, meta) in enumerate(zip(results2["documents"][0], results2["distances"][0], results2["metadatas"][0])):
    print(f"\n--- Rank {i+1} | dist={dist:.4f} | section={meta.get('section','?')} ---")
    print(doc[:400])

# Brute-force search for perspective keywords
print("\n\n=== All chunks containing 'perspective' or 'biological' or 'psychodynamic' ===")
all_res = col.get(include=["documents", "metadatas"])
found = 0
for doc, meta in zip(all_res["documents"], all_res["metadatas"]):
    dl = doc.lower()
    if any(kw in dl for kw in ["perspective", "biological", "psychodynamic", "cognitive", "humanistic"]):
        print(f"\n[section={meta.get('section','?')}]")
        print(doc[:500])
        print("...")
        found += 1
print(f"\nTotal found: {found}")
