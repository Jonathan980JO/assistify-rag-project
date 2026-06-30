import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "backend" / "chroma_db_v3" / "chroma.sqlite3"

TERMS = [
    "Meridian Financial Services",
    "Meridian Invest",
    "Everyday Checking",
    "FDIC",
]

conn = sqlite3.connect(str(DB))
cur = conn.cursor()

# Map segment/collection ids to collection names for context.
coll_name = {}
try:
    cur.execute("SELECT id, name FROM collections")
    for cid, name in cur.fetchall():
        coll_name[cid] = name
except Exception as e:
    print("(could not read collections table:", e, ")")

# Map segment -> collection
seg_to_coll = {}
try:
    cur.execute("SELECT id, collection FROM segments")
    for sid, cid in cur.fetchall():
        seg_to_coll[sid] = cid
except Exception as e:
    print("(could not read segments table:", e, ")")

# Raw stored document text lives in embedding_metadata under key 'chroma:document'.
for term in TERMS:
    print("=" * 100)
    print(f"SEARCH TERM: {term!r}")
    print("=" * 100)
    cur.execute(
        """
        SELECT e.segment_id, e.embedding_id, em.string_value
        FROM embedding_metadata em
        JOIN embeddings e ON e.id = em.id
        WHERE em.key = 'chroma:document'
          AND em.string_value LIKE ?
        """,
        (f"%{term}%",),
    )
    rows = cur.fetchall()
    if not rows:
        print("  (no matching chunks found)\n")
        continue
    for seg_id, emb_id, text in rows:
        cid = seg_to_coll.get(seg_id)
        cname = coll_name.get(cid, cid)
        print(f"\n--- collection={cname} chunk_id={emb_id} ---")
        print("[RAW CHUNK START]")
        print(repr(text))
        print("[RAW CHUNK END]")
    print()

conn.close()
