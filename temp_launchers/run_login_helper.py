import subprocess
import sys
import os

# Window title
os.system(f'title Login Server - Assistify')

# Environment setup
env = os.environ.copy()
env["PYTHONUTF8"] = "1"
env["PYTHONIOENCODING"] = "utf-8"
env["PYTHONPATH"] = "G:\Grad_Project\assistify-rag-project-main"
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
    r"C:\Users\MK\miniconda3\envs\assistify_main\python.exe",
    "-u",
    "-m",
    "uvicorn",
    "Login_system.login_server:app",
    "--host",
    "127.0.0.1",
    "--port",
    "7001",
    "--log-level",
    "info",
    "--timeout-keep-alive",
    "120" if "rag" in "Login_system.login_server" else "75",
]

process = subprocess.Popen(
    cmd,
    cwd=r"G:\Grad_Project\assistify-rag-project-main",
    env=env,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    bufsize=1,
)

# Stream output to both console and file
log_path = r"C:\Users\MK\Desktop\assistify_login_live.log"
with open(log_path, "a", encoding="utf-8") as log:
    try:
        for line in process.stdout:
            if line:
                line_clean = line.rstrip("\r\n")
                print(line_clean)
                log.write(line_clean + "\n")
                log.flush()
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)

process.wait()
