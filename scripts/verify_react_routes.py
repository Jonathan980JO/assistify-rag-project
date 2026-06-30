#!/usr/bin/env python3
"""Verify React static routes and API auth behavior on the login server."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
LOGIN_PORT = int(os.environ.get("LOGIN_SERVER_PORT", "7001"))
BASE = f"http://127.0.0.1:{LOGIN_PORT}"
REACT_OUT = REPO_ROOT / "assistify-ui-design" / "out"


def _safe_file_under_root(root: Path, relative_path: str) -> Path:
    """Mirror of Login_system.login_server._safe_file_under_root for offline checks."""
    root_resolved = root.resolve()
    cleaned = (relative_path or "").strip().strip("/")
    if not cleaned:
        candidates = [root / "index.html"]
    else:
        candidates = [
            root / cleaned,
            root / cleaned / "index.html",
            root / f"{cleaned}.html",
        ]
    for target in candidates:
        try:
            target_resolved = target.resolve()
        except Exception:
            continue
        if root_resolved not in target_resolved.parents and root_resolved != target_resolved:
            continue
        if target_resolved.is_file():
            return target_resolved
    return (root / "index.html").resolve() if not cleaned else (root / cleaned).resolve()


def check_static_resolver() -> list[str]:
    errors: list[str] = []
    if not REACT_OUT.is_dir():
        errors.append("React out/ missing — run npm run build in assistify-ui-design")
        return errors

    cases = [
        ("", "index.html"),
        ("login", "login/index.html"),
        ("login/", "login/index.html"),
        ("admin", "admin/index.html"),
        ("admin/", "admin/index.html"),
    ]
    for rel, expected_suffix in cases:
        resolved = _safe_file_under_root(REACT_OUT, rel)
        expected = (REACT_OUT / expected_suffix).resolve()
        if resolved != expected:
            errors.append(
                f"_safe_file_under_root({rel!r}) -> {resolved}; expected {expected}"
            )

    login_html = (REACT_OUT / "login" / "index.html").read_text(encoding="utf-8", errors="replace")
    chat_html = (REACT_OUT / "index.html").read_text(encoding="utf-8", errors="replace")
    if login_html == chat_html:
        errors.append("login/index.html is identical to root index.html")
    if "(auth)" not in login_html:
        errors.append("login/index.html missing (auth) route marker")
    if "AuthGuard" in login_html:
        errors.append("login/index.html contains chat AuthGuard")
    if "AuthGuard" not in chat_html:
        errors.append("chat index.html missing AuthGuard wrapper")

    return errors


def check_http_routes() -> list[str]:
    errors: list[str] = []

    try:
        login_r = requests.get(f"{BASE}/frontend/login/", timeout=5)
        chat_r = requests.get(f"{BASE}/frontend/", timeout=5, allow_redirects=False)
    except requests.RequestException as exc:
        errors.append(f"Cannot reach login server: {exc}")
        return errors

    login_body = login_r.text
    if login_r.status_code not in (200, 307, 302):
        errors.append(f"/frontend/login/ returned HTTP {login_r.status_code}")

    if "AuthGuard" in login_body:
        errors.append("/frontend/login/ serves chat bundle instead of login page")
    if "(auth)" not in login_body:
        errors.append("/frontend/login/ body missing (auth) route marker")

    chat_body = chat_r.text
    if chat_r.status_code == 200 and "AuthGuard" not in chat_body:
        errors.append("/frontend/ body missing AuthGuard wrapper")

    if login_body == chat_body and login_r.status_code == 200 and chat_r.status_code == 200:
        errors.append("/frontend/login/ and /frontend/ return identical HTML")

    try:
        api = requests.get(f"{BASE}/api/my-profile", timeout=5, allow_redirects=False)
    except requests.RequestException as exc:
        errors.append(f"Cannot reach /api/my-profile: {exc}")
        return errors

    if api.status_code != 401:
        errors.append(f"/api/my-profile without cookie returned {api.status_code}, expected 401")
    if api.status_code in (301, 302, 303, 307, 308):
        errors.append("/api/my-profile redirected instead of returning 401 JSON")

    index_path = REACT_OUT / "index.html"
    if index_path.is_file():
        index_html = index_path.read_text(encoding="utf-8", errors="replace")
        if "/frontend/frontend/" in index_html:
            errors.append("Built index.html contains double /frontend/frontend/ prefix")

    return errors


def main() -> int:
    errors: list[str] = []
    print("Static resolver checks...")
    resolver_errors = check_static_resolver()
    for msg in resolver_errors:
        print(f"  FAIL — {msg}")
    errors.extend(resolver_errors)
    if not resolver_errors:
        print("  OK")

    print("HTTP route checks...")
    http_errors = check_http_routes()
    for msg in http_errors:
        print(f"  FAIL — {msg}")
    errors.extend(http_errors)
    if not http_errors:
        print("  OK")

    if errors:
        print(f"\n{len(errors)} check(s) failed.")
        return 1
    print("\nReact route verification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
