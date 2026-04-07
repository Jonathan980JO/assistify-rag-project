import sqlite3
import json

conn = sqlite3.connect('backend/chroma_db_v3/chroma.sqlite3')
rows = conn.execute("SELECT * FROM collections").fetchall()

to_delete = []
for row in rows:
    cid = row[0]
    # find the {} in the row and replace
    is_corrupt = False
    for item in row:
        if isinstance(item, str) and item == "{}":
            is_corrupt = True
    if is_corrupt:
        to_delete.append(cid)

for cid in to_delete:
    print(f"Deleting corrupt collection ID {cid}")
    conn.execute("DELETE FROM segment_metadata WHERE segment_id IN (SELECT id FROM segments WHERE collection = ?)", (cid,))
    conn.execute("DELETE FROM segments WHERE collection = ?", (cid,))
    conn.execute("DELETE FROM collections WHERE id = ?", (cid,))

conn.commit()
conn.close()
print("Database cleaned.")
