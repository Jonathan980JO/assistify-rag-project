import requests
LOGIN_HOST = "http://127.0.0.1:7001"
RAG_HOST = "http://127.0.0.1:7000"

s = requests.Session()
# login
r = s.post(f"{LOGIN_HOST}/login", data={'username':'admin','password':'admin'}, allow_redirects=False, timeout=20)
print('login', r.status_code)
# Set RAG doc-mode to multi and include the uploaded filename
payload = {'mode': 'multi', 'active_sources': ['a016c7c9_Principles_of_Management.pdf']}
resp = s.post(f"{RAG_HOST}/rag/doc-mode", json=payload, timeout=20)
print('set doc-mode status', resp.status_code)
print(resp.json())
