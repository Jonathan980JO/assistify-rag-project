"""Upload sample PDF via Login proxy and verify RAG can answer from it."""
import os
import sys
import time

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

LOGIN_HOST = os.environ.get("LOGIN_HOST", "http://127.0.0.1:7001")
RAG_HOST = os.environ.get("RAG_HOST", "http://127.0.0.1:7000")
PDF_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "tmp_test_pdfs",
    "management_test.pdf",
)


def main() -> int:
    if not os.path.isfile(PDF_PATH):
        print(f"Missing PDF: {PDF_PATH}")
        return 1

    s = requests.Session()
    r = s.post(
        f"{LOGIN_HOST}/login",
        data={"username": "admin", "password": "admin"},
        allow_redirects=False,
        timeout=20,
    )
    if r.status_code not in (302, 303):
        print("login failed", r.status_code)
        return 1
    print("login ok")

    csrf = s.cookies.get("csrf_token", "")
    with open(PDF_PATH, "rb") as f:
        resp = s.post(
            f"{LOGIN_HOST}/proxy/upload_rag",
            files={"file": ("management_test.pdf", f, "application/pdf")},
            headers={"x-csrf-token": csrf} if csrf else {},
            timeout=120,
        )
    print("upload", resp.status_code, resp.text[:300])
    if resp.status_code not in (200, 202):
        return 1
    uploaded_name = resp.json().get("filename") or "management_test.pdf"

    for i in range(90):
        st = requests.get(f"{RAG_HOST}/kb_status", timeout=10).json()
        state = st.get("state")
        print(f"kb_status[{i}] state={state}")
        if state == "ready":
            break
        time.sleep(2)
    else:
        print("KB not ready in time")
        return 1

    s.post(
        f"{RAG_HOST}/rag/doc-mode",
        json={"mode": "single", "active_sources": ["management_test.pdf"]},
        timeout=20,
    )
    print("active_source management_test.pdf")

    q = "Who proposed scientific management according to the document?"
    ans = s.post(f"{RAG_HOST}/query", json={"text": q}, timeout=120)
    print("query", ans.status_code)
    body = ans.json() if ans.ok else {}
    print("answer:", (body.get("answer") or "")[:500])
    if "not found in the document" in str(body.get("answer", "")).lower():
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
