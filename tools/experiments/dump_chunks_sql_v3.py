import sqlite3
import os
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
db_paths = [_ROOT / "chroma_db_production", _ROOT / "chroma_db", _ROOT / "backend" / "chroma_db_v3"]

for base_path in db_paths:
    db_file = base_path / 'chroma.sqlite3'
    if not db_file.exists(): continue
    print(f"\nDB: {db_file}")
    conn = sqlite3.connect(str(db_file))
    cursor = conn.cursor()
    
    # In Chroma 0.4+, the text is often in a table related to the fulltext search.
    # The 'embedding_fulltext_search_content' or 'embedding_fulltext_search' table usually holds the documents.
    # Often 'embedding_fulltext_search_content' has 'id' and 'c0' where c0 is the text.
    
    search_terms = ['characteristics of management', 'planning process']
    
    # Try searching embedding_fulltext_search_content
    try:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='embedding_fulltext_search_content'")
        if cursor.fetchone():
            for term in search_terms:
                cursor.execute("SELECT id, c0 FROM embedding_fulltext_search_content WHERE c0 LIKE ?", (f'%{term}%',))
                rows = cursor.fetchall()
                if rows:
                    print(f"MATCH in embedding_fulltext_search_content for '{term}': {len(rows)} rows")
                    for r_id, content in rows:
                        # Try to find which collection this belongs to by looking at embeddings table
                        # r_id in fulltext usually matches id in embeddings table
                        cursor.execute("SELECT collection FROM segments JOIN embeddings ON segments.id = embeddings.segment_id WHERE embeddings.id = ?", (r_id,))
                        col_info = cursor.fetchone()
                        col_name = col_info[0] if col_info else "Unknown"
                        
                        # Get other metadata if possible
                        cursor.execute("SELECT key, string_value FROM embedding_metadata WHERE id = ?", (r_id,))
                        metas = cursor.fetchall()
                        meta_dict = {k: v for k, v in metas}
                        
                        print(f"--- Col: {col_name} ID: {r_id} chunk_index={meta_dict.get('chunk_index', '?')} ---")
                        print(content)
                        print("-" * 20)
    except Exception as e:
        print(f"Error searching fulltext: {e}")
        
    conn.close()
