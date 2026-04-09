import sqlite3
import json

conn = sqlite3.connect('backend/chroma_db_v3/chroma.sqlite3')
rows = conn.execute("SELECT * FROM collections").fetchall()
for row in rows:
    config_json = row[-2]
    print(f"Name: {row[1]}")
    print(f"Config: {config_json}")
    if config_json:
        try:
            d = json.loads(config_json)
            if "_type" not in d:
                print(">>> MISSING _type in json!")
        except Exception as e:
            print(">>> Error parsing JSON", e)
    print("-" * 50)
