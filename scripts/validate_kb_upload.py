#!/usr/bin/env python3
"""Validate KB upload -> ready -> delete for PDFs via the real Login proxy."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import requests

BASE = "http://127.0.0.1:7001"
KNOWLEDGE_DIR = Path(
    os.environ.get(
        "KB_TEST_DIR",
        str(Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "knowledge"),
    )
)
PDFS = [
    "Meridian_Financial_Handbook_Clean.pdf",
    "Nimbus_Cloud_Handbook_Clean.pdf",
    "Verdant_Organics_Handbook_Clean.pdf",
]
POLL_INTERVAL = 1.0
READY_TIMEOUT = 180


def login(session: requests.Session) -> None:
    r = session.get(f"{BASE}/login", timeout=15)
    r.raise_for_status()
    csrf = session.cookies.get("csrf_token") or ""
    r = session.post(
        f"{BASE}/login",
        data={"username": "master_admin", "password": "master_admin"},
        headers={"x-csrf-token": csrf} if csrf else {},
        timeout=15,
        allow_redirects=True,
    )
    if r.status_code not in (200, 302):
        raise RuntimeError(f"login failed: {r.status_code} {r.text[:200]}")


def kb_status(session: requests.Session) -> dict:
    r = session.get(f"{BASE}/api/knowledge/kb_status", timeout=15)
    r.raise_for_status()
    return r.json()


def wait_ready(session: requests.Session, label: str) -> dict:
    t0 = time.time()
    while time.time() - t0 < READY_TIMEOUT:
        st = kb_status(session)
        state = str(st.get("state") or "").lower()
        stage = st.get("stage")
        if state == "ready":
            return st
        if state == "failed":
            raise RuntimeError(f"{label} failed: {st.get('message')}")
        time.sleep(POLL_INTERVAL)
    raise TimeoutError(f"{label} not ready after {READY_TIMEOUT}s (last={kb_status(session)})")


def upload_pdf(session: requests.Session, path: Path) -> dict:
    csrf = session.cookies.get("csrf_token") or ""
    with path.open("rb") as fh:
        r = session.post(
            f"{BASE}/proxy/upload_rag",
            files={"file": (path.name, fh, "application/pdf")},
            headers={"x-csrf-token": csrf} if csrf else {},
            timeout=120,
        )
    r.raise_for_status()
    return r.json()


def list_files(session: requests.Session) -> list[dict]:
    r = session.get(f"{BASE}/api/knowledge/files", timeout=15)
    r.raise_for_status()
    data = r.json()
    return data if isinstance(data, list) else data.get("files") or []


def delete_file(session: requests.Session, stored_name: str) -> None:
    csrf = session.cookies.get("csrf_token") or ""
    r = session.delete(
        f"{BASE}/api/knowledge/files/{stored_name}",
        headers={"x-csrf-token": csrf} if csrf else {},
        timeout=60,
    )
    r.raise_for_status()


def main() -> int:
    session = requests.Session()
    login(session)
    results = []

    # Clear stuck Meridian asset if present from prior failed run
    for existing in list_files(session):
        name = existing.get("filename") or existing.get("stored_name") or ""
        if name:
            try:
                delete_file(session, name)
                print(f"cleared prior asset: {name}")
            except Exception as exc:
                print(f"skip clear {name}: {exc}")

    for pdf_name in PDFS:
        path = KNOWLEDGE_DIR / pdf_name
        if not path.is_file():
            print(f"MISSING {path}")
            return 1
        print(f"\n=== UPLOAD {pdf_name} ===")
        up = upload_pdf(session, path)
        print("upload response:", json.dumps(up, indent=2)[:500])
        st = wait_ready(session, pdf_name)
        print(
            f"READY in {st.get('last_total_seconds')}s | indexed_chunks={st.get('indexed_chunks')} "
            f"stage_timings={st.get('stage_timings')}"
        )
        files = list_files(session)
        match = [f for f in files if pdf_name.lower() in str(f.get("display_name", f.get("filename", ""))).lower()]
        if not match:
            print("ERROR: file not listed after upload", files)
            return 1
        stored = match[0].get("filename") or match[0].get("stored_name")
        print(f"listed as {stored}")
        t_del = time.time()
        delete_file(session, stored)
        print(f"deleted in {time.time() - t_del:.2f}s")
        files_after = list_files(session)
        if any(stored in str(f.get("filename", "")) for f in files_after):
            print("ERROR: file still listed after delete")
            return 1
        results.append({"file": pdf_name, "ok": True, "stored": stored})

    print("\nALL PASSED:", json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
