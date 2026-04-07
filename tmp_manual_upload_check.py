import requests
from pathlib import Path

s = requests.Session()
r = s.post('http://127.0.0.1:7001/login', data={'username': 'admin', 'password': 'admin'}, allow_redirects=False, timeout=20)
print('login', r.status_code)
csrf = 'tok123abc'
s.cookies.set('csrf_token', csrf)
mode = s.post('http://127.0.0.1:7000/rag/doc-mode', json={'mode': 'single', 'active_sources': []}, timeout=20)
print('mode', mode.status_code, mode.text[:160])
p = Path(r'C:\Users\MK\Desktop\Notes\PDF\Introduction_to_Philosophy-WEB_cszrKYp-compressed.pdf')
with p.open('rb') as f:
    up = s.post('http://127.0.0.1:7000/upload_rag', files={'file': (p.name, f, 'application/pdf')}, headers={'x-csrf-token': csrf}, timeout=600)
print('upload', up.status_code)
print(up.text)
files = s.get('http://127.0.0.1:7000/rag/files', timeout=20)
print('files', files.status_code)
print(files.text[:400])
