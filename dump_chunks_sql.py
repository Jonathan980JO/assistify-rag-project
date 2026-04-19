import sys, os
import sqlite3

db_paths = [r'g:\Grad_Project\assistify-rag-project-main\chroma_db_production', r'g:\Grad_Project\assistify-rag-project-main\chroma_db']

for base_path in db_paths:
    db_file = os.path.join(base_path, 'chroma.sqlite3')
    if not os.path.exists(db_file):
        print(f"Skipping {db_file}, does not exist.")
        continue
    
    print(f"Checking SQLite DB: {db_file}")
    try:
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()
        
        # Get collections
        cursor.execute("SELECT id, name FROM collections")
        collections = cursor.fetchall()
        
        for col_id, col_name in collections:
            print(f"COLLECTION: {col_name} (ID: {col_id})")
            
            # Query documents and metadata
            # Schema usually has embedding_fulltext or similar, but let's try embeddings table
            # In newer Chroma, it's often in 'embeddings' table linked to 'collections'
            try:
                # Schema might vary. Try common columns.
                cursor.execute("SELECT document, metadata FROM embeddings WHERE collection_id = ?", (col_id,))
                rows = cursor.fetchall()
                print(f"Count: {len(rows)}")
                
                for i, (doc, meta_json) in enumerate(rows):
                    if doc is None: continue
                    low = doc.lower()
                    if 'characteristics of management' in low or 'planning process' in low:
                        # meta_json is a string or blob
                        print(f"--- {col_name} i={i} ---")
                        print(doc)
                        print(f"Metadata: {meta_json}")
                        print()
            except Exception as e:
                print(f"Error querying embeddings for {col_name}: {e}")
        
        conn.close()
    except Exception as e:
        print(f"Error accessing {db_file}: {e}")
