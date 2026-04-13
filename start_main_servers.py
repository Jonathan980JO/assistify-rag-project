import os
import re
import sys
import time
import subprocess
from pathlib import Path
from typing import Iterable


def print_banner() -> None:
    print("====================================")
    print("  Assistify Main Server Launcher")
    print("  (RAG + Login only)")
    print("====================================")
    print(
        "Safe Mode Flags: "
        "SAFE_MODE=0 TTS=on RERANKER=on WHISPER=on "
        "WARMUP=on COLLECTION=auto DOC_MODE=single "
        "DOMAIN_HEURISTICS=off EMBED_DEVICE=cuda"
    )


def is_windows() -> bool:
    return os.name == "nt"


def project_root() -> Path:
    return Path(__file__).resolve().parent


def python_executable() -> Path:
    user_profile = Path(os.environ.get("USERPROFILE", str(Path.home())))
    return user_profile / "miniconda3" / "envs" / "assistify_main" / "python.exe"


def desktop_path() -> Path:
    user_profile = Path(os.environ.get("USERPROFILE", str(Path.home())))
    return user_profile / "Desktop"


def build_env(root: Path) -> dict[str, str]:
    env = os.environ.copy()

    # Match the batch file behavior as closely as possible
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONPATH"] = str(root)
    env["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
    env["CUDA_VISIBLE_DEVICES"] = "0"
    env["ASSISTIFY_SAFE_MODE"] = "0"
    env["ASSISTIFY_DISABLE_TTS"] = "0"
    env["ASSISTIFY_DISABLE_RERANKER"] = "0"
    env["ASSISTIFY_DISABLE_WHISPER"] = "0"
    env["ASSISTIFY_DISABLE_WARMUP"] = "0"
    # ASSISTIFY_COLLECTION_NAME intentionally not set
    env["ASSISTIFY_DOC_MODE"] = "single"
    env["ASSISTIFY_ENABLE_DOMAIN_SPECIFIC_HEURISTICS"] = "0"
    env["ASSISTIFY_EMBED_DEVICE"] = "cuda"

    return env


def run_command(
    command: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    capture: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        env=env,
        text=True,
        capture_output=capture,
        shell=False,
    )


def get_pids_on_port(port: int) -> set[int]:
    """
    Windows equivalent of:
      netstat -aon | findstr ":7000 "
    """
    if not is_windows():
        return set()

    result = run_command(["netstat", "-aon"], capture=True)
    output = (result.stdout or "") + "\n" + (result.stderr or "")

    pids: set[int] = set()

    for line in output.splitlines():
        # Must contain the target port
        if f":{port}" not in line:
            continue

        # Example line:
        # TCP    127.0.0.1:7000    0.0.0.0:0    LISTENING    12345
        parts = re.split(r"\s+", line.strip())
        if not parts:
            continue

        pid_str = parts[-1]
        if pid_str.isdigit():
            pid = int(pid_str)
            if pid != 0:
                pids.add(pid)

    return pids


def kill_pid(pid: int) -> None:
    if not is_windows():
        return

    subprocess.run(
        ["taskkill", "/F", "/PID", str(pid)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        shell=False,
    )


def kill_existing_servers(ports: Iterable[int]) -> None:
    print("[0/4] Stopping any old server instances...")

    killed: set[int] = set()
    for port in ports:
        for pid in get_pids_on_port(port):
            if pid not in killed:
                kill_pid(pid)
                killed.add(pid)

    time.sleep(2)
    print("      Done.")


def reset_log_files(rag_log: Path, login_log: Path) -> None:
    """Clear old log files and write fresh headers."""
    print("[1/4] Resetting Desktop log files...")

    # Write fresh headers
    rag_log.write_text(
        f"============================================================\n"
        f"Assistify RAG Server Log\n"
        f"Started: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"============================================================\n\n",
        encoding="utf-8",
    )

    login_log.write_text(
        f"============================================================\n"
        f"Assistify Login Server Log\n"
        f"Started: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"============================================================\n\n",
        encoding="utf-8",
    )

    print("      Done.")


def generate_helper_script(
    log_file: Path,
    python_exe: Path,
    module: str,
    port: int,
    project_root: Path,
    window_title: str,
    helper_file: Path,
) -> None:
    """Generate a helper Python script that streams output to both console and file."""
    script_content = f'''import subprocess
import sys
import os

# Window title
os.system(f'title {window_title}')

# Environment setup
env = os.environ.copy()
env["PYTHONUTF8"] = "1"
env["PYTHONIOENCODING"] = "utf-8"
env["PYTHONPATH"] = "{project_root}"
env["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
env["CUDA_VISIBLE_DEVICES"] = "0"
env["ASSISTIFY_SAFE_MODE"] = "0"
env["ASSISTIFY_DISABLE_TTS"] = "0"
env["ASSISTIFY_DISABLE_RERANKER"] = "0"
env["ASSISTIFY_DISABLE_WHISPER"] = "0"
env["ASSISTIFY_DISABLE_WARMUP"] = "0"
env["ASSISTIFY_DOC_MODE"] = "single"
env["ASSISTIFY_ENABLE_DOMAIN_SPECIFIC_HEURISTICS"] = "0"
env["ASSISTIFY_EMBED_DEVICE"] = "cuda"

# Start server process
cmd = [
    r"{python_exe}",
    "-u",
    "-m",
    "uvicorn",
    "{module}:app",
    "--host",
    "127.0.0.1",
    "--port",
    "{port}",
    "--log-level",
    "info",
    "--timeout-keep-alive",
    "120" if "rag" in "{module}" else "75",
]

process = subprocess.Popen(
    cmd,
    cwd=r"{project_root}",
    env=env,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    bufsize=1,
)

# Stream output to both console and file
log_path = r"{log_file}"
with open(log_path, "a", encoding="utf-8") as log:
    try:
        for line in process.stdout:
            if line:
                line_clean = line.rstrip("\\r\\n")
                print(line_clean)
                log.write(line_clean + "\\n")
                log.flush()
    except Exception as e:
        print(f"Error: {{e}}", file=sys.stderr)

process.wait()
'''
    helper_file.write_text(script_content, encoding="utf-8")


def main() -> int:
    if not is_windows():
        print("This launcher is designed for Windows only.", file=sys.stderr)
        return 1

    root = project_root()
    py_exe = python_executable()
    desktop = desktop_path()

    if not py_exe.exists():
        print(f"Python executable not found: {py_exe}", file=sys.stderr)
        return 1

    # Log file paths
    rag_log = desktop / "assistify_rag_live.log"
    login_log = desktop / "assistify_login_live.log"

    # Helper script paths (temp folder)
    temp_dir = root / "temp_launchers"
    temp_dir.mkdir(exist_ok=True)
    rag_helper = temp_dir / "run_rag_helper.py"
    login_helper = temp_dir / "run_login_helper.py"

    env = build_env(root)

    print_banner()
    kill_existing_servers([7000, 7001])
    reset_log_files(rag_log, login_log)

    # Generate helper scripts
    print("[2/4] Generating helper scripts...")
    generate_helper_script(
        rag_log,
        py_exe,
        "backend.assistify_rag_server",
        7000,
        root,
        "RAG Server - Assistify",
        rag_helper,
    )
    generate_helper_script(
        login_log,
        py_exe,
        "Login_system.login_server",
        7001,
        root,
        "Login Server - Assistify",
        login_helper,
    )
    print("      Done.")

    # Launch RAG Server in new window
    print("[3/4] Starting RAG Server (port 7000)...")
    try:
        subprocess.Popen(
            [str(py_exe), str(rag_helper)],
            cwd=str(root),
            env=env,
            creationflags=subprocess.CREATE_NEW_CONSOLE,  # type: ignore[attr-defined]
        )
    except Exception as e:
        print(f"ERROR: Failed to start RAG server: {e}", file=sys.stderr)
        return 1

    time.sleep(2)

    # Launch Login Server in new window
    print("[4/4] Starting Login Server (port 7001)...")
    try:
        subprocess.Popen(
            [str(py_exe), str(login_helper)],
            cwd=str(root),
            env=env,
            creationflags=subprocess.CREATE_NEW_CONSOLE,  # type: ignore[attr-defined]
        )
    except Exception as e:
        print(f"ERROR: Failed to start Login server: {e}", file=sys.stderr)
        return 1

    print()
    print("============================================================")
    print("Servers launched in separate windows.")
    print("  RAG   : http://localhost:7000")
    print("  Login : http://localhost:7001")
    print()
    print("Log files (Desktop):")
    print(f"  {rag_log}")
    print(f"  {login_log}")
    print()
    print("Optional: Start Ollama manually")
    print("  ollama serve")
    print()
    print("Optional: Start XTTS manually")
    print("  start_xtts_service.bat")
    print("============================================================")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
