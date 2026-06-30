"""Verify hierarchical RBAC login and API gates."""
import re
import sys

import requests

BASE = "http://127.0.0.1:7001"


def login(username: str, password: str) -> requests.Session:
    s = requests.Session()
    r = s.get(f"{BASE}/login")
    m = re.search(r'name="csrf-token" content="([^"]*)"', r.text)
    csrf = m.group(1) if m else ""
    headers = {"X-CSRF-Token": csrf} if csrf else {}
    s.post(f"{BASE}/login", data={"username": username, "password": password}, headers=headers, allow_redirects=True)
    probe = s.get(f"{BASE}/api/my-profile")
    if probe.status_code != 200 or "application/json" not in probe.headers.get("content-type", ""):
        raise RuntimeError(f"Login failed for {username}")
    return s


def main() -> int:
    errors = []
    sessions = {}

    cases = [
        ("superadmin", "superadmin", "/superadmin"),
        ("master_admin", "master_admin", "/master_admin"),
        ("admin", "admin", "/admin"),
        ("employee", "employee", "/employee"),
        ("customer", "customer", "/main"),
    ]
    for user, pwd, home in cases:
        try:
            s = login(user, pwd)
            sessions[user] = s
        except RuntimeError as e:
            errors.append(str(e))
            continue
        role = s.get(f"{BASE}/api/my-profile").json().get("role")
        if role != user:
            errors.append(f"{user}: expected role {user}, got {role}")
        if s.get(f"{BASE}{home}").status_code != 200:
            errors.append(f"{user}: cannot access home {home}")

    if "admin" in sessions:
        s = sessions["admin"]
        csrf = s.cookies.get("csrf_token", "")
        r = s.post(
            f"{BASE}/api/users/create",
            json={"username": "evil_admin", "password": "password123", "role": "admin"},
            headers={"X-CSRF-Token": csrf, "Content-Type": "application/json"},
        )
        if r.status_code != 403:
            errors.append(f"admin create admin: expected 403, got {r.status_code}")
        r = s.get(f"{BASE}/api/users", headers={"X-CSRF-Token": csrf})
        if r.status_code == 200:
            roles = {u["role"] for u in r.json()}
            if roles & {"admin", "master_admin"}:
                errors.append(f"admin /api/users leaked privileged roles: {roles}")

    if "master_admin" in sessions:
        s = sessions["master_admin"]
        csrf = s.cookies.get("csrf_token", "")
        if s.get(f"{BASE}/api/tenant-admins", headers={"X-CSRF-Token": csrf}).status_code != 200:
            errors.append("master_admin tenant-admins failed")
        if s.get(f"{BASE}/admin", allow_redirects=False).status_code == 200:
            errors.append("master_admin should not access /admin dashboard")

    if errors:
        print("FAILURES:")
        for e in errors:
            print(" -", e)
        return 1
    print("RBAC verification passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
