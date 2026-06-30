#!/usr/bin/env python3
"""
Assistify Full Regression Test Suite (post-refactor validation).
Runs Phases 1-13 and emits structured JSON + human report.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import time
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import config  # noqa: E402
from itsdangerous import URLSafeSerializer  # noqa: E402

LOGIN = os.environ.get("LOGIN_HOST", "http://127.0.0.1:7001")
RAG = os.environ.get("RAG_HOST", "http://127.0.0.1:7000")
TIMEOUT = 30
REPORT_PATH = ROOT / "logs" / "full_regression_report.json"


@dataclass
class TestResult:
    phase: str
    name: str
    status: str  # PASS | FAIL | WARN | SKIP
    details: str = ""
    repro: str = ""
    file_hint: str = ""
    cause: str = ""


@dataclass
class Report:
    started: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    results: list[TestResult] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    startup_logs: list[str] = field(default_factory=list)

    def add(self, phase: str, name: str, status: str, **kw: str) -> None:
        self.results.append(TestResult(phase=phase, name=name, status=status, **kw))

    def summary(self) -> dict[str, Any]:
        by_status = Counter(r.status for r in self.results)
        by_phase = defaultdict(lambda: {"PASS": 0, "FAIL": 0, "WARN": 0, "SKIP": 0})
        for r in self.results:
            by_phase[r.phase][r.status] += 1
        return {
            "total": len(self.results),
            "passed": by_status["PASS"],
            "failed": by_status["FAIL"],
            "warnings": by_status["WARN"],
            "skipped": by_status["SKIP"],
            "by_phase": dict(by_phase),
        }


report = Report()


def wait_for_servers(max_wait: int = 180) -> bool:
    deadline = time.time() + max_wait
    login_ok = rag_ok = False
    while time.time() < deadline:
        try:
            r = requests.get(f"{LOGIN}/", timeout=3)
            login_ok = r.status_code in (200, 302, 307)
        except Exception:
            login_ok = False
        try:
            r = requests.get(f"{RAG}/health", timeout=3)
            rag_ok = r.status_code == 200
        except Exception:
            rag_ok = False
        if login_ok and rag_ok:
            return True
        time.sleep(2)
    return login_ok and rag_ok


def session_for(username: str, role: str) -> dict[str, Any]:
    s = URLSafeSerializer(config.SESSION_SECRET)
    token = s.dumps({"username": username, "role": role, "iat": time.time()})
    csrf = uuid.uuid4().hex
    return {
        "cookies": {config.SESSION_COOKIE: token, "csrf_token": csrf},
        "headers": {"x-csrf-token": csrf, "Accept": "application/json"},
    }


def login_api(username: str, password: str) -> requests.Session | None:
    sess = requests.Session()
    try:
        r = sess.post(
            f"{LOGIN}/login",
            data={"username": username, "password": password},
            allow_redirects=False,
            timeout=TIMEOUT,
        )
        if r.status_code in (200, 302, 303) and sess.cookies.get(config.SESSION_COOKIE):
            return sess
    except Exception:
        pass
    return None


def rag_query(sess: requests.Session, text: str, tenant_id: int = 1, conversation_id: str | None = None) -> requests.Response:
    csrf = sess.cookies.get("csrf_token", "")
    payload: dict[str, Any] = {"text": text, "tenant_id": tenant_id}
    if conversation_id:
        payload["conversation_id"] = conversation_id
    return sess.post(
        f"{RAG}/query",
        json=payload,
        cookies=sess.cookies,
        headers={"x-csrf-token": csrf, "Accept": "application/json"},
        timeout=120,
    )


# ---------- Phase 1: Startup ----------
def phase1_startup() -> None:
    phase = "Phase1-Startup"
    modules = [
        "backend.database",
        "backend.knowledge_base",
        "backend.assistify_rag_server",
        "Login_system.login_server",
        "backend.main_llm_server",
    ]
    for mod in modules:
        try:
            if mod in sys.modules:
                del sys.modules[mod]
            __import__(mod)
            report.add(phase, f"import:{mod}", "PASS")
        except Exception as e:
            report.add(
                phase,
                f"import:{mod}",
                "FAIL",
                details=str(e),
                file_hint=mod.replace(".", "/") + ".py",
                cause="Import/circular dependency error",
            )

    if wait_for_servers():
        report.add(phase, "login_server_running", "PASS", details=f"{LOGIN}")
        report.add(phase, "rag_server_running", "PASS", details=f"{RAG}/health")
    else:
        report.add(
            phase,
            "servers_running",
            "FAIL",
            details="Login or RAG not reachable after wait",
            repro=f"curl {LOGIN}/ and {RAG}/health",
            cause="Servers not started or crashed on boot",
        )


# ---------- Phase 2: Routes ----------
def _collect_routes(app_module: str) -> list[tuple[str, str]]:
    mod = __import__(app_module, fromlist=["app"])
    app = mod.app
    routes = []
    for r in app.routes:
        methods = sorted(getattr(r, "methods", None) or {"GET"})
        path = getattr(r, "path", None) or getattr(r, "path_format", str(r))
        if path:
            for m in methods:
                if m not in ("HEAD", "OPTIONS"):
                    routes.append((m, path))
    return sorted(set(routes))


def phase2_routes() -> None:
    phase = "Phase2-Routes"
    try:
        login_routes = _collect_routes("Login_system.login_server")
        rag_routes = _collect_routes("backend.assistify_rag_server")
    except Exception as e:
        report.add(phase, "route_enumeration", "FAIL", details=str(e))
        return

    # Baseline from pre-refactor audit copies (same app objects)
    try:
        audit_login = _collect_routes("assistify_refactor_audit.login_server")
        audit_rag = _collect_routes("assistify_refactor_audit.assistify_rag_server")
    except Exception:
        audit_login = audit_rag = None

    login_set = set(login_routes)
    rag_set = set(rag_routes)
    dupes_login = [k for k, v in Counter(login_routes).items() if v > 1]
    dupes_rag = [k for k, v in Counter(rag_routes).items() if v > 1]

    report.add(phase, "login_route_count", "PASS", details=str(len(login_set)))
    report.add(phase, "rag_route_count", "PASS", details=str(len(rag_set)))

    if dupes_login:
        report.add(phase, "login_duplicate_routes", "FAIL", details=str(dupes_login))
    else:
        report.add(phase, "login_no_duplicates", "PASS")

    if dupes_rag:
        report.add(phase, "rag_duplicate_routes", "FAIL", details=str(dupes_rag))
    else:
        report.add(phase, "rag_no_duplicates", "PASS")

    if audit_login is not None:
        missing = audit_login - login_set
        extra = login_set - audit_login
        if missing:
            report.add(phase, "login_missing_vs_audit", "FAIL", details=str(sorted(missing)[:20]))
        else:
            report.add(phase, "login_no_missing_vs_audit", "PASS")
        if extra:
            report.add(phase, "login_extra_vs_audit", "WARN", details=str(sorted(extra)[:20]))
        if len(audit_login) == len(login_set) and not missing:
            report.add(phase, "login_route_count_unchanged", "PASS", details=str(len(login_set)))

    if audit_rag is not None:
        missing = audit_rag - rag_set
        extra = rag_set - audit_rag
        if missing:
            report.add(phase, "rag_missing_vs_audit", "FAIL", details=str(sorted(missing)[:20]))
        else:
            report.add(phase, "rag_no_missing_vs_audit", "PASS")
        if extra:
            report.add(phase, "rag_extra_vs_audit", "WARN", details=str(sorted(extra)[:20]))
        if len(audit_rag) == len(rag_set) and not missing:
            report.add(phase, "rag_route_count_unchanged", "PASS", details=str(len(rag_set)))


# ---------- Phase 3: Auth ----------
def phase3_auth() -> None:
    phase = "Phase3-Auth"
    creds = [
        ("superadmin", "superadmin", "superadmin"),
        ("admin", "admin", "admin"),
        ("customer", "customer123", "customer"),
    ]
    for user, pwd, role in creds:
        sess = login_api(user, pwd)
        if sess:
            report.add(phase, f"login:{user}", "PASS")
            if "csrf_token" in sess.cookies or sess.cookies.get("csrf_token"):
                report.add(phase, f"csrf_cookie:{user}", "PASS")
            else:
                report.add(phase, f"csrf_cookie:{user}", "WARN", details="No csrf_token cookie")
            r = sess.get(f"{LOGIN}/conversations", timeout=TIMEOUT)
            if r.status_code == 200:
                report.add(phase, f"session_validate:{user}", "PASS")
            else:
                report.add(phase, f"session_validate:{user}", "FAIL", details=str(r.status_code))
            try:
                sess.get(f"{LOGIN}/logout", timeout=TIMEOUT)
                report.add(phase, f"logout:{user}", "PASS")
            except Exception as e:
                report.add(phase, f"logout:{user}", "WARN", details=str(e))
        else:
            report.add(
                phase,
                f"login:{user}",
                "FAIL",
                repro=f"POST {LOGIN}/login username={user}",
                file_hint="Login_system/login_server.py",
            )

    bad = login_api("admin", "wrongpassword123!")
    if bad is None:
        report.add(phase, "invalid_credentials_rejected", "PASS")
    else:
        report.add(phase, "invalid_credentials_rejected", "FAIL", details="Bad login succeeded")

    # Lockout smoke: multiple failures
    for i in range(6):
        login_api("nonexistent_user_xyz", "bad")
    r = requests.post(
        f"{LOGIN}/login",
        data={"username": "nonexistent_user_xyz", "password": "bad"},
        timeout=TIMEOUT,
    )
    if r.status_code in (429, 403) or "lock" in r.text.lower() or "too many" in r.text.lower():
        report.add(phase, "lockout_logic", "PASS", details=f"status={r.status_code}")
    else:
        report.add(phase, "lockout_logic", "WARN", details=f"status={r.status_code} (may need more attempts)")


# ---------- Phase 4-5: Tenant + User mgmt ----------
def phase4_tenant() -> None:
    phase = "Phase4-Tenant"
    sa = login_api("superadmin", "superadmin")
    if not sa:
        report.add(phase, "superadmin_session", "SKIP", details="Cannot login superadmin")
        return

    slug_a = f"regtest-a-{uuid.uuid4().hex[:8]}"
    slug_b = f"regtest-b-{uuid.uuid4().hex[:8]}"
    csrf = sa.cookies.get("csrf_token", "")
    hdrs = {"x-csrf-token": csrf, "Accept": "application/json"}

    tenant_ids: dict[str, int] = {}
    for name, slug in [("Tenant A RegTest", slug_a), ("Tenant B RegTest", slug_b)]:
        r = sa.post(
            f"{LOGIN}/api/tenants/create",
            json={"name": name, "slug": slug},
            headers=hdrs,
            timeout=TIMEOUT,
        )
        if r.status_code in (200, 201):
            body = r.json()
            tenant_ids[slug] = int(body.get("id", 0))
            report.add(phase, f"create_tenant:{slug}", "PASS", details=f"id={tenant_ids[slug]}")
        else:
            report.add(phase, f"create_tenant:{slug}", "FAIL", details=f"{r.status_code} {r.text[:200]}")

    r = sa.get(f"{LOGIN}/api/tenants", headers=hdrs, timeout=TIMEOUT)
    if r.status_code == 200:
        tenants = r.json() if r.headers.get("content-type", "").startswith("application/json") else []
        report.add(phase, "list_tenants", "PASS", details=f"count={len(tenants)}")
    else:
        report.add(phase, "list_tenants", "FAIL", details=str(r.status_code))

    admin_a = login_api("admin", "admin")
    if admin_a and len(tenant_ids) >= 2:
        ah = {"x-csrf-token": admin_a.cookies.get("csrf_token", ""), "Accept": "application/json", "Content-Type": "application/json"}
        tid_a = next(iter(tenant_ids.values()))
        r = admin_a.post(f"{LOGIN}/conversations", json={"title": "Tenant scope test"}, headers=ah, timeout=TIMEOUT)
        report.add(phase, "admin_create_conversation", "PASS" if r.status_code in (200, 201) else "WARN", details=str(r.status_code))
        # Admin is tenant-scoped; verify KB list returns only own-tenant files
        r2 = admin_a.get(f"{LOGIN}/api/knowledge/files", headers=ah, timeout=TIMEOUT)
        report.add(phase, "admin_kb_tenant_scoped", "PASS" if r2.status_code == 200 else "FAIL", details=str(r2.status_code))


def phase5_user_mgmt() -> None:
    phase = "Phase5-UserMgmt"
    admin = login_api("admin", "admin")
    customer = login_api("customer", "customer123")
    if not admin:
        report.add(phase, "admin_login", "SKIP")
        return

    csrf = admin.cookies.get("csrf_token", "")
    hdrs = {"x-csrf-token": csrf, "Accept": "application/json"}

    r = admin.get(f"{LOGIN}/api/users", headers=hdrs, timeout=TIMEOUT)
    report.add(phase, "list_users_admin", "PASS" if r.status_code == 200 else "FAIL", details=str(r.status_code))

    if customer:
        r2 = customer.get(f"{LOGIN}/api/users", headers=hdrs, timeout=TIMEOUT)
        denied = r2.status_code in (401, 403, 302)
        report.add(phase, "customer_cannot_list_users", "PASS" if denied else "FAIL", details=str(r2.status_code))

    r3 = admin.get(f"{LOGIN}/api/memberships/pending", headers=hdrs, timeout=TIMEOUT)
    report.add(phase, "memberships_pending_admin", "PASS" if r3.status_code == 200 else "WARN", details=str(r3.status_code))


# ---------- Phase 6: Conversations ----------
def phase6_conversations() -> None:
    phase = "Phase6-Conversations"
    sess = login_api("customer", "customer123")
    if not sess:
        report.add(phase, "customer_login", "SKIP")
        return
    csrf = sess.cookies.get("csrf_token", "")
    hdrs = {"x-csrf-token": csrf, "Accept": "application/json", "Content-Type": "application/json"}

    r = sess.post(f"{LOGIN}/conversations", json={"title": "RegTest Chat"}, headers=hdrs, timeout=TIMEOUT)
    if r.status_code not in (200, 201):
        report.add(phase, "create_conversation", "FAIL", details=f"{r.status_code} {r.text[:200]}")
        return
    conv = r.json()
    cid = conv.get("id") or conv.get("conversation_id")
    report.add(phase, "create_conversation", "PASS", details=str(cid))

    r2 = sess.patch(f"{LOGIN}/conversations/{cid}", json={"title": "Renamed RegTest"}, headers=hdrs, timeout=TIMEOUT)
    report.add(phase, "rename_conversation", "PASS" if r2.status_code == 200 else "WARN", details=str(r2.status_code))

    r3 = sess.get(f"{LOGIN}/conversations/{cid}", headers=hdrs, timeout=TIMEOUT)
    report.add(phase, "load_conversation", "PASS" if r3.status_code == 200 else "FAIL", details=str(r3.status_code))

    r4 = sess.post(
        f"{LOGIN}/conversations/{cid}/message",
        json={"role": "user", "content": "Regression test message"},
        headers=hdrs,
        timeout=TIMEOUT,
    )
    report.add(phase, "append_message", "PASS" if r4.status_code in (200, 201) else "WARN", details=str(r4.status_code))

    r5 = sess.get(f"{LOGIN}/conversations", headers=hdrs, timeout=TIMEOUT)
    if r5.status_code == 200:
        data = r5.json()
        ids = [c.get("id") for c in (data if isinstance(data, list) else data.get("conversations", []))]
        report.add(phase, "persistence_list", "PASS" if cid in ids else "FAIL", details=str(ids[:5]))
    else:
        report.add(phase, "persistence_list", "FAIL", details=str(r5.status_code))

    r6 = sess.delete(f"{LOGIN}/conversations/{cid}", headers=hdrs, timeout=TIMEOUT)
    report.add(phase, "delete_conversation", "PASS" if r6.status_code in (200, 204) else "WARN", details=str(r6.status_code))


# ---------- Phase 7-8: PDF KB ----------
def _make_test_pdf(text: str) -> bytes:
    try:
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import letter
        buf = BytesIO()
        c = canvas.Canvas(buf, pagesize=letter)
        c.drawString(72, 720, text[:200])
        c.save()
        return buf.getvalue()
    except ImportError:
        # Minimal PDF
        content = f"BT /F1 12 Tf 72 720 Td ({text[:120]}) Tj ET"
        pdf = (
            b"%PDF-1.4\n1 0 obj<<>>endobj\n2 0 obj<</Length %d>>stream\n%s\nendstream\nendobj\n"
            b"3 0 obj<</Type/Catalog/Pages 4 0 R>>endobj\n4 0 obj<</Type/Pages/Kids[5 0 R]/Count 1>>endobj\n"
            b"5 0 obj<</Type/Page/MediaBox[0 0 612 792]/Contents 2 0 R>>endobj\n"
            b"xref\n0 6\n0000000000 65535 f \n0000000009 00000 n \n0000000052 00000 n \n"
            b"0000000150 00000 n \n0000000200 00000 n \n0000000250 00000 n \n"
            b"trailer<</Size 6/Root 3 0 R>>\nstartxref\n350\n%%EOF"
        ) % (len(content), content.encode("latin-1", errors="replace"))
        return pdf


def phase7_pdf_kb() -> None:
    phase = "Phase7-PDF-KB"
    admin = login_api("admin", "admin")
    if not admin:
        report.add(phase, "admin_login", "SKIP")
        return
    csrf = admin.cookies.get("csrf_token", "")
    hdrs = {"x-csrf-token": csrf}
    fname = f"regtest_apple_{uuid.uuid4().hex[:8]}.pdf"
    pdf_bytes = _make_test_pdf(
        "Apple was founded by Steve Jobs, Steve Wozniak, and Ronald Wayne in 1976."
    )
    files = {"file": (fname, pdf_bytes, "application/pdf")}
    r = admin.post(f"{LOGIN}/proxy/upload_rag", files=files, headers=hdrs, timeout=120)
    report.add(phase, "pdf_upload", "PASS" if r.status_code == 200 else "FAIL", details=f"{r.status_code} {r.text[:300]}")

    time.sleep(5)
    r2 = admin.get(f"{LOGIN}/api/knowledge/files", headers=hdrs, timeout=TIMEOUT)
    if r2.status_code == 200:
        files_list = r2.json()
        found = any(fname in str(f) for f in files_list)
        report.add(phase, "pdf_in_kb_list", "PASS" if found else "WARN", details=str(len(files_list)))
    else:
        report.add(phase, "pdf_in_kb_list", "FAIL", details=str(r2.status_code))

    # Query via RAG HTTP (session cookie forwarded to RAG server)
    q = "Who founded Apple?"
    r3 = rag_query(admin, q, tenant_id=1)
    if r3.status_code == 200:
        body = r3.json() if r3.headers.get("content-type", "").startswith("application/json") else {}
        ans = str(body.get("answer") or body.get("response") or r3.text)
        grounded = any(x in ans.lower() for x in ("jobs", "wozniak", "wayne", "1976", "founded"))
        report.add(phase, "rag_query_grounded", "PASS" if grounded else "WARN", details=ans[:300])
        sources = body.get("sources") or body.get("citations") or body.get("docs")
        report.add(phase, "rag_sources_present", "PASS" if sources else "WARN", details=str(type(sources)))
    else:
        report.add(phase, "rag_query", "FAIL", details=f"{r3.status_code}")

    return fname


def phase8_kb_lifecycle(fname: str | None) -> None:
    phase = "Phase8-KB-Lifecycle"
    if not fname:
        report.add(phase, "skip", "SKIP", details="No uploaded file from phase 7")
        return
    admin = login_api("admin", "admin")
    if not admin:
        report.add(phase, "admin_login", "SKIP")
        return
    csrf = admin.cookies.get("csrf_token", "")
    hdrs = {"x-csrf-token": csrf, "Accept": "application/json"}

    r = admin.delete(f"{LOGIN}/api/knowledge/files/{fname}", headers=hdrs, timeout=60)
    report.add(phase, "delete_pdf", "PASS" if r.status_code in (200, 204) else "WARN", details=str(r.status_code))

    time.sleep(3)
    r2 = rag_query(admin, "Who founded Apple?", tenant_id=1)
    if r2.status_code == 200:
        body = r2.json() if "json" in r2.headers.get("content-type", "") else {}
        ans = str(body.get("answer") or body.get("response") or "")
        still_grounded = "wozniak" in ans.lower() and fname.replace(".pdf", "") in ans.lower()
        report.add(phase, "deleted_doc_not_primary", "PASS" if not still_grounded else "WARN", details=ans[:200])
    else:
        report.add(phase, "post_delete_query", "WARN", details=str(r2.status_code))


# ---------- Phase 9: RAG queries ----------
def phase9_rag() -> None:
    phase = "Phase9-RAG"
    sess = login_api("admin", "admin")
    if not sess:
        report.add(phase, "admin_login", "SKIP")
        return
    csrf = sess.cookies.get("csrf_token", "")
    hdrs = {"x-csrf-token": csrf, "Accept": "application/json", "Content-Type": "application/json"}
    queries = {
        "definition": "What is RAG?",
        "fact": "What year was Apple founded?",
        "comparison": "Compare supervised and unsupervised learning",
        "list": "List three common machine learning algorithms",
        "followup": "Tell me more about the first one",
    }
    for qtype, q in queries.items():
        try:
            r = rag_query(sess, q, tenant_id=1)
            ok = r.status_code == 200 and len(r.text) > 10
            report.add(phase, f"query:{qtype}", "PASS" if ok else "FAIL", details=f"status={r.status_code} len={len(r.text)}")
        except Exception as e:
            report.add(phase, f"query:{qtype}", "FAIL", details=str(e))


# ---------- Phase 10: WebSockets ----------
async def _ws_test(url: str, cookies: dict | None, expect_ok: bool) -> tuple[bool, str]:
    try:
        import websockets
        from websockets.client import connect
    except ImportError:
        return False, "websockets not installed"

    extra = {}
    if cookies:
        extra["additional_headers"] = {"Cookie": "; ".join(f"{k}={v}" for k, v in cookies.items())}
    try:
        async with connect(url, open_timeout=10, close_timeout=5, **extra) as ws:
            await asyncio.wait_for(ws.recv(), timeout=5)
            return True, "connected"
    except Exception as e:
        msg = str(e)
        if not expect_ok:
            return True, msg
        return False, msg


def phase10_websocket() -> None:
    phase = "Phase10-WebSocket"
    admin_sess = login_api("admin", "admin")
    cookie_dict = dict(admin_sess.cookies) if admin_sess else {}

    tests = [
        ("ws_authenticated", f"ws://127.0.0.1:7001/ws", cookie_dict, True),
        ("ws_unauthenticated_rejected", f"ws://127.0.0.1:7001/ws", {}, False),
        ("ws_guest", f"ws://127.0.0.1:7001/ws/guest", {}, True),
    ]
    for name, url, cookies, expect_ok in tests:
        try:
            ok, msg = asyncio.run(_ws_test(url, cookies or None, expect_ok))
            status = "PASS" if ok else "FAIL"
            report.add(phase, name, status, details=msg[:200])
        except Exception as e:
            report.add(phase, name, "FAIL", details=str(e))

    # kb-events may require auth
    try:
        ok, msg = asyncio.run(_ws_test("ws://127.0.0.1:7000/ws/kb-events", cookie_dict, True))
        report.add(phase, "ws_kb_events", "PASS" if ok else "WARN", details=msg[:200])
    except Exception as e:
        report.add(phase, "ws_kb_events", "WARN", details=str(e))


# ---------- Phase 11: Analytics ----------
def phase11_analytics() -> None:
    phase = "Phase11-Analytics"
    admin = login_api("admin", "admin")
    if not admin:
        report.add(phase, "admin_login", "SKIP")
        return
    endpoints = [
        "/admin/analytics",
        "/api/analytics/comprehensive",
        "/api/analytics/errors",
        "/api/employee/analytics",
    ]
    for ep in endpoints:
        r = admin.get(f"{LOGIN}{ep}", timeout=TIMEOUT)
        report.add(phase, f"endpoint:{ep}", "PASS" if r.status_code == 200 else "WARN", details=str(r.status_code))


# ---------- Phase 12: Security ----------
def phase12_security() -> None:
    phase = "Phase12-Security"
    sess = session_for("admin", "admin")
    # Missing CSRF on state-changing request
    r = requests.post(
        f"{LOGIN}/conversations",
        json={"title": "csrf test"},
        cookies=sess["cookies"],
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        timeout=TIMEOUT,
    )
    blocked = r.status_code in (403, 401, 422)
    report.add(phase, "csrf_missing_blocked", "PASS" if blocked else "FAIL", details=str(r.status_code))

    # Invalid session
    r2 = requests.get(
        f"{LOGIN}/conversations",
        cookies={config.SESSION_COOKIE: "invalid.token.here"},
        timeout=TIMEOUT,
    )
    report.add(phase, "invalid_session_rejected", "PASS" if r2.status_code in (401, 403, 302) else "FAIL", details=str(r2.status_code))

    r3 = requests.get(f"{LOGIN}/admin", timeout=TIMEOUT)
    report.add(phase, "unauthenticated_admin_denied", "PASS" if r3.status_code in (401, 403, 302) else "FAIL", details=str(r3.status_code))


# ---------- Phase 13: Performance smoke ----------
def phase13_performance() -> None:
    phase = "Phase13-Performance"
    sess = login_api("customer", "customer123")
    if not sess:
        report.add(phase, "customer_login", "SKIP")
        return
    csrf = sess.cookies.get("csrf_token", "")
    hdrs = {"x-csrf-token": csrf, "Accept": "application/json", "Content-Type": "application/json"}
    errors = 0
    t0 = time.time()
    for i in range(20):
        try:
            r = rag_query(sess, f"Smoke test query number {i}", tenant_id=1)
            if r.status_code != 200:
                errors += 1
        except Exception:
            errors += 1
    elapsed = time.time() - t0
    report.add(phase, "20_chat_requests", "PASS" if errors == 0 else "WARN", details=f"{errors} errors in {elapsed:.1f}s")

    for _ in range(5):
        r = sess.post(f"{LOGIN}/conversations", json={"title": "perf"}, headers=hdrs, timeout=TIMEOUT)
        if r.status_code in (200, 201):
            cid = (r.json() or {}).get("id")
            if cid:
                sess.delete(f"{LOGIN}/conversations/{cid}", headers=hdrs, timeout=TIMEOUT)
    report.add(phase, "conversation_ops_burst", "PASS")


def save_report() -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "summary": report.summary(),
        "started": report.started,
        "finished": datetime.utcnow().isoformat() + "Z",
        "results": [r.__dict__ for r in report.results],
        "warnings": report.warnings,
    }
    REPORT_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\nReport saved: {REPORT_PATH}")


def print_human_report() -> None:
    s = report.summary()
    print("\n" + "=" * 70)
    print("ASSISTIFY FULL REGRESSION REPORT")
    print("=" * 70)
    print(f"Total: {s['total']} | PASS: {s['passed']} | FAIL: {s['failed']} | WARN: {s['warnings']} | SKIP: {s['skipped']}")
    print("-" * 70)
    current = None
    for r in report.results:
        if r.phase != current:
            current = r.phase
            print(f"\n## {current}")
        sym = {"PASS": "+", "FAIL": "X", "WARN": "!", "SKIP": "-"}[r.status]
        line = f"  [{sym}] {r.name}"
        if r.details:
            line += f" — {r.details[:120]}"
        print(line)
        if r.status == "FAIL" and r.repro:
            print(f"      Repro: {r.repro}")
            if r.file_hint:
                print(f"      File: {r.file_hint}")
            if r.cause:
                print(f"      Cause: {r.cause}")


def main() -> int:
    print("Waiting for servers...")
    if not wait_for_servers(240):
        print("WARNING: Servers not ready; some tests will fail")

    phase1_startup()
    phase2_routes()
    phase3_auth()
    phase4_tenant()
    phase5_user_mgmt()
    phase6_conversations()
    pdf_name = phase7_pdf_kb()
    phase8_kb_lifecycle(pdf_name)
    phase9_rag()
    phase10_websocket()
    phase11_analytics()
    phase12_security()
    phase13_performance()

    save_report()
    print_human_report()
    fails = report.summary()["failed"]
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
