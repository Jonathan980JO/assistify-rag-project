#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared Ollama binary resolution, process start, and model bootstrap."""
from __future__ import annotations

import asyncio
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from typing import Optional

try:
    import aiohttp
except Exception:
    aiohttp = None  # type: ignore

PORT_OLLAMA = 11434
OLLAMA_HOST = "127.0.0.1"
IS_WINDOWS = os.name == "nt"


def resolve_ollama_exe() -> str:
    """Resolve the Ollama CLI binary (ollama.exe on Windows)."""
    for key in ("OLLAMA_EXE", "OLLAMA_CLI"):
        env_cli = os.environ.get(key, "").strip()
        if env_cli and Path(env_cli).exists():
            return str(Path(env_cli))
    found = shutil.which("ollama")
    if found:
        return found
    local = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe"
    if local.exists():
        return str(local)
    return os.environ.get("OLLAMA_CLI", "ollama")


def resolve_ollama_tray_exe() -> Optional[str]:
    """Resolve the Windows Ollama desktop/tray app (starts the background server)."""
    local = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "Ollama.exe"
    if local.exists():
        return str(local)
    return None


def port_is_open(host: str, port: int, timeout: float = 0.5) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        try:
            return s.connect_ex((host, port)) == 0
        except Exception:
            return False


async def wait_for_port(host: str, port: int, timeout: float = 60.0) -> bool:
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        if port_is_open(host, port):
            return True
        await asyncio.sleep(0.3)
    return False


def _popen_flags() -> dict:
    return {"creationflags": 0} if IS_WINDOWS else {}


async def ollama_model_usable(model: str) -> bool:
    """Return True if model is pulled and loadable via POST /api/show."""
    if aiohttp is None:
        return True
    try:
        to = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=to) as session:
            async with session.post(
                f"http://{OLLAMA_HOST}:{PORT_OLLAMA}/api/show",
                json={"model": model},
            ) as resp:
                return resp.status == 200
    except Exception:
        return True


def print_ollama_failure_hints() -> None:
    print("[OLLAMA] Fix steps:")
    print("  1. Install Ollama from https://ollama.com/download")
    print("  2. Open the Ollama tray app from the Start menu, or run: ollama serve")
    print(f"  3. Re-run with --no-ollama if Ollama is already managed externally")
    print("  4. Run: python scripts/preflight_check.py")


async def ensure_ollama_running(skip: bool = False) -> Optional[subprocess.Popen]:
    """Start Ollama if port 11434 is not open. Returns Popen only if we spawned serve."""
    if skip:
        print("[SKIPPED] Ollama startup (--no-ollama)")
        return None

    if port_is_open(OLLAMA_HOST, PORT_OLLAMA):
        print(f"[OLLAMA] Already running on {OLLAMA_HOST}:{PORT_OLLAMA}")
        return None

    ollama_cli = resolve_ollama_exe()
    print(f"[OLLAMA] Starting via '{ollama_cli} serve' ...")
    started_proc: Optional[subprocess.Popen] = None

    if Path(ollama_cli).exists() or shutil.which(ollama_cli):
        try:
            started_proc = subprocess.Popen(
                [ollama_cli, "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                **_popen_flags(),
            )
        except FileNotFoundError:
            started_proc = None
            print(f"[OLLAMA] Could not execute '{ollama_cli}'")

    if started_proc and await wait_for_port(OLLAMA_HOST, PORT_OLLAMA, timeout=60.0):
        print(f"[OLLAMA] Ready on {OLLAMA_HOST}:{PORT_OLLAMA}")
        return started_proc

    if not port_is_open(OLLAMA_HOST, PORT_OLLAMA) and IS_WINDOWS:
        tray = resolve_ollama_tray_exe()
        if tray:
            print(f"[OLLAMA] Trying Windows tray app: {tray}")
            try:
                subprocess.Popen(
                    [tray],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    **_popen_flags(),
                )
            except Exception as e:
                print(f"[OLLAMA] Tray launch failed: {e}")
            if await wait_for_port(OLLAMA_HOST, PORT_OLLAMA, timeout=60.0):
                print(f"[OLLAMA] Ready on {OLLAMA_HOST}:{PORT_OLLAMA} (tray app)")
                return None

    if not port_is_open(OLLAMA_HOST, PORT_OLLAMA):
        print(f"[OLLAMA] Port {PORT_OLLAMA} did not open in time.")
        print_ollama_failure_hints()
    return started_proc


async def ensure_ollama_model(skip_pull: bool = False) -> bool:
    """Ensure OLLAMA_MODEL is present and loadable. Requires port 11434 open."""
    if not port_is_open(OLLAMA_HOST, PORT_OLLAMA):
        print("[OLLAMA] Cannot verify model — server not reachable on port 11434")
        return False

    model = os.environ.get("OLLAMA_MODEL", "qwen2.5:3b")
    if skip_pull:
        print(f"[OLLAMA] Skipping model pull (--skip-model-pull); assuming '{model}' is ready")
        return True

    if await ollama_model_usable(model):
        print(f"[OLLAMA] Model '{model}' present and loadable.")
        return True

    ollama_cli = resolve_ollama_exe()
    print(f"[OLLAMA] Model '{model}' missing or unusable — pulling (first run may take a while)...")
    try:
        subprocess.run(
            [ollama_cli, "rm", model],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        result = subprocess.run([ollama_cli, "pull", model], check=False)
        if result.returncode != 0:
            print(f"[OLLAMA] pull failed (exit {result.returncode})")
            return False
    except FileNotFoundError:
        print(f"[OLLAMA] '{ollama_cli}' not found — cannot pull model")
        return False
    except Exception as e:
        print(f"[OLLAMA] pull failed: {e}")
        return False

    if await ollama_model_usable(model):
        print(f"[OLLAMA] Model '{model}' ready after pull.")
        return True
    print(f"[OLLAMA] Model '{model}' still not loadable after pull")
    return False


async def ensure_ollama(skip: bool, skip_pull: bool) -> Optional[subprocess.Popen]:
    """Start Ollama if needed and ensure the configured model is available."""
    started_proc = await ensure_ollama_running(skip=skip)
    if skip:
        return None
    if port_is_open(OLLAMA_HOST, PORT_OLLAMA):
        await ensure_ollama_model(skip_pull=skip_pull)
    return started_proc


def ollama_port_ready() -> bool:
    return port_is_open(OLLAMA_HOST, PORT_OLLAMA)


def ollama_http_ready(timeout: float = 3.0) -> bool:
    """True when Ollama answers HTTP on /api/tags (not just an open TCP port)."""
    if not port_is_open(OLLAMA_HOST, PORT_OLLAMA):
        return False
    try:
        import urllib.request

        req = urllib.request.Request(
            f"http://{OLLAMA_HOST}:{PORT_OLLAMA}/api/tags",
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return 200 <= int(resp.status) < 300
    except Exception:
        return False
