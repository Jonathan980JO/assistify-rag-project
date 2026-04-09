from backend.assistify_rag_server import live_rag
docs = live_rag.search("List ONLY the main branches of philosophy mentioned in the document.", top_k=8, distance_threshold=9.0, return_dicts=True)
for i, d in enumerate(docs):
    print(i, d["metadata"]["page"], d["text"][:100].replace('\n', ' '))
