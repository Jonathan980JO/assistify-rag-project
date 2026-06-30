#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Assistify main server launcher.

Default on Windows: split-terminal mode (one window per service + coordinator).
Use --single-console for the merged-log launcher (CI / SSH).

Equivalent of the manual PowerShell sequence:

    cd "<repo root>"
    conda activate assistify_main
    $env:KMP_DUPLICATE_LIB_OK = "TRUE"
    python scripts\\project_start_split.py --kill-ports --llm-port 8010
"""
from __future__ import annotations

import os
import sys
import subprocess
from pathlib import Path

if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from scripts.react_ui_build import ensure_react_ui_built  # noqa: E402


PROJECT_ROOT = Path(__file__).resolve().parent
SPLIT_SCRIPT = PROJECT_ROOT / "scripts" / "project_start_split.py"
SINGLE_SCRIPT = PROJECT_ROOT / "scripts" / "project_start_server.py"
from scripts.python_env import CONDA_ENV_NAME, active_venv_missing_deps, python_env_label, resolve_project_python  # noqa: E402

DEFAULT_ARGS = ["--kill-ports", "--llm-port", "8010"]


def find_env_python() -> Path | None:
    resolved = resolve_project_python(PROJECT_ROOT)
    if resolved.exists():
        return resolved
    return None


def _resolve_target_script(extra_args: list[str]) -> Path:
    if "--single-console" in extra_args:
        return SINGLE_SCRIPT
    if os.name == "nt":
        return SPLIT_SCRIPT
    return SINGLE_SCRIPT


def print_startup_banner(*, single_console: bool, status_only: bool, public_tunnel: bool) -> None:
    print("====================================")
    print("  Assistify Main Server Launcher")
    print("====================================")
    if status_only:
        print("Mode: status inventory only (no services started)")
    elif single_console:
        print("Mode: single-console (merged logs)")
    else:
        print("Mode: multi-terminal (one window per service + this coordinator)")
    if public_tunnel:
        print("Public: HTTPS tunnel via cloudflared/ngrok (--public)")
    print()
    print("Services:")
    print("  Ollama      -> http://127.0.0.1:11434")
    print("  Piper TTS   -> http://127.0.0.1:5002  (skipped if --no-piper)")
    print("  LLM shim    -> http://127.0.0.1:8010")
    print("  RAG server  -> http://127.0.0.1:7000")
    print("  Login + UI  -> http://127.0.0.1:7001  (React app at /frontend/)")
    print("  Chat UI     -> http://127.0.0.1:7001/frontend/  (after login)")
    if not status_only and not single_console:
        print()
        if public_tunnel:
            print("When Ready: local + public URLs printed below (install cloudflared or ngrok)")
            print("  Service logs: mirrored to logs/*.log + /internal/service-logs (login required)")
        else:
            print("Open when Ready: http://127.0.0.1:7001/login")
            print("  Chat UI:     http://127.0.0.1:7001/frontend/")
        print("  Bootstrap login: superadmin / superadmin")
        print()
        print("Public internet access: python start_main_servers.py --public")
        print("Fast backend-only restart: python start_main_servers.py --skip-ui-build")
        print("If Ollama bind errors: python start_main_servers.py --restart-ollama")
        print("After startup:           python scripts/verify_stack.py")
        print()
        print("Coordinator opens five windows every run: Ollama, Piper, LLM, RAG, Login.")
        print("With --kill-ports, old Assistify * windows are closed before restart.")
        print("Ollama window shows status/models if the tray app already owns port 11434.")
        print("Close each service window to stop that service.")
        print("First RAG boot may take several minutes (Whisper model load).")
        print("First voice use may download Whisper small.en (~460MB one-time).")
    print("------------------------------------")


def _child_args(extra_args: list[str], *, ui_built: bool) -> list[str]:
    """Forward CLI args to the coordinator; avoid duplicate UI builds after start_main built."""
    child = list(extra_args)
    if ui_built and "--skip-ui-build" not in child and "--ui-build-only" not in child:
        child.append("--skip-ui-build")
    return child


def run_via_conda(target: Path, extra_args: list[str], *, ui_built: bool = False) -> int:
    print(f"[LAUNCHER] Falling back to 'conda run -n {CONDA_ENV_NAME}'...")
    cmd = [
        "conda", "run", "--no-capture-output", "-n", CONDA_ENV_NAME,
        "python", str(target), *DEFAULT_ARGS, *_child_args(extra_args, ui_built=ui_built),
    ]
    try:
        return subprocess.call(cmd, cwd=str(PROJECT_ROOT))
    except FileNotFoundError:
        print(
            "[ERROR] Could not find the 'assistify_main' conda environment or the "
            "'conda' command on PATH.",
            file=sys.stderr,
        )
        return 1


def main() -> int:
    os.chdir(PROJECT_ROOT)
    os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

    extra_args = sys.argv[1:]
    status_only = "--status" in extra_args
    single_console = "--single-console" in extra_args
    public_tunnel = "--public" in extra_args
    target = _resolve_target_script(extra_args)

    if not target.exists():
        print(f"[ERROR] Target script not found: {target}", file=sys.stderr)
        return 1

    print_startup_banner(
        single_console=single_console,
        status_only=status_only,
        public_tunnel=public_tunnel,
    )

    skip_ui_build = "--skip-ui-build" in extra_args
    ui_build_only = "--ui-build-only" in extra_args
    ui_built = False

    if ui_build_only:
        ok = ensure_react_ui_built(skip=skip_ui_build)
        return 0 if ok else 1

    if not status_only:
        print("[LAUNCHER] Building React UI for /frontend/ ...")
        if not ensure_react_ui_built(skip=skip_ui_build):
            print("[LAUNCHER] React UI build failed — aborting startup.", file=sys.stderr)
            return 1
        ui_built = not skip_ui_build

    env_python = find_env_python()
    if env_python is None:
        return run_via_conda(target, extra_args, ui_built=ui_built)

    python_label = python_env_label(env_python)
    if active_venv_missing_deps(PROJECT_ROOT):
        print(
            "[LAUNCHER] Note: .venv is active but missing packages (e.g. fastapi) — "
            "using conda:assistify_main for services.",
            file=sys.stderr,
        )
    print(f"[LAUNCHER] Repo root : {PROJECT_ROOT}")
    print(f"[LAUNCHER] Python env: {python_label}")
    print(f"[LAUNCHER] Python    : {env_python}")
    print(f"[LAUNCHER] Script    : {target.name}")
    print(f"[LAUNCHER] KMP_DUPLICATE_LIB_OK = {os.environ['KMP_DUPLICATE_LIB_OK']}")

    cmd = [str(env_python), str(target), *DEFAULT_ARGS, *_child_args(extra_args, ui_built=ui_built)]
    print(f"[LAUNCHER] Running   : {' '.join(cmd)}")
    print("------------------------------------")

    try:
        return subprocess.call(cmd, cwd=str(PROJECT_ROOT))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
