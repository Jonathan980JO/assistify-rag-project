from fastapi.testclient import TestClient
import uuid
from itsdangerous import URLSafeSerializer
import sys
from pathlib import Path
# Ensure project root is on sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import config
from backend import assistify_rag_server

client = TestClient(assistify_rag_server.app)

s = URLSafeSerializer(config.SESSION_SECRET)
token = s.dumps({"username": "admin", "role": "admin"})
csrf = uuid.uuid4().hex
client.cookies.set(config.SESSION_COOKIE, token)
client.cookies.set('csrf_token', csrf)

print('Uploading test txt...')
files = {'file': ('e2e_test.txt', b"Our support hours are Monday to Friday, 9 AM to 5 PM EST.")}
req_headers = {'x-csrf-token': csrf, 'host': 'localhost'}
resp = client.post('/upload_rag', files=files, headers=req_headers)
print('Upload status:', resp.status_code)
try:
    print(resp.json())
except Exception:
    print(resp.text)

# Query
resp2 = client.post('/query', json={'text':'What are your support hours?'}, headers={'host': 'localhost'})
print('Query status:', resp2.status_code)
try:
    print(resp2.json())
except Exception:
    print(resp2.text)
