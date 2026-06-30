#!/usr/bin/env python3
"""End-to-end health checks for Ollama, Piper, RAG, and Login."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

REACT_OUT_INDEX = REPO_ROOT / "assistify-ui-design" / "out" / "index.html"
REACT_OUT_STATIC = REPO_ROOT / "assistify-ui-design" / "out" / "_next" / "static"
LOGIN_PORT = int(os.environ.get("LOGIN_SERVER_PORT", "7001"))

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "127.0.0.1")
OLLAMA_PORT = int(os.environ.get("OLLAMA_PORT", "11434"))
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:3b")
LLM_PORT = int(os.environ.get("LLM_SERVER_PORT", str(__import__("config").LLM_SERVER_PORT)))


def _get(url: str, timeout: float = 5.0) -> tuple[bool, str]:
    try:
        r = requests.get(url, timeout=timeout)
        if r.status_code < 500:
            return True, f"HTTP {r.status_code}"
        return False, f"HTTP {r.status_code}"
    except requests.RequestException as e:
        return False, str(e)


def _post_json(url: str, payload: dict, timeout: float = 10.0) -> tuple[bool, str]:
    try:
        r = requests.post(url, json=payload, timeout=timeout)
        if r.status_code == 200:
            return True, "OK"
        return False, f"HTTP {r.status_code}: {r.text[:200]}"
    except requests.RequestException as e:
        return False, str(e)


def run_checks(*, require_piper: bool = True) -> tuple[bool, list[str]]:
    errors: list[str] = []

    ok, detail = _get(f"http://{OLLAMA_HOST}:{OLLAMA_PORT}/api/tags")
    print(f"Ollama ({OLLAMA_HOST}:{OLLAMA_PORT}): {'OK' if ok else 'FAIL'} — {detail}")
    if not ok:
        errors.append("Ollama not reachable on port 11434")

    if ok:
        model_ok, model_detail = _post_json(
            f"http://{OLLAMA_HOST}:{OLLAMA_PORT}/api/show",
            {"model": OLLAMA_MODEL},
        )
        print(f"Ollama model '{OLLAMA_MODEL}': {'OK' if model_ok else 'FAIL'} — {model_detail}")
        if not model_ok:
            errors.append(f"Model '{OLLAMA_MODEL}' not loadable — run: ollama pull {OLLAMA_MODEL}")

    ok, detail = _get(f"http://127.0.0.1:{LLM_PORT}/internal/gpu-status")
    print(f"LLM shim (8010): {'OK' if ok else 'WARN (optional)'} — {detail}")

    if require_piper:
        ok, detail = _get("http://127.0.0.1:5002/health")
        print(f"Piper TTS (5002): {'OK' if ok else 'FAIL'} — {detail}")
        if not ok:
            errors.append("Piper TTS not reachable on port 5002")

    ok, detail = _get("http://127.0.0.1:7000/health", timeout=15.0)
    print(f"RAG (7000): {'OK' if ok else 'FAIL'} — {detail}")
    if not ok:
        errors.append("RAG server not reachable on port 7000")

    ok, detail = _get("http://127.0.0.1:7001/login")
    print(f"Login (7001): {'OK' if ok else 'FAIL'} — {detail}")
    if not ok:
        errors.append("Login server not reachable on port 7001")

    artifacts_ok = REACT_OUT_INDEX.is_file() and REACT_OUT_STATIC.is_dir()
    print(
        f"React UI artifacts (out/): {'OK' if artifacts_ok else 'FAIL'} — "
        f"{'index.html + _next/static' if artifacts_ok else 'run npm run build in assistify-ui-design'}"
    )
    if not artifacts_ok:
        errors.append("React UI build missing — run: python start_main_servers.py --ui-build-only")

    try:
        login_r = requests.get(f"http://127.0.0.1:{LOGIN_PORT}/frontend/login/", timeout=5)
        chat_r = requests.get(f"http://127.0.0.1:{LOGIN_PORT}/frontend/", timeout=5, allow_redirects=False)
        login_body = login_r.text
        login_ok = (
            login_r.status_code < 500
            and login_body != chat_r.text
            and "AuthGuard" not in login_body
            and "(auth)" in login_body
        )
        print(
            f"React login (/frontend/login/): {'OK' if login_ok else 'FAIL'} — "
            f"HTTP {login_r.status_code}, distinct_from_chat={'yes' if login_body != chat_r.text else 'no'}"
        )
        if not login_ok:
            errors.append("React login page serves wrong content — rebuild UI and restart login server")
    except requests.RequestException as e:
        print(f"React login (/frontend/login/): FAIL — {e}")
        errors.append("React login route unreachable")

    try:
        api_r = requests.get(f"http://127.0.0.1:{LOGIN_PORT}/api/my-profile", timeout=5, allow_redirects=False)
        api_ok = api_r.status_code == 401
        print(f"API auth (/api/my-profile): {'OK' if api_ok else 'FAIL'} — HTTP {api_r.status_code}")
        if not api_ok:
            errors.append(f"/api/my-profile returned {api_r.status_code}, expected 401")
    except requests.RequestException as e:
        print(f"API auth (/api/my-profile): FAIL — {e}")

    if REACT_OUT_INDEX.is_file():
        index_html = REACT_OUT_INDEX.read_text(encoding="utf-8", errors="replace")
        double_prefix = "/frontend/frontend/" in index_html
        print(f"React link prefix: {'FAIL' if double_prefix else 'OK'} — double /frontend/={'yes' if double_prefix else 'no'}")
        if double_prefix:
            errors.append("Built HTML contains /frontend/frontend/ — fix appPath vs fullAppPath and rebuild")

    ok, detail = _get(f"http://127.0.0.1:{LOGIN_PORT}/frontend/admin/")
    admin_route_ok = ok and any(token in detail for token in ("200", "302", "307"))
    print(f"React admin route (/frontend/admin/): {'OK' if admin_route_ok else 'FAIL'} — {detail}")

    return len(errors) == 0, errors


def main() -> int:
    require_piper = "--no-piper" not in sys.argv
    ok, errors = run_checks(require_piper=require_piper)
    if errors:
        print("\nFAILURES:")
        for e in errors:
            print(f" - {e}")
        return 1
    print("\nStack verification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
