import sqlite3
import os

db_paths = [r'g:\Grad_Project\assistify-rag-project-main\chroma_db_production', r'g:\Grad_Project\assistify-rag-project-main\chroma_db']

for base_path in db_paths:
    db_file = os.path.join(base_path, 'chroma.sqlite3')
    if not os.path.exists(db_file): continue
    print(f"\nDB: {db_file}")
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    
    # Check tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [t[0] for t in cursor.fetchall()]
    print(f"Tables: {tables}")
    
    # Try to find content
    # In newer Chroma (0.4+), text is in 'embedding_fulltext' or 'embeddings' might link to 'embedding_metadata'
    # Actually, often it's 'embedding_fulltext'
    # Let's check schemas
    for table in tables:
        cursor.execute(f"PRAGMA table_info({table})")
        cols = [c[1] for c in cursor.fetchall()]
        print(f"Table {table} columns: {cols}")
        
    # Search logic based on likely schema
    # Usually: embeddings table has id, collection_id
    # embedding_fulltext has id, string_value? Or embedding_metadata?
    # Let's just try searching all tables for the strings if they have string columns
    
    search_terms = ['characteristics of management', 'planning process']
    
    for table in tables:
        cursor.execute(f"PRAGMA table_info({table})")
        text_cols = [c[1] for c in cursor.fetchall() if c[2].lower() in ('text', 'string', 'varchar')]
        if not text_cols: continue
        
        for col in text_cols:
            for term in search_terms:
                query = f"SELECT * FROM {table} WHERE {col} LIKE ?"
                cursor.execute(query, (f'%{term}%',))
                results = cursor.fetchall()
                if results:
                    print(f"MATCH in {table}.{col} for '{term}': {len(results)} rows")
                    for row in results:
                        print(row)
                        print("-" * 40)
    
    conn.close()
