import sys
sys.path.insert(0, r"g:\Grad_Project\assistify-rag-project-main")
from backend.knowledge_base import get_or_create_collection, search_documents
col = get_or_create_collection()
if not col:
    print('NO COLLECTION')
    sys.exit(0)
try:
    res = col.query(query_texts=["Chapter 6"], n_results=10, include=["documents","metadatas","distances"]) 
    docs = res.get('documents', [[]])[0]
    metas = res.get('metadatas', [[]])[0]
    dists = res.get('distances', [[]])[0]
    for i,(d,m,dist) in enumerate(zip(docs, metas, dists), start=1):
        sim = 1.0 - dist if dist is not None else None
        print('---', i, 'sim=', sim)
        print('META:', m)
        print(d[:800].replace('\n',' '))
except Exception as e:
    print('QUERY ERROR', e)
    try:
        hits = search_documents('Chapter 6', top_k=10)
        print('fallback hits:', len(hits))
        for i,h in enumerate(hits, start=1):
            print('HIT', i, h[:400].replace('\n',' '))
    except Exception as e2:
        print('fallback error', e2)


if __name__ == '__main__':
    pass
