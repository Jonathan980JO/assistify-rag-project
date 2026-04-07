from backend.assistify_rag_server import live_rag

print('collection:', live_rag.vs.collection.name if live_rag.vs.collection else None)
if live_rag.vs.collection:
    print('count:', live_rag.vs.collection.count())

qs = [
    'What is psychology?',
    'What are the main goals of psychology?',
    'ما هو علم النفس؟',
]
for q in qs:
    print('\nQ:', q)
    rs = live_rag.search(q, top_k=3, distance_threshold=0.7, return_dicts=True)
    print('results:', len(rs))
    for i, r in enumerate(rs[:3], start=1):
        m = r.get('metadata', {})
        print(f"  {i}. section={m.get('section')} page={m.get('page')} score={r.get('score')} text={str(r.get('text',''))[:120].replace(chr(10),' ')}")
