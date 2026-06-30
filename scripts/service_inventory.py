#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Port/process inventory for Assistify services (Windows-focused)."""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from typing import Iterable, List, Optional, Tuple

PORT_OLLAMA = 11434
PORT_PIPER = 5002
PORT_LLM = 8010
PORT_RAG = 7000
PORT_LOGIN = 7001
# Legacy ports from older Assistify launchers (RAG/LLM/Login/Voice on 8000–8002)
LEGACY_PORTS = (8000, 8001, 8002)

ASSISTIFY_WINDOW_TITLES = (
    "Assistify Ollama",
    "Assistify Piper",
    "Assistify LLM",
    "Assistify RAG",
    "Assistify Login",
)


@dataclass
class ServiceStatus:
    name: str
    port: int
    listening: bool
    pids: List[int]
    process_names: List[str]


def find_listeners_on_port_windows(port: int) -> List[Tuple[int, str]]:
    """Return (pid, local_address) for each LISTENING socket on *port*."""
    try:
        out = subprocess.check_output(["netstat", "-ano"], text=True, errors="ignore")
    except Exception:
        return []
    listeners: List[Tuple[int, str]] = []
    seen: set[Tuple[int, str]] = set()
    for line in out.splitlines():
        if f":{port} " not in line and not line.rstrip().endswith(f":{port}"):
            continue
        parts = line.split()
        if len(parts) < 5 or parts[-2].upper() != "LISTENING":
            continue
        try:
            pid = int(parts[-1])
        except ValueError:
            continue
        addr = parts[1] if len(parts) >= 2 else "?"
        key = (pid, addr)
        if key not in seen:
            seen.add(key)
            listeners.append(key)
    return listeners


def find_pids_on_port_windows(port: int) -> List[int]:
    pids = {pid for pid, _ in find_listeners_on_port_windows(port)}
    return sorted(pids)


def detect_ollama_conflicts() -> List[str]:
    """Return human-readable warnings when multiple processes hold port 11434."""
    listeners = find_listeners_on_port_windows(PORT_OLLAMA)
    if not listeners:
        return []
    pids = sorted({pid for pid, _ in listeners})
    warnings: List[str] = []
    if len(pids) > 1:
        proc_names = ", ".join(_process_name_for_pid(pid) for pid in pids)
        warnings.append(
            f"Ollama port conflict: {len(pids)} processes on {PORT_OLLAMA} "
            f"(PIDs {', '.join(str(p) for p in pids)}: {proc_names})"
        )
    addrs = {addr for _, addr in listeners}
    if len(addrs) > 1:
        warnings.append(
            f"Ollama bind addresses on {PORT_OLLAMA}: {', '.join(sorted(addrs))}"
        )
    return warnings


def print_ollama_conflict_warnings(*, fix_hint: bool = True) -> bool:
    """Print Ollama conflict warnings. Returns True if any were printed."""
    warnings = detect_ollama_conflicts()
    for msg in warnings:
        print(f"[WARN] {msg}")
    if warnings and fix_hint:
        print("[WARN] Fix: python start_main_servers.py --restart-ollama")
    return bool(warnings)


def _process_name_for_pid(pid: int) -> str:
    try:
        out = subprocess.check_output(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            text=True,
            errors="ignore",
        )
        line = out.strip()
        if line and "No tasks" not in line:
            return line.split(",")[0].strip('"')
    except Exception:
        pass
    return "?"


def default_service_specs(
    *,
    llm_port: Optional[int] = None,
    rag_port: Optional[int] = None,
    login_port: Optional[int] = None,
) -> List[Tuple[str, int]]:
    llm = llm_port if llm_port is not None else int(os.environ.get("LLM_SERVER_PORT", PORT_LLM))
    rag = rag_port if rag_port is not None else PORT_RAG
    login = login_port if login_port is not None else PORT_LOGIN
    return [
        ("Ollama", PORT_OLLAMA),
        ("Piper", PORT_PIPER),
        ("LLM", llm),
        ("RAG", rag),
        ("Login", login),
    ]


def scan_services(specs: Iterable[Tuple[str, int]]) -> List[ServiceStatus]:
    rows: List[ServiceStatus] = []
    for name, port in specs:
        pids = find_pids_on_port_windows(port)
        rows.append(
            ServiceStatus(
                name=name,
                port=port,
                listening=bool(pids),
                pids=pids,
                process_names=[_process_name_for_pid(pid) for pid in pids],
            )
        )
    return rows


def print_inventory_table(rows: List[ServiceStatus], *, title: str = "Assistify Process Inventory") -> None:
    print()
    print("=" * 72)
    print(f"  {title}")
    print("=" * 72)
    print(f"{'Service':<10} {'Port':<8} {'Status':<12} {'PID(s)':<14} Process")
    print("-" * 72)
    for row in rows:
        status = "LISTENING" if row.listening else "FREE"
        pid_str = ",".join(str(p) for p in row.pids) if row.pids else "-"
        proc_str = ",".join(row.process_names) if row.process_names else "-"
        print(f"{row.name:<10} {row.port:<8} {status:<12} {pid_str:<14} {proc_str}")
    print("=" * 72)
    print()


def close_assistify_service_windows() -> List[str]:
    """Close visible cmd windows titled 'Assistify ...' from a prior launcher run."""
    if os.name != "nt":
        return []
    titles_ps = ",".join(f"'{t}'" for t in ASSISTIFY_WINDOW_TITLES)
    script = f"""
$titles = @({titles_ps})
$closed = @()
Get-Process | Where-Object {{
  $_.MainWindowTitle -and ($titles -contains $_.MainWindowTitle)
}} | ForEach-Object {{
  $closed += $_.MainWindowTitle
  Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
}}
$closed -join "`n"
"""
    try:
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command", script],
            text=True,
            errors="ignore",
        )
        return [ln.strip() for ln in out.splitlines() if ln.strip()]
    except Exception:
        return []


def kill_listeners_on_ports(
    ports: Iterable[int],
    *,
    exclude_ollama: bool = True,
) -> List[Tuple[int, List[int]]]:
    killed: List[Tuple[int, List[int]]] = []
    for port in ports:
        if exclude_ollama and port == PORT_OLLAMA:
            continue
        pids = find_pids_on_port_windows(port)
        if not pids:
            continue
        for pid in pids:
            try:
                subprocess.check_call(
                    ["taskkill", "/PID", str(pid), "/F"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except Exception:
                pass
        killed.append((port, pids))
    return killed
