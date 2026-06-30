#!/usr/bin/env python3
"""RCA Sprint #2 — read-only Chroma collection introspection.

Enumerates collections, record counts, distinct source documents, and searches
for the suspicious leakage strings (Sign Up / Create Password / Purchase History
/ manufacturer's warranty). Pure sqlite read — no GPU, no server.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "backend" / "chroma_db_v3" / "chroma.sqlite3"


def main() -> None:
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    cur = con.cursor()

    print("=" * 100)
    print("COLLECTIONS")
    print("-" * 100)
    try:
        rows = cur.execute("SELECT id, name FROM collections ORDER BY name").fetchall()
    except sqlite3.OperationalError:
        rows = cur.execute("SELECT id, name FROM collections").fetchall()
    coll_names = {}
    for cid, name in rows:
        coll_names[cid] = name
        # count records per collection via segments -> embeddings
        try:
            n = cur.execute(
                "SELECT COUNT(*) FROM embeddings e "
                "JOIN segments s ON e.segment_id = s.id "
                "WHERE s.collection = ?",
                (cid,),
            ).fetchone()[0]
        except sqlite3.OperationalError:
            n = "?"
        print(f"  {name:40} id={cid} records={n}")

    print()
    print("=" * 100)
    print("DISTINCT SOURCES (embedding_metadata key in source/filename/file)")
    print("-" * 100)
    # Map embedding -> collection
    try:
        meta_rows = cur.execute(
            "SELECT em.key, em.string_value, s.collection "
            "FROM embedding_metadata em "
            "JOIN embeddings e ON em.id = e.id "
            "JOIN segments s ON e.segment_id = s.id "
            "WHERE em.key IN ('source','filename','file','source_file','display_source','document')"
        ).fetchall()
    except sqlite3.OperationalError as exc:
        print("  metadata join failed:", exc)
        meta_rows = []
    by_coll: dict = {}
    for key, val, coll in meta_rows:
        by_coll.setdefault(coll, {}).setdefault(key, {})
        by_coll[coll][key][val] = by_coll[coll][key].get(val, 0) + 1
    for coll, keys in by_coll.items():
        print(f"\n  collection={coll_names.get(coll, coll)} ({coll})")
        for key, vals in keys.items():
            for val, cnt in sorted(vals.items(), key=lambda x: -x[1]):
                print(f"      {key}={val!r}  x{cnt}")

    print()
    print("=" * 100)
    print("LEAKAGE STRING SEARCH (in stored chunk text)")
    print("-" * 100)
    needles = [
        "Sign Up", "Create Password", "Purchase History", "manufacturer's warranty",
        "warranty", "Add to Cart", "checkout", "Everyday Checking", "Meridian Invest",
    ]
    # chunk text is stored in embedding_metadata with key like 'chroma:document'
    try:
        doc_rows = cur.execute(
            "SELECT em.string_value, s.collection "
            "FROM embedding_metadata em "
            "JOIN embeddings e ON em.id = e.id "
            "JOIN segments s ON e.segment_id = s.id "
            "WHERE em.key = 'chroma:document'"
        ).fetchall()
    except sqlite3.OperationalError as exc:
        print("  document fetch failed:", exc)
        doc_rows = []
    print(f"  total stored documents scanned: {len(doc_rows)}")
    for needle in needles:
        hits = [(txt, coll) for (txt, coll) in doc_rows if txt and needle.lower() in txt.lower()]
        print(f"\n  needle={needle!r}: {len(hits)} hit(s)")
        for txt, coll in hits[:3]:
            snippet = " ".join(str(txt).split())[:200]
            print(f"      [{coll_names.get(coll, coll)}] {snippet}")

    print()
    print("=" * 100)
    print("FULL PER-CHUNK DUMP: support_docs_v3_latest (default tenant)")
    print("-" * 100)
    target = None
    for cid, name in coll_names.items():
        if name == "support_docs_v3_latest":
            target = cid
            break
    if target:
        ids = cur.execute(
            "SELECT e.id FROM embeddings e JOIN segments s ON e.segment_id=s.id WHERE s.collection=?",
            (target,),
        ).fetchall()
        for (eid,) in ids:
            meta = dict(
                cur.execute(
                    "SELECT key, string_value FROM embedding_metadata WHERE id=?", (eid,)
                ).fetchall()
            )
            doc = meta.get("chroma:document", "")
            src = meta.get("source") or meta.get("filename") or meta.get("file")
            ci = meta.get("chunk_index")
            keys = sorted(k for k in meta.keys() if k != "chroma:document")
            snippet = " ".join(str(doc).split())[:120]
            print(f"  id={eid} src={src!r} ci={ci} keys={keys}")
            print(f"     {snippet}")

    con.close()


if __name__ == "__main__":
    main()
