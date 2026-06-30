# -*- coding: utf-8 -*-
import requests

LOGIN = "http://127.0.0.1:7001/login"
QUERY = "http://127.0.0.1:7000/query"

queries = [
    "ما هي الإدارة؟",
    "ما هو التنظيم؟",
    "ارجع فقرة عن الأهداف",
    "ارجع فقرة تشرح الإدارة العلمية",
    "ما هي خطوات عملية التخطيط؟",
    "ما هو أفضل موقع للتجارة الإلكترونية؟",
]

s = requests.Session()
resp = s.post(LOGIN, data={"username":"admin", "password":"admin"}, allow_redirects=False, timeout=20)
print("login_status", resp.status_code)
print("has_session_cookie", any(k.lower().startswith("session") or k=="session" for k in s.cookies.keys()))

for q in queries:
    r = s.post(QUERY, json={"text": q}, timeout=120)
    print("="*80)
    print(q)
    print("status", r.status_code)
    try:
        data = r.json()
        ans = data.get("answer", "")
        print("answer_preview", (ans or "")[:220].replace("\n", " "))
    except Exception:
        print("non_json", r.text[:220])
