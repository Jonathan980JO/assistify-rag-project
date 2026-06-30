#!/usr/bin/env python3
"""Automated health check for Assistify RAG stack (CLI).

Checks HTTP services, SQLite integrity/WAL, WebSocket ports, and RAG KB readiness.
Exit code 0 when all required checks pass; 1 when any FAIL.
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import sqlite3
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional
from urllib.error import URLError
from urllib.request import Request, urlopen

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

RAG_PORT = int(os.environ.get("RAG_SERVER_PORT", "7000"))
LOGIN_PORT = int(os.environ.get("LOGIN_SERVER_PORT", "7001"))
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "127.0.0.1")
OLLAMA_PORT = int(os.environ.get("OLLAMA_PORT", "11434"))
PIPER_PORT = int(os.environ.get("PIPER_PORT", "5002"))
LLM_PORT = int(os.environ.get("LLM_SERVER_PORT", str(getattr(__import__("config"), "LLM_SERVER_PORT", 8010))))

USERS_DB = REPO_ROOT / "Login_system" / "users.db"
CONVERSATIONS_DB = REPO_ROOT / "backend" / "conversations.db"
ANALYTICS_DB = REPO_ROOT / "backend" / "analytics.db"
CONVERSATIONS_JSON = REPO_ROOT / "backend" / "conversations.json"
CHROMA_DIR = REPO_ROOT / "backend" / "chroma_db_v3"


@dataclass
class CheckResult:
    name: str
    status: str  # OK | WARN | FAIL | SKIP
    detail: str = ""


def _http_get(url: str, timeout: float = 5.0) -> tuple[int, str]:
    req = Request(url, headers={"User-Agent": "assistify-system-health-check/1.0"})
    with urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8", errors="replace")
        return int(resp.status), body


def _tcp_open(host: str, port: int, timeout: float = 3.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _ws_handshake(host: str, port: int, path: str = "/ws", timeout: float = 5.0) -> tuple[bool, str]:
    """Best-effort WebSocket upgrade probe (stdlib only)."""
    try:
        sock = socket.create_connection((host, port), timeout=timeout)
    except OSError as exc:
        return False, str(exc)
    try:
        sock.sendall(
            (
                f"GET {path} HTTP/1.1\r\n"
                f"Host: {host}:{port}\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n"
                "Sec-WebSocket-Version: 13\r\n"
                "\r\n"
            ).encode("ascii")
        )
        sock.settimeout(timeout)
        data = sock.recv(4096)
        text = data.decode("utf-8", errors="replace")
        ok = "101" in text.split("\r\n", 1)[0]
        return ok, text.split("\r\n", 1)[0] if text else "no response"
    except OSError as exc:
        return False, str(exc)
    finally:
        sock.close()


def _check_sqlite(path: Path, *, expect_wal: bool = False) -> CheckResult:
    label = path.name
    if not path.exists():
        return CheckResult(f"DB {label}", "WARN", "file missing (may be created on first run)")

    wal_path = Path(str(path) + "-wal")
    journal_path = Path(str(path) + "-journal")
    stuck = []
    if journal_path.exists():
        stuck.append("-journal present")

    try:
        conn = sqlite3.connect(str(path), timeout=2.0)
        try:
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            quick = conn.execute("PRAGMA quick_check").fetchone()[0]
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("ROLLBACK")
        finally:
            conn.close()
    except sqlite3.OperationalError as exc:
        if "locked" in str(exc).lower():
            return CheckResult(f"DB {label}", "FAIL", f"database is locked: {exc}")
        return CheckResult(f"DB {label}", "FAIL", str(exc))
    except Exception as exc:
        return CheckResult(f"DB {label}", "FAIL", str(exc))

    status = "OK"
    notes = [f"journal_mode={mode}", f"quick_check={quick}"]
    if expect_wal and str(mode).lower() != "wal":
        status = "WARN"
        notes.append("expected WAL")
    if wal_path.exists() and wal_path.stat().st_size > 50 * 1024 * 1024:
        status = "WARN"
        notes.append(f"large WAL ({wal_path.stat().st_size // (1024 * 1024)}MB)")
    if stuck:
        status = "WARN"
        notes.extend(stuck)
    return CheckResult(f"DB {label}", status, "; ".join(notes))


def _check_rag_health() -> CheckResult:
    url = f"http://127.0.0.1:{RAG_PORT}/health"
    try:
        code, body = _http_get(url, timeout=15.0)
    except (URLError, TimeoutError, OSError) as exc:
        return CheckResult("RAG /health", "FAIL", str(exc))

    if code >= 500:
        return CheckResult("RAG /health", "FAIL", f"HTTP {code}")

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return CheckResult("RAG /health", "WARN", f"HTTP {code} non-JSON body")

    flags = {k: payload.get(k) for k in ("db", "kb", "llm", "tts", "asr")}
    kb_state = None
    if isinstance(payload.get("kb_pipeline"), dict):
        kb_state = payload["kb_pipeline"].get("state")
    elif isinstance(payload.get("kb_status"), dict):
        kb_state = payload["kb_status"].get("state")

    bad = [k for k, v in flags.items() if v is False]
    if bad:
        return CheckResult("RAG /health", "WARN", f"flags false: {bad}; payload={flags}")

    detail = f"HTTP {code}; flags={flags}"
    if kb_state and str(kb_state).lower() not in {"ready", "idle"}:
        return CheckResult("RAG /health", "WARN", f"{detail}; kb_state={kb_state}")
    return CheckResult("RAG /health", "OK", detail)


def _check_conversations_json() -> CheckResult:
    if not CONVERSATIONS_JSON.exists():
        return CheckResult("conversations.json", "WARN", "missing (created on first chat)")
    try:
        data = json.loads(CONVERSATIONS_JSON.read_text(encoding="utf-8"))
        count = len(data.get("conversations", [])) if isinstance(data, dict) else 0
        return CheckResult("conversations.json", "OK", f"valid JSON; conversations={count}")
    except Exception as exc:
        return CheckResult("conversations.json", "FAIL", str(exc))


def _check_chroma_dir() -> CheckResult:
    if not CHROMA_DIR.exists():
        return CheckResult("ChromaDB path", "WARN", f"missing: {CHROMA_DIR}")
    try:
        entries = list(CHROMA_DIR.iterdir())
        return CheckResult("ChromaDB path", "OK", f"{len(entries)} entries under chroma_db_v3")
    except Exception as exc:
        return CheckResult("ChromaDB path", "FAIL", str(exc))


def run_checks(*, require_piper: bool = True, require_ollama: bool = True) -> list[CheckResult]:
    results: list[CheckResult] = []

    def add(name: str, fn: Callable[[], CheckResult]) -> None:
        try:
            results.append(fn())
        except Exception as exc:
            results.append(CheckResult(name, "FAIL", str(exc)))

    add("Ollama", lambda: _service_ping(
        f"http://{OLLAMA_HOST}:{OLLAMA_PORT}/api/tags",
        "Ollama",
        required=require_ollama,
    ))
    add("LLM shim", lambda: _service_ping(
        f"http://127.0.0.1:{LLM_PORT}/internal/gpu-status",
        "LLM shim",
        required=False,
    ))
    add("Piper TTS", lambda: _service_ping(
        f"http://127.0.0.1:{PIPER_PORT}/health",
        "Piper TTS",
        required=require_piper,
    ))
    add("RAG server", _check_rag_health)
    add("Login server", lambda: _service_ping(
        f"http://127.0.0.1:{LOGIN_PORT}/login",
        "Login server",
        required=True,
    ))

    add("TCP RAG :7000", lambda: CheckResult(
        "TCP RAG port",
        "OK" if _tcp_open("127.0.0.1", RAG_PORT) else "FAIL",
        f"127.0.0.1:{RAG_PORT}",
    ))
    add("TCP Login :7001", lambda: CheckResult(
        "TCP Login port",
        "OK" if _tcp_open("127.0.0.1", LOGIN_PORT) else "FAIL",
        f"127.0.0.1:{LOGIN_PORT}",
    ))

    ok_ws_rag, ws_detail_rag = _ws_handshake("127.0.0.1", RAG_PORT, "/ws")
    results.append(CheckResult(
        "WS RAG /ws",
        "OK" if ok_ws_rag else "WARN",
        ws_detail_rag,
    ))
    ok_ws_login, ws_detail_login = _ws_handshake("127.0.0.1", LOGIN_PORT, "/ws")
    results.append(CheckResult(
        "WS Login /ws proxy",
        "OK" if ok_ws_login else "WARN",
        ws_detail_login,
    ))

    results.append(_check_sqlite(USERS_DB, expect_wal=True))
    results.append(_check_sqlite(CONVERSATIONS_DB, expect_wal=False))
    results.append(_check_sqlite(ANALYTICS_DB, expect_wal=False))
    results.append(_check_conversations_json())
    results.append(_check_chroma_dir())

    # Timed RAG responsiveness (vector stack indirectly via /health)
    t0 = time.perf_counter()
    try:
        code, _ = _http_get(f"http://127.0.0.1:{RAG_PORT}/health", timeout=10.0)
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        status = "OK" if code < 500 and elapsed_ms < 8000 else "WARN"
        results.append(CheckResult("RAG latency", status, f"{elapsed_ms}ms HTTP {code}"))
    except Exception as exc:
        results.append(CheckResult("RAG latency", "FAIL", str(exc)))

    return results


def _service_ping(url: str, name: str, *, required: bool) -> CheckResult:
    try:
        code, _ = _http_get(url, timeout=8.0)
        if code < 500:
            return CheckResult(name, "OK", f"HTTP {code}")
        return CheckResult(name, "FAIL" if required else "WARN", f"HTTP {code}")
    except Exception as exc:
        return CheckResult(name, "FAIL" if required else "SKIP", str(exc))


def _print_table(results: list[CheckResult]) -> None:
    width = max(len(r.name) for r in results) if results else 20
    print(f"\n{'CHECK'.ljust(width)}  STATUS  DETAIL")
    print("-" * (width + 40))
    for r in results:
        print(f"{r.name.ljust(width)}  {r.status.ljust(6)}  {r.detail}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Assistify system health check")
    parser.add_argument("--no-piper", action="store_true", help="Do not fail if Piper is down")
    parser.add_argument("--no-ollama", action="store_true", help="Do not fail if Ollama is down")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    args = parser.parse_args()

    results = run_checks(require_piper=not args.no_piper, require_ollama=not args.no_ollama)
    failures = [r for r in results if r.status == "FAIL"]

    if args.json:
        print(json.dumps([r.__dict__ for r in results], indent=2))
    else:
        print("Assistify System Health Check")
        print(f"Repo: {REPO_ROOT}")
        _print_table(results)
        if failures:
            print(f"\n{len(failures)} FAIL check(s).")
        else:
            print("\nAll required checks passed.")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
