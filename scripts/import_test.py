import importlib
modules = [
    'backend.database',
    'backend.knowledge_base',
    'backend.assistify_rag_server',
    'Login_system.login_server',
    'backend.main_llm_server'
]
for m in modules:
    try:
        importlib.import_module(m)
        print(m, 'OK')
    except Exception as e:
        print(m, 'ERROR', e)
