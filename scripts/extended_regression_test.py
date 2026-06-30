#!/usr/bin/env python3
"""Extended regression using create_session_token (avoids login rate limits)."""
from __future__ import annotations

import asyncio
import json
import sys
import time
import uuid
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from Login_system import guest_session
from Login_system.login_server import SESSION_COOKIE, create_session_token

LOGIN = "http://127.0.0.1:7001"
RAG = "http://127.0.0.1:7000"
OUT = ROOT / "logs" / "extended_regression.json"
results: list[tuple[str, str, str, str]] = []


def rec(phase: str, name: str, status: str, details: str = "") -> None:
    results.append((phase, name, status, details))
    print(f"[{status}] {phase} :: {name}" + (f" -- {details[:120]}" if details else ""))


def mk(user: str, role: str) -> tuple[requests.Session, dict[str, str]]:
    tok = create_session_token(user, role)
    csrf = uuid.uuid4().hex
    s = requests.Session()
    s.cookies.set(SESSION_COOKIE, tok)
    s.cookies.set("csrf_token", csrf)
    return s, {"x-csrf-token": csrf, "Accept": "application/json", "Content-Type": "application/json"}


def main() -> int:
    for u, r in [("superadmin", "superadmin"), ("admin", "admin"), ("customer", "customer")]:
        s, h = mk(u, r)
        rv = s.get(f"{LOGIN}/conversations", headers=h, timeout=20)
        rec("P3", f"session_{u}", "PASS" if rv.status_code == 200 else "FAIL", str(rv.status_code))

    sa, h = mk("superadmin", "superadmin")
    slug_a = "rt-a-" + uuid.uuid4().hex[:6]
    slug_b = "rt-b-" + uuid.uuid4().hex[:6]
    for name, slug in [("Tenant A", slug_a), ("Tenant B", slug_b)]:
        r = sa.post(f"{LOGIN}/api/tenants/create", json={"name": name, "slug": slug}, headers=h, timeout=20)
        rec("P4", f"create_{slug}", "PASS" if r.status_code == 200 else "FAIL", r.text[:100])
    r = sa.get(f"{LOGIN}/api/tenants", headers=h, timeout=20)
    rec("P4", "list_tenants", "PASS" if r.status_code == 200 else "FAIL", f"count={len(r.json()) if r.ok else 0}")

    adm, h = mk("admin", "admin")
    cust, h2 = mk("customer", "customer")
    r = adm.get(f"{LOGIN}/api/users", headers=h, timeout=20)
    rec("P5", "admin_list_users", "PASS" if r.status_code == 200 else "FAIL", str(r.status_code))
    r = cust.get(f"{LOGIN}/api/users", headers=h2, timeout=20)
    rec("P5", "customer_denied_users", "PASS" if r.status_code in (401, 403) else "FAIL", str(r.status_code))

    r = cust.post(f"{LOGIN}/conversations", json={"title": "RegTest"}, headers=h2, timeout=20)
    rec("P6", "create_conv", "PASS" if r.status_code in (200, 201) else "FAIL", r.text[:80])
    cid = (r.json() or {}).get("id") if r.ok else None
    if cid:
        for label, fn in [
            ("rename", lambda: cust.patch(f"{LOGIN}/conversations/{cid}", json={"title": "Renamed"}, headers=h2, timeout=20)),
            ("load", lambda: cust.get(f"{LOGIN}/conversations/{cid}", headers=h2, timeout=20)),
        ]:
            rv = fn()
            rec("P6", label, "PASS" if rv.status_code == 200 else "FAIL", str(rv.status_code))
        rv = cust.post(f"{LOGIN}/conversations/{cid}/message", json={"role": "user", "content": "hi"}, headers=h2, timeout=20)
        rec("P6", "append_msg", "PASS" if rv.status_code in (200, 201) else "WARN", str(rv.status_code))
        rv = cust.get(f"{LOGIN}/conversations", headers=h2, timeout=20)
        data = rv.json()
        ids = [c.get("id") for c in (data if isinstance(data, list) else data.get("conversations", []))]
        rec("P6", "persist", "PASS" if cid in ids else "FAIL", str(ids[:3]))
        rv = cust.delete(f"{LOGIN}/conversations/{cid}", headers=h2, timeout=20)
        rec("P6", "delete", "PASS" if rv.status_code in (200, 204) else "WARN", str(rv.status_code))

    pdf = (
        b"%PDF-1.4\n1 0 obj<<>>endobj\n2 0 obj<</Length 44>>stream\n"
        b"BT /F1 12 Tf 72 720 Td (Apple was founded by Steve Jobs, Steve Wozniak, and Ronald Wayne in 1976.) Tj ET\n"
        b"endstream\nendobj\n3 0 obj<</Type/Catalog/Pages 4 0 R>>endobj\n"
        b"4 0 obj<</Type/Pages/Kids[5 0 R]/Count 1>>endobj\n"
        b"5 0 obj<</Type/Page/MediaBox[0 0 612 792]/Contents 2 0 R>>endobj\n"
        b"xref\n0 6\n0000000000 65535 f \n0000000009 00000 n \n0000000052 00000 n \n"
        b"0000000150 00000 n \n0000000200 00000 n \n0000000250 00000 n \n"
        b"trailer<</Size 6/Root 3 0 R>>\nstartxref\n350\n%%EOF"
    )
    fname = "regtest_" + uuid.uuid4().hex[:8] + ".pdf"
    r = adm.post(
        f"{LOGIN}/proxy/upload_rag",
        files={"file": (fname, pdf, "application/pdf")},
        headers={"x-csrf-token": h["x-csrf-token"]},
        timeout=120,
    )
    rec("P7", "upload_pdf", "PASS" if r.status_code == 200 else "FAIL", r.text[:120])
    time.sleep(8)
    r = adm.post(
        f"{RAG}/query",
        json={"text": "Who founded Apple?", "tenant_id": 1},
        cookies=adm.cookies,
        headers={"x-csrf-token": h["x-csrf-token"], "Accept": "application/json"},
        timeout=180,
    )
    if r.ok:
        body = r.json()
        ans = str(body.get("answer") or body.get("response") or "")
        grounded = any(x in ans.lower() for x in ("jobs", "wozniak", "wayne", "1976", "founded"))
        rec("P7", "query_grounded", "PASS" if grounded else "WARN", ans[:160])
        src = body.get("sources") or body.get("retrieved_docs") or body.get("citations")
        rec("P7", "sources", "PASS" if src else "WARN", str(type(src)))
    else:
        rec("P7", "query", "FAIL", str(r.status_code))

    r = adm.delete(f"{LOGIN}/api/knowledge/files/{fname}", headers=h, timeout=60)
    rec("P8", "delete_pdf", "PASS" if r.status_code in (200, 204) else "WARN", str(r.status_code))
    time.sleep(3)
    r = adm.post(
        f"{RAG}/query",
        json={"text": "Who founded Apple?", "tenant_id": 1},
        cookies=adm.cookies,
        headers={"x-csrf-token": h["x-csrf-token"]},
        timeout=120,
    )
    rec("P8", "post_delete_query_ok", "PASS" if r.status_code == 200 else "FAIL", str(r.status_code))

    for qt, q in {
        "definition": "What is retrieval augmented generation?",
        "fact": "What is a neural network?",
        "comparison": "Compare batch and online learning",
        "list": "List three types of machine learning",
        "followup": "Explain the first one in simpler terms",
    }.items():
        r = adm.post(
            f"{RAG}/query",
            json={"text": q, "tenant_id": 1},
            cookies=adm.cookies,
            headers={"x-csrf-token": h["x-csrf-token"]},
            timeout=180,
        )
        rec("P9", qt, "PASS" if r.status_code == 200 and len(r.text) > 20 else "FAIL", f"status={r.status_code}")

    for ep in ["/api/analytics/comprehensive", "/api/analytics/errors", "/api/employee/analytics"]:
        r = adm.get(f"{LOGIN}{ep}", headers=h, timeout=20)
        rec("P11", ep, "PASS" if r.status_code == 200 else "WARN", str(r.status_code))

    r = requests.get(f"{LOGIN}/admin", headers={"Accept": "application/json"}, timeout=10)
    rec("P12", "unauth_admin_json", "PASS" if r.status_code == 401 else "FAIL", str(r.status_code))

    errs = 0
    for i in range(5):
        r = cust.post(
            f"{RAG}/query",
            json={"text": f"smoke {i}", "tenant_id": 1},
            cookies=cust.cookies,
            headers={"x-csrf-token": h2["x-csrf-token"]},
            timeout=120,
        )
        if r.status_code != 200:
            errs += 1
    rec("P13", "5_rag_queries", "PASS" if errs == 0 else "WARN", f"{errs} errors")

    asyncio.run(_ws_tests())
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, indent=2), encoding="utf-8")
    passed = sum(1 for *_, s, _ in results if s == "PASS")
    failed = sum(1 for *_, s, _ in results if s == "FAIL")
    warn = sum(1 for *_, s, _ in results if s == "WARN")
    print(f"\nSUMMARY {passed} PASS {failed} FAIL {warn} WARN TOTAL {len(results)}")
    return 1 if failed else 0


async def _ws_tests() -> None:
    import aiohttp

    adm, _ = mk("admin", "admin")
    sess_val = adm.cookies.get(SESSION_COOKIE)
    csrf_val = adm.cookies.get("csrf_token")
    cookie = f"{SESSION_COOKIE}={sess_val}; csrf_token={csrf_val}"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect("ws://127.0.0.1:7001/ws", headers={"Cookie": cookie}, timeout=15) as ws:
                rec("P10", "ws_auth_connect", "PASS", "connected")
                await ws.send_json({"type": "ping"})
                try:
                    msg = await asyncio.wait_for(ws.receive(), timeout=5)
                    rec("P10", "ws_auth_msg", "PASS", str(msg.type))
                except asyncio.TimeoutError:
                    rec("P10", "ws_auth_msg", "WARN", "no immediate reply")
    except Exception as e:
        rec("P10", "ws_auth_connect", "FAIL", str(e)[:120])

    gid = "guest_" + uuid.uuid4().hex[:12]
    gc = guest_session.make_guest_cookie_value(gid)
    gcookie = f"{guest_session.GUEST_COOKIE}={gc}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect("ws://127.0.0.1:7001/ws/guest", headers={"Cookie": gcookie}, timeout=15) as ws:
                rec("P10", "ws_guest_connect", "PASS", "connected")
    except Exception as e:
        rec("P10", "ws_guest_connect", "FAIL", str(e)[:120])

    try:
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect("ws://127.0.0.1:7000/ws/kb-events", headers={"Cookie": cookie}, timeout=15) as ws:
                rec("P10", "ws_kb_events", "PASS", "connected")
    except Exception as e:
        rec("P10", "ws_kb_events", "FAIL", str(e)[:120])


if __name__ == "__main__":
    raise SystemExit(main())
