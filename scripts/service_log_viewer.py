#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read-only web viewer for split-mode service log files."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse

SERVICE_LOGS = ("ollama", "piper", "llm", "rag", "login")


def _tail_file(path: Path, lines: int) -> str:
    if not path.is_file():
        return f"(no log yet — start with --public or --service-logs)\n"
    try:
        data = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return f"(could not read log: {exc})\n"
    chunks = data.splitlines()
    if lines <= 0 or len(chunks) <= lines:
        return data if data.endswith("\n") else data + "\n"
    return "\n".join(chunks[-lines:]) + "\n"


def build_service_log_router(log_dir: Path, auth_dep: Callable) -> APIRouter:
    router = APIRouter(prefix="/internal/service-logs", tags=["internal"])

    @router.get("", response_class=HTMLResponse)
    async def dashboard(_user=Depends(auth_dep)):
        tabs = "".join(
            f'<button type="button" class="tab" data-log="{name}">{name}</button>'
            for name in SERVICE_LOGS
        )
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Assistify service logs</title>
  <style>
    body {{ font-family: Consolas, monospace; margin: 0; background: #0f1117; color: #e6edf3; }}
    header {{ padding: 12px 16px; background: #161b22; border-bottom: 1px solid #30363d; }}
    h1 {{ margin: 0 0 8px; font-size: 18px; }}
    .tabs {{ display: flex; gap: 8px; flex-wrap: wrap; }}
    .tab {{ background: #21262d; color: #e6edf3; border: 1px solid #30363d; padding: 6px 12px; cursor: pointer; }}
    .tab.active {{ background: #238636; border-color: #238636; }}
    pre {{ margin: 0; padding: 16px; white-space: pre-wrap; word-break: break-word; min-height: 70vh; }}
    .meta {{ color: #8b949e; font-size: 12px; }}
  </style>
</head>
<body>
  <header>
    <h1>Assistify service logs</h1>
    <p class="meta">Mirrors the five Assistify * terminal windows. Auto-refreshes every 2s.</p>
    <div class="tabs">{tabs}</div>
  </header>
  <pre id="log"></pre>
  <script>
    const logEl = document.getElementById("log");
    const tabs = document.querySelectorAll(".tab");
    let active = "ollama";
    function setActive(name) {{
      active = name;
      tabs.forEach(t => t.classList.toggle("active", t.dataset.log === name));
      refresh();
    }}
    async function refresh() {{
      try {{
        const r = await fetch(`/internal/service-logs/${{active}}/tail?lines=300`, {{ credentials: "include" }});
        logEl.textContent = await r.text();
      }} catch (e) {{
        logEl.textContent = "Failed to load log: " + e;
      }}
    }}
    tabs.forEach(t => t.addEventListener("click", () => setActive(t.dataset.log)));
    setActive("ollama");
    setInterval(refresh, 2000);
  </script>
</body>
</html>"""

    @router.get("/{name}/tail", response_class=PlainTextResponse)
    async def tail(name: str, lines: int = 200, _user=Depends(auth_dep)):
        if name not in SERVICE_LOGS:
            raise HTTPException(status_code=404, detail="Unknown log")
        return _tail_file(log_dir / f"{name}.log", max(1, min(lines, 2000)))

    return router


def mount_service_logs(app, log_dir: Path, auth_dep: Callable) -> None:
    if not log_dir.exists():
        log_dir.mkdir(parents=True, exist_ok=True)
    app.include_router(build_service_log_router(log_dir, auth_dep))
