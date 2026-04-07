import requests
import uuid
from itsdangerous import URLSafeSerializer
from pathlib import Path

import config

LOGIN_HOST = "http://127.0.0.1:7001"
ADMIN_USER = "admin"
ADMIN_ROLE = "admin"

s = URLSafeSerializer(config.SESSION_SECRET)
# Create session token for admin
token = s.dumps({"username": ADMIN_USER, "role": ADMIN_ROLE})
csrf = uuid.uuid4().hex
cookies = {config.SESSION_COOKIE: token, 'csrf_token': csrf}
headers = {'x-csrf-token': csrf}

p = Path(__file__).resolve().parent.parent / 'backend' / 'assets' / 'a016c7c9_Principles_of_Management.pdf'
print('Uploading file:', p)
with p.open('rb') as f:
    files = {'file': (p.name, f, 'application/pdf')}
    resp = requests.post(f"{LOGIN_HOST}/proxy/upload_rag", files=files, cookies=cookies, headers=headers, timeout=300)
    print('status', resp.status_code)
    try:
        print(resp.json())
    except Exception:
        print(resp.text)
