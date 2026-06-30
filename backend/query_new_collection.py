import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from chromadb import PersistentClient

CHROMA_DIR = Path(__file__).resolve().parents[1] / 'backend' / 'chroma_db_reindex'
COL_NAME = None
# Try to find the reindex collection
client = PersistentClient(path=str(CHROMA_DIR))
cols = client.list_collections()
for c in cols:
    if c.name.startswith('support_docs_reindex'):
        COL_NAME = c.name
        break
if not COL_NAME:
    print('No reindex collection found')
    sys.exit(1)
collection = client.get_collection(COL_NAME)
q = "Summarize Chapter 6 in 3 bullet points"
res = collection.query(query_texts=[q], n_results=10, include=["documents","metadatas","distances"]) 
docs = res.get('documents',[[]])[0]
metas = res.get('metadatas',[[]])[0]
dists = res.get('distances',[[]])[0]
for i,(d,m,dist) in enumerate(zip(docs,metas,dists), start=1):
    sim = 1.0 - dist if dist is not None else None
    print(f"--- RANK {i} | similarity: {sim}")
    print('metadata:', json.dumps(m, ensure_ascii=False))
    print('text:\n', d[:3000])
