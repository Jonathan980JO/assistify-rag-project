import requests
import uuid
import time
import os
from itsdangerous import URLSafeSerializer
import config

# Allow overriding the host via ASSISTIFY_HOST env var (useful during tests)
HOST = os.environ.get("ASSISTIFY_HOST", "http://localhost:7000")

print('Using host', HOST)

# Create session cookie for admin
s = URLSafeSerializer(config.SESSION_SECRET)
token = s.dumps({"username": "admin", "role": "admin"})
csrf = uuid.uuid4().hex
cookies = {config.SESSION_COOKIE: token, "csrf_token": csrf}

print('Session cookie and CSRF prepared')

# Upload a small TXT file
files = {'file': ('e2e_test.txt', b"Our support hours are Monday to Friday, 9 AM to 5 PM EST.")}
headers = {'x-csrf-token': csrf}
print('Uploading test document...')
resp = requests.post(f"{HOST}/upload_rag", files=files, cookies=cookies, headers=headers)
print('Upload response:', resp.status_code)
print(resp.text)

# Give the server a second to process
time.sleep(1)

# Query the RAG endpoint to see if our document is found
query = {"text": "What are your support hours?"}
resp2 = requests.post(f"{HOST}/query", json=query, cookies=cookies)
print('Query response:', resp2.status_code)
print(resp2.text)
