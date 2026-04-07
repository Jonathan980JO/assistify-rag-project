from pathlib import Path
import chromadb

paths = [
    Path(r"g:\\Grad_Project\\assistify-rag-project-main\\backend\\chroma_db_v3"),
    Path(r"g:\\Grad_Project\\assistify-rag-project-main\\backend\\chroma_db"),
    Path(r"g:\\Grad_Project\\assistify-rag-project-main\\chroma_db"),
]

for p in paths:
    print(f"\nPATH: {p}")
    if not p.exists():
        print("  missing")
        continue
    try:
        client = chromadb.PersistentClient(path=str(p))
        cols = client.list_collections()
        print("  collections:", [c.name for c in cols])
        for c in cols:
            col = client.get_collection(c.name)
            cnt = col.count()
            print(f"   - {c.name}: count={cnt}")
            if cnt > 0:
                sample = col.get(limit=1, include=["documents", "metadatas"])
                docs = sample.get("documents") or []
                metas = sample.get("metadatas") or []
                if docs and docs[0]:
                    print("     doc preview:", str(docs[0])[:140].replace("\n", " "))
                if metas and metas[0]:
                    print("     meta keys:", list(metas[0].keys())[:10])
    except Exception as exc:
        print("  error:", exc)
