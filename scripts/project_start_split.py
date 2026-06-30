#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Assistify split-terminal launcher (Windows).

Phase 1: Scan and print process inventory.
Phase 2: Optionally free occupied ports (--kill-ports).
Phase 3: Open one cmd window per service, sequentially with readiness gating.
Phase 4: Coordinator polls health after each spawn.

Non-Windows: falls back to scripts/project_start_server.py (single console).
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.service_inventory import (  # noqa: E402
    LEGACY_PORTS,
    PORT_OLLAMA,
    PORT_PIPER,
    close_assistify_service_windows,
    default_service_specs,
    find_pids_on_port_windows,
    kill_listeners_on_ports,
    print_inventory_table,
    print_ollama_conflict_warnings,
    scan_services,
)
from scripts.project_start_server import (  # noqa: E402
    IS_WINDOWS,
    REPO_ROOT as _REPO,
    SERVICES,
    _host_for_check,
    _piper_voice_env,
    ensure_cwd_and_path,
    http_check,
    parse_args,
    wait_for_port,
)
from scripts.ollama_bootstrap import (  # noqa: E402
    ensure_ollama_model,
    ensure_ollama_running,
    ollama_http_ready,
    ollama_port_ready,
    print_ollama_failure_hints,
    resolve_ollama_exe,
)
from scripts.react_ui_build import ensure_react_ui_built  # noqa: E402
from scripts.public_tunnel import PublicTunnel, print_access_urls  # noqa: E402
from scripts.launch_windows.write_launch_scripts import (  # noqa: E402
    LAUNCH_DIR,
    write_service_bats,
)
from scripts.python_env import python_env_label, resolve_project_python  # noqa: E402

assert REPO_ROOT == _REPO

SPAWN_SETTLE_SEC = 1.5
PORT_KILL_SETTLE_SEC = 0.5

_LOGIN_PORT_HINT = (
    "Port 7001 already in use — close other Assistify Login windows or run with --kill-ports."
)


def ensure_sqlite3_or_exit() -> None:
    """Fail fast before spawning RAG/Login if sqlite3 native DLL is blocked."""
    try:
        import backend.sqlite_compat  # noqa: F401
        import sqlite3

        print(f"[COORDINATOR] sqlite3 OK ({sqlite3.sqlite_version})")
    except Exception as exc:
        print()
        print("[COORDINATOR] FATAL: sqlite3 is not available — RAG and Login cannot start.")
        print(f"  {exc}")
        print("  Run: python scripts/preflight_check.py")
        print("  See: docs/WINDOWS_TROUBLESHOOTING.md")
        print()
        raise SystemExit(1)


def spawn_bat_window(title: str, bat_path: Path) -> None:
    """Open a new cmd window that runs a service batch file.

    Avoid Windows ``START`` title parsing (``Assistify Piper`` runs ``Piper`` as a
    command). ``CREATE_NEW_CONSOLE`` opens a visible window; each bat sets ``title``.
    """
    bat = str(bat_path.resolve())
    subprocess.Popen(
        ["cmd", "/k", bat],
        cwd=str(REPO_ROOT),
        creationflags=subprocess.CREATE_NEW_CONSOLE,
    )
    print(f"[LAUNCHER] Opened window: {title}")


def build_rag_env(args) -> dict:
    rag_env = {
        "WHISPER_DEVICE": "cpu",
        "WHISPER_COMPUTE_TYPE": "int8",
        "RAG_USE_GPU": "1",
    }
    if args.use_whisper:
        rag_env["USE_WHISPER"] = "1"
    if args.whisper_model:
        rag_env["WHISPER_MODEL"] = args.whisper_model
    if args.whisper_chunk_ms:
        rag_env["WHISPER_CHUNK_MS"] = str(args.whisper_chunk_ms)
    return rag_env


def generate_launch_bats(args, python_exe: str) -> dict[str, Path]:
    capture_logs = args.service_logs or args.public
    return write_service_bats(
        REPO_ROOT,
        python_exe,
        llm=SERVICES[0],
        rag=SERVICES[1],
        login=SERVICES[2],
        rag_env=build_rag_env(args),
        piper_env=_piper_voice_env() or {},
        reload_flag=args.reload,
        capture_logs=capture_logs,
    )


def apply_cli_overrides(args) -> None:
    if args.llm_host is not None:
        SERVICES[0]["host"] = args.llm_host
    if args.rag_host is not None:
        SERVICES[1]["host"] = args.rag_host
    if args.login_host is not None:
        SERVICES[2]["host"] = args.login_host
    if args.llm_port is not None:
        SERVICES[0]["port"] = args.llm_port
    if args.rag_port is not None:
        SERVICES[1]["port"] = args.rag_port
    if args.login_port is not None:
        SERVICES[2]["port"] = args.login_port


async def wait_service_ready(name: str, host: str, port: int, ready_path: str, quick: bool) -> bool:
    if quick:
        timeout = 30.0
    elif name in ("LLM", "OLLAMA"):
        timeout = 120.0
    elif name == "RAG":
        timeout = 600.0
    else:
        timeout = 60.0

    check_host = _host_for_check(host)
    if not await wait_for_port(check_host, port, timeout=timeout):
        print(f"[{name}] Port {port} did not open in time.")
        return False

    if ready_path:
        url = f"http://{check_host}:{port}{ready_path}"
        for _ in range(30):
            if await http_check(url):
                print(f"[{name}] Ready on http://{host}:{port}")
                return True
            await asyncio.sleep(1.0)
        print(f"[{name}] Warning: health check {ready_path} did not respond; port is open.")
        return True

    print(f"[{name}] Ready on http://{host}:{port}")
    return True


async def _service_is_healthy(host: str, port: int, ready_path: str) -> bool:
    """True when something is listening and passes the HTTP readiness probe."""
    if not find_pids_on_port_windows(port):
        return False
    if not ready_path:
        return True
    check_host = _host_for_check(host)
    url = f"http://{check_host}:{port}{ready_path}"
    return await http_check(url)


async def _free_port_listeners(port: int, *, label: str, exclude_ollama: bool = False) -> None:
    pids = find_pids_on_port_windows(port)
    if not pids:
        return
    print(f"[COORDINATOR] Freed port {port} before {label} (PIDs: {pids})")
    kill_listeners_on_ports([port], exclude_ollama=exclude_ollama)
    await asyncio.sleep(PORT_KILL_SETTLE_SEC)


def report_service_failure(
    name: str,
    window_title: str,
    specs,
    *,
    extra_hint: Optional[str] = None,
) -> None:
    print()
    print(f'[{name}] Startup failed — check the "{window_title}" window for errors above.')
    if extra_hint:
        print(f"[{name}] Hint: {extra_hint}")
    print_inventory_table(
        scan_services(specs),
        title=f"Assistify Process Inventory (after {name} failure)",
    )
    print()


async def start_service_sequential(
    name: str,
    bat_path: Path,
    window_title: str,
    host: str,
    port: int,
    ready_path: str,
    args,
    status_by_name: dict,
    specs,
    *,
    failure_hint: Optional[str] = None,
    force_spawn: bool = False,
    pre_kill_port: bool = False,
) -> bool:
    if pre_kill_port:
        await _free_port_listeners(port, label=name)

    if not force_spawn:
        if await _service_is_healthy(host, port, ready_path):
            print(f"[{name}] Already healthy on port {port} — skipping new window")
            return True
    elif name == "Ollama":
        if ollama_http_ready():
            print(f"[{name}] API healthy — opening status window")
        elif find_pids_on_port_windows(port):
            print(f"[{name}] Port {port} open but API unhealthy — freeing stale listener")
            await _free_port_listeners(port, label=name, exclude_ollama=False)
    elif not pre_kill_port:
        row = status_by_name.get(name)
        if row and row.listening and await _service_is_healthy(host, port, ready_path):
            print(f"[{name}] Already running on port {row.port} — skipping new window")
            return True

    if find_pids_on_port_windows(port):
        print(f"[{name}] Stale listener on port {port} — freeing before spawn")
        exclude_ollama = name != "Ollama"
        await _free_port_listeners(port, label=name, exclude_ollama=exclude_ollama)

    print(f"[COORDINATOR] Starting {name} in a new window...")
    spawn_bat_window(window_title, bat_path)
    await asyncio.sleep(SPAWN_SETTLE_SEC)

    ok = await wait_service_ready(name.upper(), host, port, ready_path, args.quick)
    if not ok:
        report_service_failure(name.upper(), window_title, specs, extra_hint=failure_hint)
    return ok


async def run_split_launcher(args) -> int:
    ensure_cwd_and_path()
    apply_cli_overrides(args)
    ensure_sqlite3_or_exit()

    if args.ui_build_only:
        return 0 if ensure_react_ui_built(skip=args.skip_ui_build) else 1

    python_exe = str(resolve_project_python(REPO_ROOT))
    print(f"[COORDINATOR] Repo root : {REPO_ROOT}")
    print(f"[COORDINATOR] Python env: {python_env_label(Path(python_exe))}")
    print(f"[COORDINATOR] Python    : {python_exe}")
    print(f"[COORDINATOR] Launchers : {LAUNCH_DIR}")

    specs = default_service_specs(
        llm_port=SERVICES[0]["port"],
        rag_port=SERVICES[1]["port"],
        login_port=SERVICES[2]["port"],
    )
    inventory = scan_services(specs)
    print_inventory_table(inventory, title="Assistify Process Inventory (before start)")
    print_ollama_conflict_warnings()

    legacy_still_up = [p for p in LEGACY_PORTS if find_pids_on_port_windows(p)]

    if args.kill_ports:
        closed_windows = close_assistify_service_windows()
        if closed_windows:
            print(f"[COORDINATOR] Closed prior Assistify windows: {', '.join(closed_windows)}")
            await asyncio.sleep(1.0)
        ports = list(LEGACY_PORTS) + [SERVICES[0]["port"], SERVICES[1]["port"], SERVICES[2]["port"]]
        if not args.no_piper:
            ports.append(PORT_PIPER)
        killed = kill_listeners_on_ports(ports, exclude_ollama=True)
        legacy_killed = [port for port, _ in killed if port in LEGACY_PORTS]
        if legacy_killed:
            print(
                f"[COORDINATOR] Freed legacy ports {legacy_killed} "
                "(old FastAPI RAG/LLM/Login/Voice layout)"
            )
        for port, pids in killed:
            print(f"[COORDINATOR] Freed port {port} (PIDs: {pids})")
        inventory = scan_services(specs)
        print_inventory_table(inventory, title="Assistify Process Inventory (after --kill-ports)")
        legacy_still_up = [p for p in LEGACY_PORTS if find_pids_on_port_windows(p)]

    if legacy_still_up:
        print(
            f"[WARN] Legacy services may still run on port(s) {legacy_still_up} — "
            "close old 'FastAPI *' cmd windows manually."
        )

    status_by_name = {row.name: row for row in inventory}
    bats = generate_launch_bats(args, python_exe)

    all_ok = True
    failures: list[str] = []

    ui_build_ok = True
    if not args.no_login:
        print()
        print("[COORDINATOR] Building React UI for /frontend/ ...")
        ui_build_ok = ensure_react_ui_built(skip=args.skip_ui_build)
        if not ui_build_ok:
            print("[COORDINATOR] React UI build failed — Login will be skipped.")
            failures.append("React UI build")
            all_ok = False
    elif args.skip_ui_build:
        ensure_react_ui_built(skip=True)

    ollama_ok = args.no_ollama or ollama_http_ready()

    if not args.no_ollama:
        if args.restart_ollama:
            print("[COORDINATOR] --restart-ollama: freeing port 11434...")
            killed = kill_listeners_on_ports([PORT_OLLAMA], exclude_ollama=False)
            for port, pids in killed:
                print(f"[COORDINATOR] Freed port {port} (PIDs: {pids})")
            await asyncio.sleep(1.0)
            inventory = scan_services(specs)
            status_by_name = {row.name: row for row in inventory}

        ollama_exe = resolve_ollama_exe()
        print(f"[COORDINATOR] Ollama binary: {ollama_exe}")
        if args.ollama_silent:
            print("[COORDINATOR] Starting Ollama silently (--ollama-silent)...")
            await ensure_ollama_running(skip=False)
            ollama_ok = ollama_port_ready()
        else:
            ok = await start_service_sequential(
                "Ollama",
                bats["Ollama"],
                "Assistify Ollama",
                "127.0.0.1",
                PORT_OLLAMA,
                "",
                args,
                status_by_name,
                specs,
                force_spawn=True,
                failure_hint="Install Ollama or use --no-ollama if managed externally",
            )
            ollama_ok = ok and ollama_http_ready()
            if not ollama_ok:
                print("[COORDINATOR] Ollama window failed — trying Python bootstrap fallback...")
                await ensure_ollama_running(skip=False)
                ollama_ok = ollama_http_ready()
        if not ollama_ok:
                failures.append("Ollama")
                print_ollama_failure_hints()
                all_ok = False

        if ollama_ok:
            model_ok = await ensure_ollama_model(skip_pull=args.skip_model_pull)
            if not model_ok:
                print("[OLLAMA] Model bootstrap failed — chat may not work until model is pulled.")
                ollama_ok = False
                all_ok = False
                if "Ollama" not in failures:
                    failures.append("Ollama (model)")
        else:
            all_ok = False
    else:
        print("[SKIPPED] Ollama (--no-ollama)")
        ollama_ok = True

    startup_plan = [
        ("Piper", "Piper", "127.0.0.1", PORT_PIPER, "/health", args.no_piper, None),
        (
            "LLM",
            "LLM",
            SERVICES[0]["host"],
            SERVICES[0]["port"],
            SERVICES[0]["ready_path"],
            args.no_llm,
            None,
        ),
        (
            "RAG",
            "RAG",
            SERVICES[1]["host"],
            SERVICES[1]["port"],
            SERVICES[1]["ready_path"],
            args.no_rag,
            None,
        ),
        (
            "Login",
            "Login",
            SERVICES[2]["host"],
            SERVICES[2]["port"],
            SERVICES[2]["ready_path"],
            args.no_login,
            _LOGIN_PORT_HINT,
        ),
    ]

    print()
    print("[COORDINATOR] Starting services sequentially (spawn -> wait -> next)...")
    print("-" * 72)

    for key, display, host, port, ready_path, skipped, hint in startup_plan:
        if skipped:
            print(f"[SKIPPED] {display}")
            continue
        if display == "Login" and not ui_build_ok:
            print(f"[SKIPPED] {display} — React UI build failed")
            continue
        if display == "RAG" and not ollama_ok and not args.continue_without_ollama:
            print("[SKIPPED] RAG — Ollama is not ready (use --continue-without-ollama to force)")
            failures.append("RAG (blocked: Ollama)")
            all_ok = False
            continue
        ok = await start_service_sequential(
            key,
            bats[key],
            f"Assistify {display}",
            host,
            port,
            ready_path,
            args,
            status_by_name,
            specs,
            failure_hint=hint,
            pre_kill_port=args.kill_ports and display == "Login",
        )
        all_ok = all_ok and ok
        if not ok:
            failures.append(display)

    print()
    print("=" * 72)
    if all_ok:
        print("  ALL SERVICES READY")
    else:
        print("  STARTUP COMPLETED WITH WARNINGS")
        print(f"  Failed or timed out: {', '.join(failures)}")
        print("  Check the matching Assistify * windows for error output.")
    print("=" * 72)
    login_port = SERVICES[2]["port"]
    public_url: str | None = None
    tunnel: PublicTunnel | None = None
    if args.public and all_ok and not args.no_login:
        tunnel = PublicTunnel(port=login_port, provider=args.tunnel_provider)
        public_url = await tunnel.start_async()

    print_access_urls(
        login_port=login_port,
        rag_port=SERVICES[1]["port"],
        llm_port=SERVICES[0]["port"],
        public_base=public_url,
        tunnel_provider=tunnel.resolved_provider if tunnel else None,
        service_logs=args.service_logs or args.public,
    )
    print("  Bootstrap login: superadmin / superadmin")
    if all_ok:
        print()
        print("  Running stack verification...")
        print("  Login window may show HTTP 401 on /api/my-profile during verification — expected when logged out.")
        if not args.no_ollama and not ollama_http_ready():
            print("[COORDINATOR] Ollama not responding before verify — attempting recovery...")
            await ensure_ollama_running(skip=False)
            if ollama_http_ready():
                await ensure_ollama_model(skip_pull=args.skip_model_pull)
            else:
                print("[COORDINATOR] Ollama still unreachable after recovery attempt.")
                all_ok = False
                if "Ollama" not in failures:
                    failures.append("Ollama (verify)")
        try:
            from scripts.verify_stack import run_checks

            stack_ok, _ = run_checks(require_piper=not args.no_piper)
            if not stack_ok:
                print("  Stack verification reported issues — see messages above.")
                all_ok = False
        except Exception as e:
            print(f"  Stack verification skipped: {e}")
    else:
        print()
        print("  If Ollama failed: python start_main_servers.py --restart-ollama")
        print("  After services are up: python scripts/verify_stack.py")
    print()
    print("  Each service runs in its own window titled 'Assistify ...'.")
    print("  Close those windows to stop individual services.")
    print("  Press Ctrl+C here to exit the coordinator (service windows stay open).")
    print("=" * 72)

    print_inventory_table(
        scan_services(specs),
        title="Assistify Process Inventory (final)",
    )

    try:
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\n[COORDINATOR] Exiting. Service windows are still running — close them manually.")
        if tunnel is not None:
            print("[TUNNEL] Stopping tunnel...")
            tunnel.stop()
        return 0

    return 0 if all_ok else 1


def run_status_only(args) -> int:
    ensure_cwd_and_path()
    apply_cli_overrides(args)
    specs = default_service_specs(
        llm_port=SERVICES[0]["port"],
        rag_port=SERVICES[1]["port"],
        login_port=SERVICES[2]["port"],
    )
    print_inventory_table(scan_services(specs))
    return 0


def main() -> int:
    if not IS_WINDOWS:
        print("[LAUNCHER] Split-terminal mode is Windows-only; using single-console launcher.")
        script = REPO_ROOT / "scripts" / "project_start_server.py"
        argv = [a for a in sys.argv[1:] if a != "--status"]
        return subprocess.call([sys.executable, str(script), *argv], cwd=str(REPO_ROOT))

    argv = sys.argv[1:]
    status_only = False
    if "--status" in argv:
        status_only = True
        argv = [a for a in argv if a != "--status"]
    sys.argv = [sys.argv[0], *argv]

    args = parse_args()
    if status_only:
        return run_status_only(args)
    try:
        return asyncio.run(run_split_launcher(args))
    except KeyboardInterrupt:
        print("\n[COORDINATOR] Exiting. Service windows are still running — close them manually.")
        return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(0)
