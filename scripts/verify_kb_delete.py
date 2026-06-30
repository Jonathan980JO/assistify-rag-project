"""Smoke test: admin can list and delete knowledge-base files (requires login + RAG)."""
import re
import sys

import requests

LOGIN_BASE = "http://127.0.0.1:7001"
RAG_BASE = "http://127.0.0.1:7000"


def login(username: str, password: str) -> requests.Session:
    s = requests.Session()
    r = s.get(f"{LOGIN_BASE}/login")
    m = re.search(r'name="csrf-token" content="([^"]*)"', r.text)
    csrf = m.group(1) if m else s.cookies.get("csrf_token", "")
    headers = {"X-CSRF-Token": csrf} if csrf else {}
    s.post(
        f"{LOGIN_BASE}/login",
        data={"username": username, "password": password},
        headers=headers,
        allow_redirects=True,
    )
    probe = s.get(f"{LOGIN_BASE}/api/my-profile")
    if probe.status_code != 200:
        raise RuntimeError(f"Login failed for {username}")
    return s


def rag_up() -> bool:
    try:
        return requests.get(f"{RAG_BASE}/kb_status", timeout=3).status_code == 200
    except requests.RequestException:
        return False


def main() -> int:
    errors = []

    if not rag_up():
        print("SKIP: RAG server not reachable on port 7000 (start full stack to run delete test).")
        return 0

    try:
        session = login("admin", "admin")
    except RuntimeError as e:
        print(f"FAIL: {e}")
        return 1

    csrf = session.cookies.get("csrf_token", "")
    headers = {"X-CSRF-Token": csrf} if csrf else {}

    list_resp = session.get(f"{LOGIN_BASE}/api/knowledge/files", headers=headers)
    if list_resp.status_code != 200:
        errors.append(f"list files: expected 200, got {list_resp.status_code}")
    else:
        files = list_resp.json()
        if not files:
            print("KB delete verification passed (no files to delete).")
            return 0

        target = files[0].get("stored_name") or files[0].get("name")
        del_resp = session.delete(
            f"{LOGIN_BASE}/api/knowledge/files/{target}",
            headers=headers,
        )
        if del_resp.status_code != 200:
            errors.append(
                f"delete {target!r}: expected 200, got {del_resp.status_code} — {del_resp.text[:300]}"
            )
        else:
            after = session.get(f"{LOGIN_BASE}/api/knowledge/files", headers=headers).json()
            names = {f.get("stored_name") or f.get("name") for f in after}
            if target in names:
                errors.append(f"delete {target!r}: file still listed after delete")

    if errors:
        print("FAILURES:")
        for e in errors:
            print(" -", e)
        return 1

    print("KB delete verification passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
