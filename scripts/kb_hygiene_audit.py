import os
os.environ.setdefault('ANONYMIZED_TELEMETRY', 'False')
os.environ.setdefault('CHROMA_TELEMETRY_IMPL', 'none')
os.environ.setdefault('KMP_DUPLICATE_LIB_OK', 'TRUE')
os.environ.setdefault('RAG_USE_GPU', '0')

import sys
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import chromadb
from config import CHROMA_DB_PATH

DEMO_TERMS = [
    "sign up", "purchase history", "shipping", "returns", "warranty",
    "return policy", "refund", "order", "tracking",
]

client = chromadb.PersistentClient(path=str(CHROMA_DB_PATH))

target = sys.argv[1] if len(sys.argv) > 1 else "support_docs_v3_latest"
col = client.get_collection(name=target)
print(f"Collection: {target}  count={col.count()}")

data = col.get(include=["documents", "metadatas"])
ids = data.get("ids") or []
docs = data.get("documents") or []
metas = data.get("metadatas") or []

by_source = defaultdict(list)
for cid, doc, meta in zip(ids, docs, metas):
    md = meta if isinstance(meta, dict) else {}
    src = (
        md.get("source_name")
        or md.get("original_filename")
        or md.get("normalized_filename")
        or md.get("filename")
        or md.get("source")
        or "<none>"
    )
    by_source[str(src)].append((cid, doc, md))

print("\n=== Per-source chunk counts ===")
for src, items in sorted(by_source.items(), key=lambda kv: -len(kv[1])):
    print(f"  {len(items):3d}  {src}")

print("\n=== Chunks containing demo/e-commerce terms ===")
demo_ids = []
for cid, doc, meta in zip(ids, docs, metas):
    dl = str(doc or "").lower()
    hits = [t for t in DEMO_TERMS if t in dl]
    if hits:
        demo_ids.append(cid)
        md = meta if isinstance(meta, dict) else {}
        src = md.get("source_name") or md.get("filename") or md.get("source") or "<none>"
        print(f"\n--- id={cid} source={src!r} hits={hits} ---")
        print(repr(str(doc)[:400]))

print(f"\nTotal demo-term chunks: {len(demo_ids)}")

print("\n=== Distinct metadata source keys present ===")
allkeys = set()
for meta in metas:
    md = meta if isinstance(meta, dict) else {}
    for k in ("source_doc_id", "source_name", "normalized_filename", "filename", "source", "document_id", "base_doc_id"):
        v = md.get(k)
        if v:
            allkeys.add(f"{k}={v}")
for k in sorted(allkeys):
    print("  ", k)
