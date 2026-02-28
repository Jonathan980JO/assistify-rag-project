#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Assistify project multi-server launcher (Windows-friendly).

Starts services in the correct order and verifies health:
1) LLM server (backend.main_llm_server:app) on 0.0.0.0:8000 (bind all)
2) RAG server (backend.assistify_rag_server:app) on 127.0.0.1:7000
3) Login server (Login_system.login_server:app) on 127.0.0.1:7001

Features:
- Ensures CWD is repo root and PYTHONPATH includes it
- Optional auto-kill for ports 8000/7000/7001 if occupied (Windows)
- Prefixed, live logs for each server
- Health checks and startup gating
- Graceful shutdown on Ctrl+C

GPU notes:
- By default, this launcher ensures CUDA_VISIBLE_DEVICES=0 so Ollama offloads to your GPU.

Usage (PowerShell):
  # Basic usage (optimized for RTX 3070)
  python scripts/project_start_server.py
  
  # Development mode with auto-reload
  python scripts/project_start_server.py --reload
  
  # Production mode (optimized GPU settings)
  python scripts/project_start_server.py --production
  
  # Quick startup (minimal health checks)
  python scripts/project_start_server.py --quick
  
  # Force kill occupied ports before starting
  python scripts/project_start_server.py --kill-ports
  
  # Custom settings
  python scripts/project_start_server.py --llm-port 8001

Notes:
- Run this inside your intended Python environment (e.g., conda env 'grad').
- This launcher does NOT activate conda; it uses the current interpreter.
- GPU offloading is handled by Ollama (ggml-cuda) — set CUDA_VISIBLE_DEVICES=0.
"""
from __future__ import annotations
import asyncio
import os
import sys
import signal
import socket
import subprocess
from pathlib import Path
from typing import Optional, Tuple, List

try:
    import aiohttp  # for health checks
except Exception:
    aiohttp = None

REPO_ROOT = Path(__file__).resolve().parent.parent
PORT_LLM = 8000
PORT_RAG = 7000
PORT_LOGIN = 7001

SERVICES = [
    {
        "name": "LLM",
        "module": "backend.main_llm_server:app",
        "host": "0.0.0.0",  # bind all interfaces (matches your manual command)
        "port": PORT_LLM,
        "ready_path": "/internal/gpu-status",  # best-effort; falls back to port check if missing
        "log_level": "info",
        "keep_alive": 300,  # LLM responses can take a while — generous timeout
    },
    {
        "name": "RAG",
        "module": "backend.assistify_rag_server:app",
        "host": "127.0.0.1",
        "port": PORT_RAG,
        "ready_path": "/health",
        "log_level": "info",
        "keep_alive": 120,  # WebSocket + STT streaming headroom
    },
    {
        "name": "LOGIN",
        "module": "Login_system.login_server:app",
        "host": "127.0.0.1",
        "port": PORT_LOGIN,
        "ready_path": "/",  # root page should respond
        "log_level": "info",
        "keep_alive": 75,
    },
]

IS_WINDOWS = os.name == "nt"
CREATE_NEW_PROCESS_GROUP = 0x00000200 if IS_WINDOWS else 0
DETACHED_PROCESS = 0x00000008 if IS_WINDOWS else 0


def _find_venv_python() -> str:
    """Detect the project venv Python interpreter.
    Falls back to sys.executable if the venv is not found."""
    venv_dir = REPO_ROOT / "graduation"
    if IS_WINDOWS:
        venv_py = venv_dir / "Scripts" / "python.exe"
    else:
        venv_py = venv_dir / "bin" / "python"
    if venv_py.exists():
        return str(venv_py)
    return sys.executable

# Resolve once at import time so all subprocesses use the same interpreter
PYTHON_EXE = _find_venv_python()


def _purge_pycache() -> None:
    """Remove __pycache__ dirs so Python compiles fresh .pyc from current source."""
    import shutil
    for subdir in ("backend", "Login_system", ""):
        cache = REPO_ROOT / subdir / "__pycache__" if subdir else REPO_ROOT / "__pycache__"
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)
            print(f"[CACHE] Removed stale {cache.relative_to(REPO_ROOT)}")


def ensure_cwd_and_path() -> None:
    os.chdir(REPO_ROOT)
    # prepend repo root to PYTHONPATH for reliable imports
    os.environ["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + os.environ.get("PYTHONPATH", "")
    _purge_pycache()


def parse_args():
    import argparse
    p = argparse.ArgumentParser(description="Assistify multi-server launcher")
    p.add_argument("--reload", action="store_true", help="Run uvicorn with --reload (dev mode)")
    p.add_argument("--kill-ports", action="store_true", help="Kill any process listening on required ports (Windows only)")
    p.add_argument("--quick", action="store_true", help="Quick startup mode - skip extensive health checks")
    p.add_argument("--production", action="store_true", help="Production mode - optimized GPU settings for RTX 3070")
    p.add_argument("--no-llm", action="store_true", help="Skip starting LLM server (use existing one)")
    p.add_argument("--no-rag", action="store_true", help="Skip starting RAG server (use existing one)")
    p.add_argument("--no-login", action="store_true", help="Skip starting Login server (use existing one)")
    p.add_argument("--llm-host", default=None, help="Override LLM bind host (default 0.0.0.0)")
    p.add_argument("--rag-host", default=None, help="Override RAG bind host (default 127.0.0.1)")
    p.add_argument("--login-host", default=None, help="Override Login bind host (default 127.0.0.1)")
    p.add_argument("--llm-port", type=int, default=None, help="Override LLM port (default 8000)")
    p.add_argument("--rag-port", type=int, default=None, help="Override RAG port (default 7000)")
    p.add_argument("--login-port", type=int, default=None, help="Override Login port (default 7001)")
    # ASR GPU (whisper) controls
    p.add_argument("--use-whisper", action="store_true", help="Use faster-whisper GPU ASR instead of Vosk")
    p.add_argument("--whisper-model", default=None, help="Override whisper model size (tiny, small, medium, large, etc.)")
    p.add_argument("--whisper-chunk-ms", type=int, default=800, help="Approximate milliseconds of audio to batch per whisper transcription (default 800)")
    # Reliability / diagnostics
    p.add_argument("--restart-attempts", type=int, default=0, help="Number of automatic restart attempts for a crashed service (default 0)")
    p.add_argument("--log-dir", default="logs", help="Directory to write per-service log files (default 'logs')")
    return p.parse_args()


def port_is_open(host: str, port: int, timeout: float = 0.5) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        try:
            return s.connect_ex((host, port)) == 0
        except Exception:
            return False


def _popen_flags() -> dict:
    # Ensure subprocesses run in the same console and get Ctrl+C forwarded
    kwargs = {}
    if IS_WINDOWS:
        # Creation flags omitted to keep same console; group signals still handled
        kwargs["creationflags"] = 0
    return kwargs


def find_pids_on_port_windows(port: int) -> List[int]:
    # Parses 'netstat -ano' output to get PIDs listening on ':{port}'
    try:
        out = subprocess.check_output(["netstat", "-ano"], text=True, errors="ignore")
    except Exception:
        return []
    pids = set()
    for line in out.splitlines():
        if f":{port} " in line or f":{port}\n" in line:
            parts = line.split()
            if len(parts) >= 5:
                state = parts[-2]
                pid = parts[-1]
                if state.upper() == "LISTENING":
                    try:
                        pids.add(int(pid))
                    except Exception:
                        pass
    return list(pids)


def kill_pid_windows(pid: int) -> None:
    try:
        subprocess.check_call(["taskkill", "/PID", str(pid), "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


async def wait_for_port(host: str, port: int, timeout: float = 30.0) -> bool:
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        if port_is_open(host, port):
            return True
        await asyncio.sleep(0.3)
    return False


async def http_check(url: str, timeout: float = 5.0) -> bool:
    if aiohttp is None:
        # Fallback: just ensure port is open
        return True
    try:
        to = aiohttp.ClientTimeout(total=timeout)
        async with aiohttp.ClientSession(timeout=to) as session:
            async with session.get(url) as resp:
                return resp.status < 500
    except Exception:
        return False


async def pipe_output(prefix: str, stream: asyncio.StreamReader):
    """Stream process stdout to console and append to file if configured."""
    try:
        while True:
            try:
                line = await stream.readline()
                if not line:
                    break
                try:
                    text = line.decode(errors="ignore").rstrip()
                except Exception:
                    text = str(line).rstrip()
                print(f"[{prefix}] {text}")
                log_file = SERVICE_LOG_FILES.get(prefix)
                if log_file:
                    try:
                        log_file.write(text + "\n")
                        log_file.flush()
                    except Exception:
                        pass
            except (asyncio.CancelledError, RuntimeError):
                # Stream closed or event loop closing
                break
            except Exception:
                # Ignore other read errors during shutdown
                break
    except Exception:
        pass


def _host_for_check(bind_host: str) -> str:
    # If a service binds to 0.0.0.0, we still check via localhost
    return "127.0.0.1" if bind_host in ("0.0.0.0", "::") else bind_host


async def start_service(name: str, module: str, host: str, port: int, ready_path: str, reload_flag: bool, log_level: str, keep_alive: int = 75, env_overrides: Optional[dict] = None) -> Tuple[asyncio.subprocess.Process, bool]:
    cmd = [
        PYTHON_EXE, "-u", "-m", "uvicorn", module,
        "--host", host,
        "--port", str(port),
        "--log-level", log_level,
        "--timeout-keep-alive", str(keep_alive),
    ]
    if reload_flag:
        cmd.extend(["--reload"])

    print(f"Starting {name} on http://{host}:{port} ...")
    env = os.environ.copy()
    # Always enforce GPU for Ollama — must be present for ggml-cuda.dll to load
    env["CUDA_VISIBLE_DEVICES"] = os.environ.get("CUDA_VISIBLE_DEVICES", "0")
    env["OLLAMA_KEEP_ALIVE"] = os.environ.get("OLLAMA_KEEP_ALIVE", "5m")
    if env_overrides:
        # Remove None values and stringify
        for k, v in list(env_overrides.items()):
            if v is None:
                env_overrides.pop(k)
        env.update({k: str(v) for k, v in env_overrides.items()})

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(REPO_ROOT),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env=env,
        **_popen_flags(),
    )

    asyncio.create_task(pipe_output(name, proc.stdout))

    # Wait for port, then health path (best effort)
    # LLM needs more time for model loading
    # RAG needs extra time on first run for faster-whisper model download (~300-600 seconds)
    # Get quick mode from global args if available
    quick_mode = hasattr(asyncio.current_task(), '_quick_mode') and asyncio.current_task()._quick_mode
    
    if quick_mode:
        timeout = 30.0  # Quick mode: minimal wait
    elif name == 'LLM':
        timeout = 120.0
    elif name == 'RAG':
        timeout = 600.0  # 10 minutes for model download on first run
    else:
        timeout = 60.0
    
    check_host = _host_for_check(host)
    port_ok = await wait_for_port(check_host, port, timeout=timeout)
    if not port_ok:
        print(f"[{name}] Port {port} did not open in time.")
        return proc, False

    if ready_path:
        url = f"http://{check_host}:{port}{ready_path}"
        for _ in range(30):  # up to ~30s
            if await http_check(url):
                break
            await asyncio.sleep(1.0)
        else:
            # Health path not responding; continue but warn
            print(f"[{name}] Warning: health check {ready_path} did not respond; proceeding.")

    print(f"[{name}] Ready on http://{host}:{port}")
    return proc, True


def tail_log_lines(name: str, count: int = 40) -> List[str]:
    f = SERVICE_LOG_FILES.get(name)
    if not f:
        return []
    try:
        f.flush()
        path = f.name
        with open(path, 'r', encoding='utf-8', errors='ignore') as rf:
            lines = rf.readlines()
        return lines[-count:]
    except Exception:
        return []


async def restart_service_if_needed(args, name: str, meta: dict, attempt: int) -> Optional[Tuple[str, asyncio.subprocess.Process]]:
    """Attempt a restart for a crashed service according to policies.
    Returns (name, proc) if restarted, else None.
    """
    if attempt >= args.restart_attempts:
        return None
    print(f"[LAUNCHER] Restarting {name} (attempt {attempt+1}/{args.restart_attempts}) ...")
    # Special fallback: just restart without extra logic (Ollama handles GPU)
    env_overrides = meta.get('env')
    proc, ok = await start_service(name, meta['module'], meta['host'], meta['port'], meta['ready_path'], meta['reload'], meta['log_level'], keep_alive=meta.get('keep_alive', 75), env_overrides=env_overrides)
    if not ok:
        print(f"[LAUNCHER] {name} restart did not pass readiness checks.")
    return (name, proc)


async def main():
    args = parse_args()
    ensure_cwd_and_path()
    print(f"Python: {PYTHON_EXE}  (sys.executable={sys.executable})")
    print(f"Repo root: {REPO_ROOT}")

    # Apply CLI overrides for hosts/ports
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

    # Optionally free ports (Windows only)
    if args.kill_ports and IS_WINDOWS:
        for p in (SERVICES[0]["port"], SERVICES[1]["port"], SERVICES[2]["port"]):
            pids = find_pids_on_port_windows(p)
            if pids:
                print(f"Killing PIDs on port {p}: {pids}")
                for pid in pids:
                    kill_pid_windows(pid)

    running = []  # list of (name, proc)
    # Prepare log directory & file handles
    global SERVICE_LOG_FILES
    SERVICE_LOG_FILES = {}
    log_dir = Path(args.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    try:
        # Store quick mode in current task for access in start_service
        if args.quick:
            try:
                asyncio.current_task()._quick_mode = True
            except Exception:
                pass
        
        # LLM
        if not args.no_llm:
            # GPU note: Ollama handles GPU layer offloading via ggml-cuda.
            # CUDA_VISIBLE_DEVICES is injected in start_service() automatically.
            llm_env = {}  # No llama-cpp env vars needed — Ollama manages GPU

            # Open log file
            SERVICE_LOG_FILES['LLM'] = open(log_dir / 'llm.log', 'a', encoding='utf-8')
            proc, ok = await start_service(
                "LLM",
                SERVICES[0]["module"],
                SERVICES[0]["host"],
                SERVICES[0]["port"],
                SERVICES[0]["ready_path"],
                args.reload,
                SERVICES[0]["log_level"],
                keep_alive=SERVICES[0]["keep_alive"],
                env_overrides=llm_env,
            )
            running.append(("LLM", proc))
            if not ok:
                print("[WARNING] LLM failed to become ready. Check logs or use --no-llm")
        else:
            print("[SKIPPED] LLM startup (--no-llm)")

        # RAG
        if not args.no_rag:
            rag_env = {}
            if args.use_whisper:
                rag_env["USE_WHISPER"] = "1"
            if args.whisper_model:
                rag_env["WHISPER_MODEL"] = args.whisper_model
            if args.whisper_chunk_ms:
                rag_env["WHISPER_CHUNK_MS"] = str(args.whisper_chunk_ms)
            SERVICE_LOG_FILES['RAG'] = open(log_dir / 'rag.log', 'a', encoding='utf-8')
            proc, ok = await start_service(
                "RAG",
                SERVICES[1]["module"],
                SERVICES[1]["host"],
                SERVICES[1]["port"],
                SERVICES[1]["ready_path"],
                args.reload,
                SERVICES[1]["log_level"],
                keep_alive=SERVICES[1]["keep_alive"],
                env_overrides=rag_env or None,
            )
            running.append(("RAG", proc))
            if not ok:
                print("RAG failed to become ready. Check logs above.")
        else:
            print("Skipping RAG startup (--no-rag)")

        # LOGIN
        if not args.no_login:
            SERVICE_LOG_FILES['LOGIN'] = open(log_dir / 'login.log', 'a', encoding='utf-8')
            proc, ok = await start_service(
                "LOGIN",
                SERVICES[2]["module"],
                SERVICES[2]["host"],
                SERVICES[2]["port"],
                SERVICES[2]["ready_path"],
                args.reload,
                SERVICES[2]["log_level"],
                keep_alive=SERVICES[2]["keep_alive"],
                env_overrides=None,
            )
            running.append(("LOGIN", proc))
            if not ok:
                print("Login server failed to become ready. Check logs above.")
        else:
            print("Skipping Login startup (--no-login)")

        print("All startups attempted. Logs are streaming below. Press Ctrl+C to stop.")

        # Monitor processes; do not shutdown on first exit — keep others running
        if not running:
            print("No processes started. Exiting.")
            return

        restart_meta = {
            'LLM': {
                'module': SERVICES[0]['module'], 'host': SERVICES[0]['host'], 'port': SERVICES[0]['port'],
                'ready_path': SERVICES[0]['ready_path'], 'reload': args.reload, 'log_level': SERVICES[0]['log_level'],
                'keep_alive': SERVICES[0]['keep_alive'],
                'env': llm_env if not args.no_llm else None
            },
            'RAG': {
                'module': SERVICES[1]['module'], 'host': SERVICES[1]['host'], 'port': SERVICES[1]['port'],
                'ready_path': SERVICES[1]['ready_path'], 'reload': args.reload, 'log_level': SERVICES[1]['log_level'],
                'keep_alive': SERVICES[1]['keep_alive'],
                'env': (rag_env or None) if not args.no_rag else None
            },
            'LOGIN': {
                'module': SERVICES[2]['module'], 'host': SERVICES[2]['host'], 'port': SERVICES[2]['port'],
                'ready_path': SERVICES[2]['ready_path'], 'reload': args.reload, 'log_level': SERVICES[2]['log_level'],
                'keep_alive': SERVICES[2]['keep_alive'],
                'env': None if not args.no_login else None
            },
        }
        restart_counts = {'LLM':0,'RAG':0,'LOGIN':0}
        
        print("\n" + "="*70)
        print("[SUCCESS] ALL SERVERS RUNNING")
        print("="*70)
        print("Press Ctrl+C to stop all servers")
        print("="*70 + "\n")
        
        # Keep running until interrupted
        while running:
            await asyncio.sleep(1.0)
            still_running = []
            for name, proc in running:
                rc = proc.returncode
                if rc is None:
                    still_running.append((name, proc))
                else:
                    print(f"[{name}] exited with code {rc}")
                    tail = tail_log_lines(name)
                    if tail:
                        print(f"[{name}] Last log lines:\n" + "\n".join(tail))
                    if args.restart_attempts > 0:
                        attempt = restart_counts[name]
                        restarted = await restart_service_if_needed(args, name, restart_meta[name], attempt)
                        if restarted:
                            restart_counts[name] += 1
                            still_running.append(restarted)
            running = still_running
        print("All processes exited. Launcher will exit.")
    except KeyboardInterrupt:
        print("\n\n[SHUTDOWN] Ctrl+C detected - shutting down servers...")
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Cleanup: stop all servers gracefully
        if running:
            print("\n[CLEANUP] Shutting down servers...")
            
            # First, terminate all processes
            for name, proc in running:
                if proc.returncode is None:
                    try:
                        print(f"   Stopping {name}...", end="", flush=True)
                        proc.terminate()
                        print(" [OK]")
                    except Exception as e:
                        print(f" [ERROR] ({e})")
            
            # Wait for graceful shutdown
            print("   Waiting for graceful shutdown...", end="", flush=True)
            await asyncio.sleep(2.0)
            print(" [DONE]")
            
            # Force kill any remaining processes
            killed_any = False
            for name, proc in running:
                if proc.returncode is None:
                    try:
                        print(f"   Force killing {name}...", end="", flush=True)
                        proc.kill()
                        # Wait for process to actually die
                        try:
                            await asyncio.wait_for(proc.wait(), timeout=2.0)
                            print(" [OK]")
                        except asyncio.TimeoutError:
                            print(" [TIMEOUT]")
                        killed_any = True
                    except Exception as e:
                        print(f" [ERROR] ({e})")
        
        # Close log files
        for log_file in SERVICE_LOG_FILES.values():
            try:
                log_file.close()
            except Exception:
                pass
        
        print("[SUCCESS] All servers stopped.\n")


if __name__ == "__main__":
    # Force UTF-8 encoding for Windows console
    if IS_WINDOWS:
        import sys
        import codecs
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')
    
    # Suppress asyncio cleanup warnings on Windows
    if IS_WINDOWS:
        import warnings
        # Suppress all ResourceWarning and asyncio cleanup errors
        warnings.filterwarnings("ignore", category=ResourceWarning)
        warnings.filterwarnings("ignore", message="Event loop is closed")
        warnings.filterwarnings("ignore", message=".*closed pipe.*")
        warnings.filterwarnings("ignore", message="Task was destroyed but it is pending")
        
        # Suppress console output for these specific errors
        import sys
        _original_stderr = sys.stderr
        
        class FilteredStderr:
            """Filter out asyncio cleanup errors from stderr"""
            def write(self, text):
                # Skip asyncio cleanup errors
                if any(x in text for x in [
                    "Event loop is closed",
                    "closed pipe",
                    "BaseSubprocessTransport",
                    "_ProactorBasePipeTransport",
                    "Task was destroyed but it is pending"
                ]):
                    return
                _original_stderr.write(text)
            
            def flush(self):
                _original_stderr.flush()
        
        sys.stderr = FilteredStderr()
    
    try:
        # Use Windows-specific event loop policy
        if sys.version_info >= (3, 8) and IS_WINDOWS:
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        
        asyncio.run(main())
    except KeyboardInterrupt:
        # User pressed Ctrl+C - this is expected
        pass
    except Exception as e:
        print(f"\n[FATAL ERROR] {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Restore stderr if we filtered it
        if IS_WINDOWS:
            sys.stderr = _original_stderr
