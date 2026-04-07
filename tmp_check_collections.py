from backend import knowledge_base
from backend import assistify_rag_server

print('CHROMA PATH:', knowledge_base.CHROMA_DB_PATH)
print('Collections:')
for c in knowledge_base.client.list_collections():
    try:
        col = knowledge_base.client.get_collection(name=c.name)
        print('-', c.name, 'count=', col.count())
    except Exception as e:
        print('-', c.name, 'ERROR', e)

print('\nUploaded files (list_uploaded_files):')
files = knowledge_base.list_uploaded_files()
print('count ->', len(files))
for f in files[:50]:
    print(' *', f)

print('\nget_or_create_collection ->', getattr(knowledge_base.get_or_create_collection(), 'name', None))

lr = getattr(assistify_rag_server, 'live_rag', None)
if lr and getattr(lr, 'vs', None) and getattr(lr.vs, 'collection', None):
    try:
        c = lr.vs.collection
        print('\nLiveRAG collection object:', getattr(c,'name',None), 'count=', c.count())
    except Exception as e:
        print('\nLiveRAG collection object error:', e)
else:
    print('\nLiveRAG.vs.collection not set')
