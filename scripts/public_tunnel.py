#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Start a public HTTPS tunnel to the Login/UI port (cloudflared or ngrok)."""
from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

TunnelProvider = Literal["auto", "cloudflared", "ngrok"]

_CLOUDFLARE_URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com", re.I)
_NGROK_API = "http://127.0.0.1:4040/api/tunnels"
_TUNNEL_WAIT_SEC = 90
_CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
_PUBLIC_TUNNEL_URL_FILE = Path("logs") / "public-tunnel-url.json"


def persist_public_tunnel_url(url: str, provider: str) -> None:
    """Write active tunnel URL for the login-page QR (local dev / --public)."""
    path = Path.cwd() / _PUBLIC_TUNNEL_URL_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "url": url.rstrip("/"),
        "provider": provider,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def read_public_tunnel_url() -> dict | None:
    path = Path.cwd() / _PUBLIC_TUNNEL_URL_FILE
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) and data.get("url") else None


def clear_public_tunnel_url() -> None:
    path = Path.cwd() / _PUBLIC_TUNNEL_URL_FILE
    try:
        if path.is_file():
            path.unlink()
    except OSError:
        pass


def _windows_tunnel_candidates(name: str) -> list[Path]:
    """Well-known install paths when winget/MSI did not update PATH."""
    if os.name != "nt":
        return []
    pf = os.environ.get("ProgramFiles", r"C:\Program Files")
    pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    local = os.environ.get("LOCALAPPDATA", "")
    progdata = os.environ.get("ProgramData", "")
    home = Path.home()
    exe = f"{name}.exe"
    roots = [
        Path(pf) / name,
        Path(pf86) / name,
        Path(pf) / "Cloudflare" / name,
        Path(local) / "Microsoft" / "WinGet" / "Links",
        Path(progdata) / "chocolatey" / "bin",
        home / "scoop" / "shims",
        home / "AppData" / "Local" / "Microsoft" / "WinGet" / "Links",
    ]
    out: list[Path] = []
    for root in roots:
        candidate = root / exe if root.name != "Links" and root.name != "bin" and root.name != "shims" else root / exe
        if candidate.is_file():
            out.append(candidate)
        nested = root / name / exe
        if nested.is_file():
            out.append(nested)
    return out


def resolve_tunnel_binary(provider: TunnelProvider) -> tuple[str, str] | None:
    """Return (provider_name, executable_path) or None."""
    order: list[str]
    if provider == "cloudflared":
        order = ["cloudflared"]
    elif provider == "ngrok":
        order = ["ngrok"]
    else:
        order = ["cloudflared", "ngrok"]
    for name in order:
        path = shutil.which(name)
        if path:
            return name, path
        for candidate in _windows_tunnel_candidates(name):
            return name, str(candidate)
    return None


def _hostname_from_url(url: str) -> str:
    return urlparse(url).hostname or url


def print_access_urls(
    *,
    login_port: int,
    rag_port: int = 7000,
    llm_port: int = 8010,
    piper_port: int = 5002,
    ollama_port: int = 11434,
    public_base: str | None = None,
    tunnel_provider: str | None = None,
    service_logs: bool = False,
) -> None:
    """Print local service URLs and optional public tunnel URLs."""
    local_login = f"http://127.0.0.1:{login_port}"
    print()
    print("=" * 72)
    print("  ACCESS URLS")
    print("=" * 72)
    print("  Local (this machine only):")
    print(f"    Login:        {local_login}/login")
    print(f"    Chat UI:      {local_login}/frontend/")
    print(f"    Guest chat:   {local_login}/frontend/guest/")
    print(f"    RAG health:   http://127.0.0.1:{rag_port}/health")
    print(f"    LLM status:   http://127.0.0.1:{llm_port}/internal/gpu-status")
    print(f"    Piper health: http://127.0.0.1:{piper_port}/health")
    print(f"    Ollama:       http://127.0.0.1:{ollama_port}")
    if service_logs:
        print(f"    Service logs: {local_login}/internal/service-logs  (login required)")
    if public_base:
        base = public_base.rstrip("/")
        host = _hostname_from_url(base)
        print()
        print(f"  Public (tunnel via {tunnel_provider or 'tunnel'}):")
        print(f"    Login:        {base}/login")
        print(f"    Chat UI:      {base}/frontend/")
        print(f"    Guest chat:   {base}/frontend/guest/")
        if service_logs:
            print(f"    Service logs: {base}/internal/service-logs  (login required)")
        print()
        print("  .env hint (if you see 'Invalid host' errors):")
        print(f"    ALLOWED_HOSTS={host}")
        print("    ENFORCE_HTTPS=true")
    print("=" * 72)
    print()
    if public_base:
        print("  Keep the coordinator window open — closing it stops the public tunnel.")
        print()


class PublicTunnel:
    """Manage a cloudflared or ngrok process exposing Login/UI to the internet."""

    def __init__(self, port: int, provider: TunnelProvider = "auto") -> None:
        self.port = port
        self.provider = provider
        self._proc: subprocess.Popen | None = None
        self._async_proc: asyncio.subprocess.Process | None = None
        self._log_file = None
        self.public_url: str | None = None
        self.resolved_provider: str | None = None

    def _cloudflared_log_path(self) -> Path:
        return Path.cwd() / "logs" / "cloudflared-tunnel.log"

    def _start_cloudflared_sync(self, exe: str) -> str | None:
        import time

        log_path = self._cloudflared_log_path()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        # Fresh log each run — old trycloudflare URLs in the file are dead once cloudflared stops.
        log_path.write_text("--- tunnel session start ---\n", encoding="utf-8")
        self._log_file = log_path.open("a", encoding="utf-8", errors="replace")
        popen_kwargs: dict = {
            "stdout": self._log_file,
            "stderr": subprocess.STDOUT,
        }
        if _CREATE_NO_WINDOW:
            popen_kwargs["creationflags"] = _CREATE_NO_WINDOW
        self._proc = subprocess.Popen(
            [exe, "tunnel", "--url", f"http://127.0.0.1:{self.port}"],
            **popen_kwargs,
        )
        deadline = time.time() + _TUNNEL_WAIT_SEC
        while time.time() < deadline:
            try:
                text = log_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                text = ""
            match = _CLOUDFLARE_URL_RE.search(text)
            if match:
                # Use the newest URL if cloudflared printed more than one line.
                urls = _CLOUDFLARE_URL_RE.findall(text)
                url = urls[-1] if urls else match.group(0)
                if self._proc.poll() is not None:
                    print(
                        "[TUNNEL] cloudflared exited early — see logs/cloudflared-tunnel.log",
                        file=sys.stderr,
                    )
                    return None
                return url
            if self._proc.poll() is not None:
                tail = text.splitlines()[-5:]
                if tail:
                    print("[TUNNEL] cloudflared log tail:", file=sys.stderr)
                    for line in tail:
                        print(f"  {line}", file=sys.stderr)
                break
            time.sleep(0.5)
        return None

    @staticmethod
    def _verify_public_url(url: str, attempts: int = 5) -> bool:
        import socket
        import time

        host = _hostname_from_url(url)
        try:
            socket.getaddrinfo(host, 443)
        except OSError:
            print(
                f"[TUNNEL] DNS on this PC cannot resolve {host}",
                file=sys.stderr,
            )
            print(
                "[TUNNEL] Fix: set DNS to 1.1.1.1 (Cloudflare) or 8.8.8.8 (Google), then run: ipconfig /flushdns",
                file=sys.stderr,
            )
            print(
                "[TUNNEL] Or try: python start_main_servers.py --public --tunnel-provider ngrok",
                file=sys.stderr,
            )
            return False

        probe = f"{url.rstrip('/')}/login"
        for attempt in range(attempts):
            try:
                with urllib.request.urlopen(probe, timeout=20) as resp:
                    if 200 <= resp.status < 500:
                        return True
            except Exception:
                if attempt + 1 < attempts:
                    time.sleep(3)
        return False

    async def _start_cloudflared_async(self, exe: str) -> str | None:
        # Windows asyncio subprocess pipes are flaky; sync reader in a thread is reliable.
        return await asyncio.to_thread(self._start_cloudflared_sync, exe)

    async def _start_cloudflared_async_pipes(self, exe: str) -> str | None:
        """Fallback async pipe reader (ngrok-style). TimeoutError = keep waiting."""
        self._async_proc = await asyncio.create_subprocess_exec(
            exe,
            "tunnel",
            "--url",
            f"http://127.0.0.1:{self.port}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        assert self._async_proc.stdout is not None
        loop = asyncio.get_running_loop()
        deadline = loop.time() + _TUNNEL_WAIT_SEC
        while loop.time() < deadline:
            remaining = deadline - loop.time()
            try:
                line_b = await asyncio.wait_for(
                    self._async_proc.stdout.readline(),
                    timeout=min(2.0, max(0.1, remaining)),
                )
            except asyncio.TimeoutError:
                if self._async_proc.returncode is not None:
                    break
                continue
            if not line_b:
                if self._async_proc.returncode is not None:
                    break
                continue
            line = line_b.decode(errors="replace")
            match = _CLOUDFLARE_URL_RE.search(line)
            if match:
                return match.group(0)
        return None

    def _poll_ngrok_api(self) -> str | None:
        try:
            with urllib.request.urlopen(_NGROK_API, timeout=2) as resp:
                data = json.loads(resp.read().decode())
        except (urllib.error.URLError, json.JSONDecodeError, TimeoutError):
            return None
        for tunnel in data.get("tunnels", []):
            if tunnel.get("proto") == "https" and tunnel.get("public_url"):
                return str(tunnel["public_url"])
        return None

    def _start_ngrok_sync(self, exe: str) -> str | None:
        self._proc = subprocess.Popen(
            [exe, "http", str(self.port), "--log=stdout"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        import time

        deadline = time.time() + _TUNNEL_WAIT_SEC
        while time.time() < deadline:
            url = self._poll_ngrok_api()
            if url:
                return url
            if self._proc.poll() is not None:
                break
            time.sleep(0.5)
        return None

    async def _start_ngrok_async(self, exe: str) -> str | None:
        self._async_proc = await asyncio.create_subprocess_exec(
            exe,
            "http",
            str(self.port),
            "--log=stdout",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        loop = asyncio.get_running_loop()
        deadline = loop.time() + _TUNNEL_WAIT_SEC
        while loop.time() < deadline:
            url = await asyncio.to_thread(self._poll_ngrok_api)
            if url:
                return url
            if self._async_proc.returncode is not None:
                break
            await asyncio.sleep(0.5)
        return None

    def start_sync(self) -> str | None:
        resolved = resolve_tunnel_binary(self.provider)
        if not resolved:
            self._print_install_hint()
            return None
        name, exe = resolved
        self.resolved_provider = name
        print(f"[TUNNEL] Starting {name} -> http://127.0.0.1:{self.port} ...")
        if name == "cloudflared":
            self.public_url = self._start_cloudflared_sync(exe)
        else:
            self.public_url = self._start_ngrok_sync(exe)
        if self.public_url:
            persist_public_tunnel_url(self.public_url, name)
            print(f"[TUNNEL] Public URL ready: {self.public_url}")
            if self._verify_public_url(self.public_url):
                print("[TUNNEL] Verified — public URL responds OK")
            else:
                print(
                    "[TUNNEL] WARNING: URL printed but probe failed. "
                    "Keep this coordinator window open; see logs/cloudflared-tunnel.log",
                    file=sys.stderr,
                )
        else:
            print("[TUNNEL] Failed to obtain a public URL — check tunnel output above.", file=sys.stderr)
        return self.public_url

    async def start_async(self) -> str | None:
        resolved = resolve_tunnel_binary(self.provider)
        if not resolved:
            self._print_install_hint()
            return None
        name, exe = resolved
        self.resolved_provider = name
        print(f"[TUNNEL] Starting {name} -> http://127.0.0.1:{self.port} ...")
        try:
            if name == "cloudflared":
                self.public_url = await self._start_cloudflared_async(exe)
            else:
                self.public_url = await self._start_ngrok_async(exe)
        except Exception as exc:
            print(f"[TUNNEL] Failed to start tunnel: {exc}", file=sys.stderr)
            self.public_url = None
        if self.public_url:
            persist_public_tunnel_url(self.public_url, name)
            print(f"[TUNNEL] Public URL ready: {self.public_url}")
            if self._verify_public_url(self.public_url):
                print("[TUNNEL] Verified — public URL responds OK")
            else:
                print(
                    "[TUNNEL] WARNING: URL printed but probe failed. "
                    "Keep this coordinator window open; see logs/cloudflared-tunnel.log",
                    file=sys.stderr,
                )
        else:
            print(
                "[TUNNEL] No public URL — services still run locally. "
                "Retry: cloudflared tunnel --url http://127.0.0.1:{0}".format(self.port),
                file=sys.stderr,
            )
        return self.public_url

    def stop(self) -> None:
        clear_public_tunnel_url()
        for proc in (self._proc, self._async_proc):
            if proc is None:
                continue
            try:
                proc.terminate()
            except ProcessLookupError:
                pass
            except Exception:
                pass
        self._proc = None
        self._async_proc = None
        if self._log_file is not None:
            try:
                self._log_file.close()
            except Exception:
                pass
            self._log_file = None

    @staticmethod
    def _print_install_hint() -> None:
        win_hint = (
            "\n  Windows quick install:\n"
            "    winget install Cloudflare.cloudflared\n"
            "  Then re-run: python start_main_servers.py --public\n"
            "  (No terminal restart needed after this update.)"
            if os.name == "nt"
            else ""
        )
        print(
            "[TUNNEL] No tunnel binary found. Install one of:\n"
            "  cloudflared — https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/\n"
            "  ngrok       — https://ngrok.com/download"
            f"{win_hint}",
            file=sys.stderr,
        )
