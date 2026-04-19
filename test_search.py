import sys, os, json, re
os.chdir(r'g:\Grad_Project\assistify-rag-project-main')
sys.path.insert(0, '.')
try:
    from backend import assistify_rag_server as ars
    queries = ["characteristics of management", "steps in the planning process"]
    for q in queries:
        print("="*80)
        print("QUERY:", q)
        docs = ars.live_rag.search(q, top_k=5, distance_threshold=1.5, return_dicts=True, enable_rerank=True)
        for i,d in enumerate(docs):
            md = d.get('metadata') or {}
            print(f"--- rank {i} chunk_index={md.get('chunk_index')} source={md.get('source','')[:60]} score={d.get('similarity', d.get('score','?'))} ---")
            txt = d.get('page_content') or d.get('text') or ''
            rep = txt[:3000].replace('\n', '\\n\n')
            print(rep)
            print()
except Exception as e:
    import traceback
    traceback.print_exc()
