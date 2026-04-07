import requests
s=requests.Session()
login=s.post('http://127.0.0.1:7001/login', data={'username':'admin','password':'admin'}, allow_redirects=False, timeout=20)
print('login', login.status_code, 'cookie', bool(s.cookies))
r=s.post('http://127.0.0.1:7000/query', json={'text':'What is psychology?'}, timeout=180)
print('status', r.status_code)
print(r.text[:500])
