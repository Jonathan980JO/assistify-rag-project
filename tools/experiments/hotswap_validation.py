"""Full PDF Hot-Swap Validation runner.

Hits the REAL WebSocket endpoint at ws://127.0.0.1:7000/ws and the REAL
HTTP /upload_rag and /rag/delete endpoints on the same RAG server.

NO simulation, NO direct internal calls.
"""
import asyncio
import json
import sys
import time
import uuid
from pathlib import Path

# Force UTF-8 stdout so the upload response (which contains a check mark)
# does not crash on Windows cp1252 consoles.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import requests
import websockets
from itsdangerous import URLSafeSerializer

# Project import
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import config  # noqa: E402

RAG_HOST = "http://127.0.0.1:7000"
WS_URI = "ws://127.0.0.1:7000/ws"
PDF_DIR = Path(r"C:\Users\MK\Desktop\Notes\PDF\Best")
MGMT_PDF = PDF_DIR / "Principles_of_Management.pdf"
PSY_PDF = PDF_DIR / "Introduction to Psychology  (Complete) (14).pdf"

# Build admin session token (matches scripts/upload_principles.py pattern)
_serializer = URLSafeSerializer(config.SESSION_SECRET)
ADMIN_TOKEN = _serializer.dumps({"username": "admin", "role": "admin"})
CSRF = uuid.uuid4().hex
AUTH_COOKIES = {config.SESSION_COOKIE: ADMIN_TOKEN, "csrf_token": CSRF}
AUTH_HEADERS = {"x-csrf-token": CSRF}


# -----------------------------------------------------------------
# WS helper
# -----------------------------------------------------------------
async def ws_query(ws, text: str, timeout: float = 90.0) -> str:
    """Send a typed-text query and wait for aiResponseDone.fullText."""
    await ws.send(json.dumps({"text": text}))
    full = ""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        try:
            msg = await asyncio.wait_for(ws.recv(), timeout=remaining)
        except asyncio.TimeoutError:
            return full or "<TIMEOUT>"
        try:
            data = json.loads(msg)
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        t = data.get("type")
        if t == "aiResponseDone":
            return data.get("fullText", full).strip()
        if t == "aiResponseChunk" and data.get("done"):
            full = data.get("text", full)
    return full or "<NO_RESPONSE>"


# -----------------------------------------------------------------
# HTTP helpers
# -----------------------------------------------------------------
def http_upload(pdf_path: Path) -> dict:
    with pdf_path.open("rb") as f:
        files = {"file": (pdf_path.name, f, "application/pdf")}
        r = requests.post(
            f"{RAG_HOST}/upload_rag",
            files=files,
            cookies=AUTH_COOKIES,
            headers=AUTH_HEADERS,
            timeout=600,
        )
    try:
        return {"status": r.status_code, "json": r.json()}
    except Exception:
        return {"status": r.status_code, "text": r.text[:400]}


def http_delete(doc_prefix: str) -> dict:
    r = requests.post(
        f"{RAG_HOST}/rag/delete",
        params={"doc_prefix": doc_prefix},
        cookies=AUTH_COOKIES,
        headers=AUTH_HEADERS,
        timeout=120,
    )
    try:
        return {"status": r.status_code, "json": r.json()}
    except Exception:
        return {"status": r.status_code, "text": r.text[:400]}


def rag_ready_state() -> dict:
    r = requests.get(
        f"{RAG_HOST}/rag/ready",
        cookies=AUTH_COOKIES,
        headers=AUTH_HEADERS,
        timeout=10,
    )
    return r.json()


def set_doc_mode(mode: str) -> dict:
    r = requests.post(
        f"{RAG_HOST}/rag/doc-mode",
        json={"mode": mode},
        cookies=AUTH_COOKIES,
        headers=AUTH_HEADERS,
        timeout=10,
    )
    return r.json()


def list_assets() -> list:
    r = requests.get(
        f"{RAG_HOST}/rag/files",
        cookies=AUTH_COOKIES,
        headers=AUTH_HEADERS,
        timeout=10,
    )
    try:
        j = r.json()
    except Exception:
        return []
    if isinstance(j, dict):
        for k in ("files", "items", "data"):
            if k in j and isinstance(j[k], list):
                return j[k]
    return j if isinstance(j, list) else []


def find_active_doc_filename(target_basename: str) -> str:
    """Find the actual stored filename containing the basename keyword."""
    target_low = target_basename.lower().split(".")[0]
    for entry in list_assets():
        name = entry.get("filename") or entry.get("name") or ""
        if target_low in name.lower():
            return name
    return ""


def wait_for_ready(timeout: float = 600.0, poll: float = 0.25) -> dict:
    """Poll /rag/ready until ready=True. Returns final state + elapsed."""
    t0 = time.monotonic()
    last = {}
    while time.monotonic() - t0 < timeout:
        try:
            last = rag_ready_state()
        except Exception as e:
            last = {"error": str(e)}
        if last.get("ready"):
            return {"state": last, "elapsed": time.monotonic() - t0}
        time.sleep(poll)
    return {"state": last, "elapsed": time.monotonic() - t0, "timed_out": True}


# -----------------------------------------------------------------
# Reporting
# -----------------------------------------------------------------
RESULTS = []


def record(phase: str, label: str, query: str, response: str, expectation: str, passed: bool, extra: dict = None):
    rec = {
        "phase": phase,
        "label": label,
        "query": query,
        "response": response,
        "expectation": expectation,
        "passed": passed,
        "extra": extra or {},
    }
    RESULTS.append(rec)
    status = "PASS" if passed else "FAIL"
    print(f"\n[{status}] {phase} {label}")
    print(f"  Q: {query}")
    snippet = response.replace("\n", " ")[:400]
    print(f"  A: {snippet}")
    if extra:
        print(f"  extra: {extra}")


def is_loading_response(text: str) -> bool:
    return "loading the document" in text.lower()


def is_not_found(text: str) -> bool:
    t = text.strip().lower()
    return t.startswith("not found in the document")


def mentions_any(text: str, terms) -> bool:
    low = text.lower()
    return any(term.lower() in low for term in terms)


# Domain leak terms for cross-document validation. Used ONLY to detect
# contamination in test responses; not injected into the system.
PSY_LEAK_TERMS = ["psychology", "wundt", "structuralism", "behaviorism",
                  "cognitive", "psychologist"]
MGMT_LEAK_TERMS = ["management", "scientific management", "taylor", "fayol",
                   "six ms", "manpower"]


# -----------------------------------------------------------------
# Main
# -----------------------------------------------------------------
async def main():
    print("=" * 70)
    print("FULL PDF HOT-SWAP VALIDATION")
    print(f"Management PDF : {MGMT_PDF.name}")
    print(f"Psychology PDF : {PSY_PDF.name}")
    print("=" * 70)

    # Pre-flight: assert mgmt is the currently active doc; if not, upload it.
    # Force single-doc mode so the documented hot-swap reset semantics apply
    # (blue/green collection swap, asset overwrite, active_sources isolation).
    mode_res = set_doc_mode("single")
    print(f"\nForced doc-mode -> single: {mode_res}")

    pre_state = rag_ready_state()
    print(f"\nPre-flight /rag/ready: ready={pre_state.get('ready')} "
          f"active_sources={pre_state.get('active_sources')} "
          f"state={pre_state.get('state', {}).get('state')} "
          f"mode={pre_state.get('doc_mode')}")
    active = pre_state.get("active_sources") or []
    has_mgmt = any("management" in s.lower() or "principles" in s.lower() for s in active)
    if not has_mgmt:
        print("Pre-flight: management PDF not active — uploading it first.")
        # Best-effort: clear any other active doc
        for src in active:
            try:
                http_delete(src)
            except Exception:
                pass
        up = http_upload(MGMT_PDF)
        print(f"  upload mgmt: {up}")
        ready = wait_for_ready(timeout=600)
        print(f"  ready after pre-flight upload in {ready['elapsed']:.1f}s")

    # ============================================================
    # PHASE 1 — MANAGEMENT PDF — same connection
    # ============================================================
    print("\n\n========== PHASE 1 — MANAGEMENT PDF ==========")
    async with websockets.connect(WS_URI, max_size=8 * 1024 * 1024) as ws_a:
        q1 = "What is scientific management?"
        a1 = await ws_query(ws_a, q1)
        leak = mentions_any(a1, PSY_LEAK_TERMS) and not mentions_any(a1, MGMT_LEAK_TERMS)
        record("PHASE1", "Q1", q1, a1, "grounded in management", not is_loading_response(a1) and not is_not_found(a1) and not leak)

        q2 = "What are the six Ms of management?"
        a2 = await ws_query(ws_a, q2)
        record("PHASE1", "Q2", q2, a2, "grounded in management", not is_loading_response(a2) and not is_not_found(a2) and not mentions_any(a2, PSY_LEAK_TERMS))

        q3 = "What are the characteristics of management?"
        a3 = await ws_query(ws_a, q3)
        record("PHASE1", "Q3", q3, a3, "grounded in management", not is_loading_response(a3) and not is_not_found(a3) and not mentions_any(a3, PSY_LEAK_TERMS))

        q4 = "explain more"
        a4 = await ws_query(ws_a, q4)
        record("PHASE1", "Q4", q4, a4, "follow-up grounded in management", not is_loading_response(a4) and not is_not_found(a4) and not mentions_any(a4, PSY_LEAK_TERMS))

        # ============================================================
        # PHASE 2 — SWAP TO PSYCHOLOGY (start timer)
        # ============================================================
        print("\n\n========== PHASE 2 — SWAP TO PSYCHOLOGY ==========")
        active_now = rag_ready_state().get("active_sources") or []
        mgmt_filename = active_now[0] if active_now else find_active_doc_filename("management") or find_active_doc_filename("principles")
        print(f"Removing active mgmt doc: {mgmt_filename}")
        del_res = http_delete(mgmt_filename)
        print(f"  delete result: {del_res}")

        swap_t0 = time.monotonic()  # 🔥 START TIMER
        upload_t0 = time.monotonic()
        print(f"Uploading psychology PDF...")
        up_res = http_upload(PSY_PDF)
        upload_t1 = time.monotonic()
        upload_elapsed = upload_t1 - upload_t0
        print(f"  upload returned in {upload_elapsed:.2f}s: {up_res.get('status')} {str(up_res.get('json'))[:200]}")

        # IMMEDIATELY ask Q5 on SAME connection
        q5 = "What is psychology?"
        t_q5 = time.monotonic()
        a5 = await ws_query(ws_a, q5, timeout=15)
        record("PHASE2", "Q5", q5, a5,
               "loading message during indexing",
               is_loading_response(a5),
               extra={"asked_after_upload_ms": int((t_q5 - upload_t1) * 1000)})

        # ============================================================
        # PHASE 3 — wait until ready, then ask
        # ============================================================
        print("\n\n========== PHASE 3 — PSYCHOLOGY ACTIVE ==========")
        ready_info = wait_for_ready(timeout=600)
        swap_t1 = time.monotonic()  # 🔥 STOP TIMER
        swap_AtoB_seconds = swap_t1 - swap_t0
        print(f"Ready in {ready_info['elapsed']:.2f}s after upload, "
              f"total swap A->B: {swap_AtoB_seconds:.2f}s")
        print(f"  active_sources={ready_info['state'].get('active_sources')}")
        print(f"  active_collection={ready_info['state'].get('active_collection')} "
              f"chunks={ready_info['state'].get('active_collection_chunks')}")

    # NEW connection (fresh-session) for psychology phase
    async with websockets.connect(WS_URI, max_size=8 * 1024 * 1024) as ws_b:
        q6 = "What is psychology?"
        a6 = await ws_query(ws_b, q6)
        ok6 = (not is_loading_response(a6) and not is_not_found(a6)
               and mentions_any(a6, ["psychology"])
               and not mentions_any(a6, ["scientific management", "six ms", "fayol", "taylor"]))
        record("PHASE3", "Q6", q6, a6, "psychology answer, no mgmt leak", ok6)

        q7 = "What are the goals of psychology?"
        a7 = await ws_query(ws_b, q7)
        ok7 = (not is_not_found(a7)
               and not mentions_any(a7, ["scientific management", "six ms", "fayol", "taylor"]))
        record("PHASE3", "Q7", q7, a7, "psychology answer, no mgmt leak", ok7)

        q8 = "Who established the first psychological laboratory and when?"
        a8 = await ws_query(ws_b, q8)
        ok8 = (not is_not_found(a8)
               and not mentions_any(a8, ["scientific management", "six ms", "fayol", "taylor"]))
        record("PHASE3", "Q8", q8, a8, "psychology answer, no mgmt leak", ok8)

        q9 = "explain more"
        a9 = await ws_query(ws_b, q9)
        ok9 = (not is_not_found(a9)
               and not mentions_any(a9, ["scientific management", "six ms", "fayol", "taylor"]))
        record("PHASE3", "Q9", q9, a9, "follow-up psychology, no mgmt leak", ok9)

        # ============================================================
        # PHASE 4 — LEAK TEST
        # ============================================================
        print("\n\n========== PHASE 4 — LEAK TEST ==========")
        q10 = "What is scientific management?"
        a10 = await ws_query(ws_b, q10)
        record("PHASE4", "Q10", q10, a10,
               "Not found in the document.",
               is_not_found(a10))

        # ============================================================
        # PHASE 5 — SWAP BACK TO MANAGEMENT
        # ============================================================
        print("\n\n========== PHASE 5 — SWAP BACK TO MANAGEMENT ==========")
        active_now = rag_ready_state().get("active_sources") or []
        psy_filename = active_now[0] if active_now else find_active_doc_filename("psychology")
        print(f"Removing active psychology doc: {psy_filename}")
        del_res2 = http_delete(psy_filename)
        print(f"  delete result: {del_res2}")

        swap_t0_b = time.monotonic()  # 🔥 START TIMER
        upload_t0_b = time.monotonic()
        print(f"Uploading management PDF...")
        up_res2 = http_upload(MGMT_PDF)
        upload_t1_b = time.monotonic()
        upload_elapsed_b = upload_t1_b - upload_t0_b
        print(f"  upload returned in {upload_elapsed_b:.2f}s")

        q11 = "What is scientific management?"
        t_q11 = time.monotonic()
        a11 = await ws_query(ws_b, q11, timeout=15)
        record("PHASE5", "Q11", q11, a11,
               "loading message during indexing",
               is_loading_response(a11),
               extra={"asked_after_upload_ms": int((t_q11 - upload_t1_b) * 1000)})

        ready_info2 = wait_for_ready(timeout=600)
        swap_t1_b = time.monotonic()  # 🔥 STOP TIMER
        swap_BtoA_seconds = swap_t1_b - swap_t0_b
        print(f"Ready in {ready_info2['elapsed']:.2f}s after upload, "
              f"total swap B->A: {swap_BtoA_seconds:.2f}s")

    # NEW connection again for clean follow-up state on mgmt side
    async with websockets.connect(WS_URI, max_size=8 * 1024 * 1024) as ws_c:
        q12 = "What is scientific management?"
        a12 = await ws_query(ws_c, q12)
        ok12 = (not is_loading_response(a12) and not is_not_found(a12)
                and not mentions_any(a12, PSY_LEAK_TERMS))
        record("PHASE5", "Q12", q12, a12, "management answer, no psy leak", ok12)

        q13 = "explain more"
        a13 = await ws_query(ws_c, q13)
        ok13 = (not is_loading_response(a13)
                and not mentions_any(a13, PSY_LEAK_TERMS))
        record("PHASE5", "Q13", q13, a13, "follow-up mgmt, no psy leak", ok13)

        # ============================================================
        # PHASE 6 — FOLLOW-UP MEMORY TEST
        # ============================================================
        print("\n\n========== PHASE 6 — FOLLOW-UP MEMORY TEST ==========")
        q14 = "explain more"
        a14 = await ws_query(ws_c, q14)
        ok14 = (not mentions_any(a14, PSY_LEAK_TERMS))
        record("PHASE6", "Q14", q14, a14,
               "no psychology reference; mgmt only",
               ok14)

    # ============================================================
    # SUMMARY
    # ============================================================
    print("\n\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    pass_count = sum(1 for r in RESULTS if r["passed"])
    fail_count = len(RESULTS) - pass_count
    for r in RESULTS:
        status = "PASS" if r["passed"] else "FAIL"
        print(f"  [{status}] {r['phase']} {r['label']}: {r['query'][:60]}")
    print(f"\nTotal: {pass_count}/{len(RESULTS)} pass, {fail_count} fail")
    print(f"\nSwap A->B (mgmt -> psy): {swap_AtoB_seconds:.2f} s "
          f"(upload http roundtrip {upload_elapsed:.2f}s, ready-after-upload {ready_info['elapsed']:.2f}s)")
    print(f"Swap B->A (psy -> mgmt): {swap_BtoA_seconds:.2f} s "
          f"(upload http roundtrip {upload_elapsed_b:.2f}s, ready-after-upload {ready_info2['elapsed']:.2f}s)")

    out = {
        "results": RESULTS,
        "swap_AtoB_seconds": swap_AtoB_seconds,
        "swap_BtoA_seconds": swap_BtoA_seconds,
        "upload_AtoB_http_seconds": upload_elapsed,
        "upload_BtoA_http_seconds": upload_elapsed_b,
        "ready_after_upload_AtoB": ready_info["elapsed"],
        "ready_after_upload_BtoA": ready_info2["elapsed"],
        "ready_state_AtoB": ready_info["state"],
        "ready_state_BtoA": ready_info2["state"],
        "pass": pass_count,
        "fail": fail_count,
    }
    Path("hotswap_validation_results.json").write_text(
        json.dumps(out, indent=2, default=str), encoding="utf-8"
    )
    print("\nResults written to hotswap_validation_results.json")


if __name__ == "__main__":
    asyncio.run(main())
