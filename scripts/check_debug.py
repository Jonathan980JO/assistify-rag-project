import requests

LOGIN='http://127.0.0.1:7001'
RAG='http://127.0.0.1:7000'

s = requests.Session()
s.post(f"{LOGIN}/login", data={'username':'admin','password':'admin'}, allow_redirects=False)
resp = s.get(f"{RAG}/rag/debug")
print('status', resp.status_code)
try:
    j = resp.json()
    print('count', j.get('count'))
    for i in j.get('entries',[])[:5]:
        print(i)
except Exception as e:
    print('error parsing', e)
