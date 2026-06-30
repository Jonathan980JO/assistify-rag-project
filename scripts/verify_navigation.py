"""Verify React app shell is served on authenticated dashboard routes."""
import re
import sys

import requests

BASE = "http://127.0.0.1:7001"
USERS = [
    ("superadmin", "superadmin", "superadmin", ["/superadmin", "/profile", "/notifications"]),
    ("admin", "admin", "admin", ["/admin", "/admin/users", "/profile", "/notifications"]),
    ("employee", "employee", "employee", ["/employee", "/employee/customers", "/profile", "/notifications"]),
    ("customer", "customer", "customer", ["/main", "/my-tickets", "/profile", "/notifications"]),
]


def login(username: str, password: str) -> requests.Session:
    s = requests.Session()
    r = s.get(f"{BASE}/login", allow_redirects=True)
    csrf = ""
    m = re.search(r'name="csrf-token" content="([^"]*)"', r.text) or re.search(
        r'name="csrf_token"[^>]*value="([^"]*)"', r.text
    )
    if m:
        csrf = m.group(1)
    headers = {"X-CSRF-Token": csrf} if csrf else {}
    s.post(
        f"{BASE}/login",
        data={"username": username, "password": password},
        headers=headers,
        allow_redirects=True,
    )
    return s


def main() -> int:
    errors = []
    for username, password, role, paths in USERS:
        s = login(username, password)
        probe = s.get(f"{BASE}/api/my-profile")
        if probe.status_code != 200:
            errors.append(f"{username}: api login failed ({probe.status_code})")
            continue
        if probe.json().get("role") != role:
            errors.append(f"{username}: expected role {role}, got {probe.json().get('role')}")

        for path in paths:
            r = s.get(f"{BASE}{path}", allow_redirects=True)
            if r.status_code != 200:
                errors.append(f"{username}{path}: status {r.status_code}")
                continue
            if "/frontend/" not in r.url:
                errors.append(f"{username}{path}: expected React URL under /frontend/, got {r.url}")
            if "Assistify" not in r.text:
                errors.append(f"{username}{path}: missing React shell branding")
            if "menu-btn" in r.text:
                errors.append(f"{username}{path}: legacy menu-btn still present")
            if "/static/navigation.css" in r.text:
                errors.append(f"{username}{path}: legacy navigation.css still referenced")

    if errors:
        print("FAILURES:")
        for e in errors:
            print(" -", e)
        return 1

    print("All React navigation shell checks passed for 4 roles.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
