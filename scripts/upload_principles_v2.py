import requests
from pathlib import Path

LOGIN_HOST = "http://127.0.0.1:7001"

s = requests.Session()
# Attempt login with default admin creds (this server often has admin/admin seeded in dev)
r = s.post(f"{LOGIN_HOST}/login", data={'username':'admin','password':'admin'}, allow_redirects=False, timeout=20)
print('login status', r.status_code)
# Extract csrf token cookie or create one
csrf = s.cookies.get('csrf_token') or 'tok123'
if not s.cookies.get('csrf_token'):
    s.cookies.set('csrf_token', csrf)

p = Path(__file__).resolve().parent.parent / 'backend' / 'assets' / 'a016c7c9_Principles_of_Management.pdf'
print('Uploading file:', p)
with p.open('rb') as f:
    files = {'file': (p.name, f, 'application/pdf')}
    resp = s.post(f"{LOGIN_HOST}/proxy/upload_rag", files=files, headers={'x-csrf-token': csrf}, timeout=300)
    print('status', resp.status_code)
    try:
        print(resp.json())
    except Exception:
        print(resp.text)
