"""Diagnose Q2 (goals chunk raw text) and Q4 (perspectives cross-encoder scores)."""
import sys
sys.path.insert(0, '.')
import chromadb
from sentence_transformers import SentenceTransformer, CrossEncoder

model = SentenceTransformer('intfloat/multilingual-e5-base')
reranker = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')
client = chromadb.PersistentClient(path='backend/chroma_db_v3')
col = client.get_collection('support_docs_v3_latest')

print("=" * 60)
print("Q2 GOALS CHUNK RAW TEXT")
print("=" * 60)
emb = model.encode('query: What are the goals of psychology').tolist()
r = col.query(query_embeddings=[emb], n_results=5, include=['documents', 'metadatas', 'distances'])
for i, (doc, dist, meta) in enumerate(zip(r['documents'][0], r['distances'][0], r['metadatas'][0])):
    print(f"\n--- RANK{i+1} dist={dist:.3f} sec={meta.get('section','?')} ---")
    print(repr(doc[:800]))

print()
print("=" * 60)
print("Q4 PERSPECTIVES - TOP 10 WITH CROSS-ENCODER SCORES")
print("=" * 60)
q4 = "What are the main perspectives of psychology?"
emb4 = model.encode('query: ' + q4).tolist()
r4 = col.query(query_embeddings=[emb4], n_results=40, include=['documents', 'metadatas', 'distances'])
docs = r4['documents'][0]
metas = r4['metadatas'][0]
dists = r4['distances'][0]

pairs = [(q4, d) for d in docs]
scores = reranker.predict(pairs)
ranked = sorted(zip(scores, docs, metas, dists), key=lambda x: -x[0])

for i, (score, doc, meta, dist) in enumerate(ranked[:15]):
    sec = meta.get('section', '?')
    flag = "PASS" if score > 0 else "FAIL"
    print(f"[{flag}] rank={i+1} score={score:.3f} dist={dist:.3f} sec={sec}")
    print(f"  preview={doc[:120].encode('ascii','replace').decode('ascii')}")
