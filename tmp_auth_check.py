import requests
s=requests.Session()
for host in ['http://127.0.0.1:7000','http://127.0.0.1:7001']:
    r=s.post(f'{host}/login', data={'username':'admin','password':'admin'}, allow_redirects=False, timeout=20)
    print(host, r.status_code, r.headers.get('set-cookie'))
    r2=s.get('http://127.0.0.1:7000/rag/retrieve-debug', params={'query':'Who is Frederick Taylor?','top_k':5}, timeout=30)
    print('  retrieve', r2.status_code, r2.text[:120])
