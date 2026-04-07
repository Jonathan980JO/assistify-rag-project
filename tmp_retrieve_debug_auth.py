import requests, json
s=requests.Session()
r=s.post('http://127.0.0.1:7001/login', data={'username':'admin','password':'admin'}, allow_redirects=False, timeout=20)
print('login', r.status_code)
for q in ['Who is Frederick Taylor?','Disadvantages of scientific management','Steps in planning process']:
    rr=s.get('http://127.0.0.1:7000/rag/retrieve-debug', params={'query':q,'top_k':10}, timeout=60)
    print('\nQ:', q, 'status', rr.status_code)
    if rr.status_code!=200:
        print(rr.text[:300]);
        continue
    data=rr.json()
    rows=data.get('results') or data.get('rows') or data.get('data') or data.get('docs') or data
    if isinstance(rows, dict):
        rows=rows.get('rows') or rows.get('results') or []
    if not isinstance(rows, list):
        print('unexpected payload keys:', list(data.keys()) if isinstance(data,dict) else type(data));
        print(str(data)[:400]);
        continue
    for i,d in enumerate(rows[:5],1):
        print(f"  {i}) page={d.get('page')} source={d.get('source')} sim={d.get('similarity')} text={(d.get('text') or d.get('preview') or '')[:110].replace(chr(10),' ')}")
