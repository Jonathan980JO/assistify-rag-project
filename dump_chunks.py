import sys, os
import chromadb
db_paths = [r'g:\Grad_Project\assistify-rag-project-main\chroma_db_production', r'g:\Grad_Project\assistify-rag-project-main\chroma_db']

for db_path in db_paths:
    if not os.path.exists(db_path):
        print(f"Skipping {db_path}, does not exist.")
        continue
    print(f"Checking DB: {db_path}")
    try:
        client = chromadb.PersistentClient(path=db_path)
        collections = client.list_collections()
        for col_obj in collections:
            # Handle different versions of list_collections (some return names, some return objects)
            col_name = col_obj if isinstance(col_obj, str) else col_obj.name
            print('COLLECTION:', col_name)
            c = client.get_collection(col_name)
            
            # Using get() with batching or just print info
            count = c.count()
            print(f"Count: {count}")
            if count == 0:
                continue
            
            # Retrieve in chunks to be safe
            all_data = c.get(include=['documents','metadatas'])
            docs = all_data.get('documents', [])
            metas = all_data.get('metadatas', [])
            
            for i, (d, m) in enumerate(zip(docs, metas)):
                if d is None: continue
                low = d.lower()
                if 'characteristics of management' in low or 'planning process' in low:
                    print(f'--- {col_name} chunk_index_meta={m.get("chunk_index") if m else "?"} i={i} ---')
                    print(d)
                    print()
    except Exception as e:
        import traceback
        print(f"Error accessing {db_path}: {e}")
        traceback.print_exc()
