#!/usr/bin/env python3
"""Quick local checks before starting Assistify servers."""
from __future__ import annotations

import socket
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def main() -> int:
    print(f"Project root: {REPO_ROOT}")
    ok = True

    try:
        import backend.sqlite_compat  # noqa: F401
        import sqlite3

        print(f"sqlite3: OK ({sqlite3.sqlite_version})")
    except Exception as exc:
        print(f"FAIL: sqlite3 not available ({exc})")
        print("  See docs/WINDOWS_TROUBLESHOOTING.md")
        return 1

    try:
        from config import (
            ASSETS_DIR,
            WHISPER_MODEL_PATH,
            WHISPER_MODEL_RESOLVED_PATH,
            WHISPER_MODEL_SOURCE,
        )
    except Exception as exc:
        print(f"FAIL: cannot import config ({exc})")
        return 1

    try:
        from scripts.ollama_bootstrap import resolve_ollama_exe, resolve_ollama_tray_exe

        ollama_cli = resolve_ollama_exe()
        cli_exists = Path(ollama_cli).exists() if ollama_cli else False
        print(f"Ollama CLI: {ollama_cli} -> {'OK' if cli_exists or ollama_cli == 'ollama' else 'MISSING'}")
        if not cli_exists and ollama_cli != "ollama":
            ok = False
        tray = resolve_ollama_tray_exe()
        if tray:
            print(f"Ollama tray: {tray} -> OK")
        else:
            print("Ollama tray: not found (install Ollama desktop app)")
    except Exception as exc:
        print(f"WARN: Ollama resolution failed ({exc})")

    whisper = Path(WHISPER_MODEL_PATH)
    if WHISPER_MODEL_SOURCE == "plain":
        print(f"Whisper path: {whisper} -> OK")
    elif WHISPER_MODEL_SOURCE == "cache":
        print(f"Whisper path: {whisper} -> OK (HF cache: {WHISPER_MODEL_RESOLVED_PATH})")
    else:
        print(f"Whisper path: {whisper} -> MISSING")
        ok = False

    en = REPO_ROOT / "models" / "piper" / "en" / "voice.onnx"
    ar = REPO_ROOT / "models" / "piper" / "ar" / "voice.onnx"
    print(f"Piper EN voice: {en} -> {'OK' if en.exists() else 'MISSING'}")
    print(f"Piper AR voice: {ar} -> {'OK' if ar.exists() else 'MISSING'}")
    if not en.exists() or not ar.exists():
        print("  (Voice TTS will report not_ready until Piper models exist)")

    chroma = REPO_ROOT / "backend" / "chroma_db_v3"
    print(f"Chroma v3: {chroma} -> {'OK' if chroma.is_dir() else 'MISSING'}")
    if chroma.is_dir():
        try:
            import chromadb

            client = chromadb.PersistentClient(path=str(chroma))
            names = client.list_collections()
            for name in names:
                col = client.get_collection(name)
                print(f"  collection {name!r}: {col.count()} chunks")
        except Exception as exc:
            print(f"  WARN: chroma read failed ({exc})")
    else:
        ok = False

    assets = Path(ASSETS_DIR)
    pdfs = list(assets.glob("*.pdf")) if assets.is_dir() else []
    print(f"Assets PDFs: {len(pdfs)}")
    try:
        from backend.knowledge_base import find_orphan_asset_files, get_or_create_collection

        orphans = find_orphan_asset_files(assets)
        if orphans:
            ok = False
            print(f"WARN: {len(orphans)} orphan asset(s) on disk with no indexed chunks:")
            for name in orphans[:10]:
                print(f"  - {name}")
            if len(orphans) > 10:
                print(f"  ... and {len(orphans) - 10} more")
            print("  Fix: re-upload PDFs in admin KB or POST /rag/reindex-all")
        else:
            col = get_or_create_collection(allow_empty=True)
            if col and pdfs:
                print(f"Assets index health: OK ({col.count()} chunks, {len(pdfs)} PDFs on disk)")
    except Exception as exc:
        msg = str(exc).lower()
        if "already exists" in msg and "chroma" in msg:
            print("Assets index health: skipped (RAG server holds Chroma lock — run verify_kb_retrieval.py)")
        else:
            print(f"WARN: orphan asset check failed ({exc})")

    llm_port = int(__import__("os").environ.get("LLM_SERVER_PORT", "8010"))
    try:
        from scripts.service_inventory import (
            LEGACY_PORTS,
            find_pids_on_port_windows,
            print_ollama_conflict_warnings,
        )

        print_ollama_conflict_warnings()
        legacy_up = [p for p in LEGACY_PORTS if find_pids_on_port_windows(p)]
        if legacy_up:
            print(
                f"WARN: Legacy ports still listening {legacy_up} — "
                "run start_main_servers.py with --kill-ports or close old FastAPI windows"
            )
    except Exception as exc:
        print(f"WARN: port conflict scan failed ({exc})")

    for port, label in ((11434, "Ollama"), (7000, "RAG"), (7001, "Login"), (llm_port, "LLM shim"), (5002, "Piper")):
        up = _port_open("127.0.0.1", port)
        print(f"Port {port} ({label}): {'listening' if up else 'down'}")
        if label == "Ollama" and not up:
            print("  (Expected before first start — launcher will start Ollama)")

    print("\nResult:", "READY TO START SERVERS" if ok else "FIX ISSUES ABOVE FIRST")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
