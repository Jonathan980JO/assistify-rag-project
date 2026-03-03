# ===========================================================================
#  Assistify — PowerShell Server Launcher
#  Runs all 3 servers with optimal uvicorn settings + GPU enforcement.
#  Usage:  .\run_servers.ps1
#          .\run_servers.ps1 -Dev          # enable --reload for RAG & Login
#          .\run_servers.ps1 -KillFirst    # kill any existing listeners first
# ===========================================================================
param(
    [switch]$Dev,
    [switch]$KillFirst
)

Set-StrictMode -Off
$ErrorActionPreference = "Continue"

# ---------------------------------------------------------------------------
# 1. GPU environment — MUST be set before Ollama and before Python subprocesses
# ---------------------------------------------------------------------------
$env:CUDA_VISIBLE_DEVICES  = "0"
$env:OLLAMA_KEEP_ALIVE     = "-1"   # never unload model from VRAM
$env:HF_HUB_DISABLE_SYMLINKS_WARNING = "1"

# ---------------------------------------------------------------------------
# 2. Paths
# ---------------------------------------------------------------------------
$Root      = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonExe = Join-Path $Root "graduation\Scripts\python.exe"

if (-not (Test-Path $PythonExe)) {
    Write-Error "[ERROR] Python venv not found at: $PythonExe"
    exit 1
}

# Ensure repo root is on PYTHONPATH
$env:PYTHONPATH = "$Root;$($env:PYTHONPATH)"

Set-Location $Root

# ---------------------------------------------------------------------------
# 3. Purge stale __pycache__ so Python always re-compiles from current .py
# ---------------------------------------------------------------------------
foreach ($dir in @("backend\__pycache__", "Login_system\__pycache__", "__pycache__")) {
    $full = Join-Path $Root $dir
    if (Test-Path $full) {
        Remove-Item $full -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host "[CACHE] Removed stale $dir"
    }
}

# ---------------------------------------------------------------------------
# 4. Optionally kill existing listeners
# ---------------------------------------------------------------------------
if ($KillFirst) {
    foreach ($port in @(8000, 7000, 7001)) {
        $pids = (netstat -ano | Select-String ":$port " | Select-String "LISTENING") -replace '.*\s+(\d+)$','$1'
        foreach ($p in $pids) {
            if ($p -match '^\d+$') {
                Write-Host "Killing PID $p on port $port"
                taskkill /PID $p /F 2>$null
            }
        }
    }
    Start-Sleep -Seconds 1
}

# ---------------------------------------------------------------------------
# 5. Build uvicorn command arrays (best-practice flags)
#
#    LLM  (port 8000) — binds all interfaces so the frontend can reach it
#         --timeout-keep-alive 300  : long timeout for slow LLM responses
#         --log-level info          : no noise, readable
#         NO --reload               : file-watching wastes CPU on a hot path
#
#    RAG  (port 7000) — local only
#         --timeout-keep-alive 120  : WebSocket + STT streaming needs headroom
#         --log-level info
#         --reload only in -Dev mode
#
#    LOGIN (port 7001) — local only
#         --timeout-keep-alive 75
#         --log-level info
#         --reload only in -Dev mode
# ---------------------------------------------------------------------------

$LLMArgs = @(
    "-u", "-m", "uvicorn", "backend.main_llm_server:app",
    "--host", "0.0.0.0",
    "--port", "8000",
    "--log-level", "info",
    "--timeout-keep-alive", "300"
)

$RAGArgs = @(
    "-u", "-m", "uvicorn", "backend.assistify_rag_server:app",
    "--host", "127.0.0.1",
    "--port", "7000",
    "--log-level", "info",
    "--timeout-keep-alive", "120"
)
if ($Dev) { $RAGArgs += "--reload" }

$LoginArgs = @(
    "-u", "-m", "uvicorn", "Login_system.login_server:app",
    "--host", "127.0.0.1",
    "--port", "7001",
    "--log-level", "info",
    "--timeout-keep-alive", "75"
)
if ($Dev) { $LoginArgs += "--reload" }

# ---------------------------------------------------------------------------
# 6. Launch each server in its own console window
# ---------------------------------------------------------------------------
function Start-Server {
    param($Title, $Args)
    # Build an argument string for the Python executable
    $argStr = ($Args | ForEach-Object { $_ }) -join ' '
    # Use cmd.exe start to reliably open a new console window and run the python command
    # The empty quoted title prevents the first token being treated as the window title
    # Build the start command using concatenation to avoid nested-quote parsing errors
    $startCmd = 'start "' + $Title + '" "' + $PythonExe + '" ' + $argStr
    Write-Host "[LAUNCH] $Title  ->  cmd /c $startCmd"
    Start-Process -FilePath "cmd.exe" -ArgumentList "/c", $startCmd -WorkingDirectory $Root -WindowStyle Normal
}

Write-Host ""
Write-Host "============================================================"
Write-Host "  Assistify Server Launcher"
Write-Host "  CUDA_VISIBLE_DEVICES = $env:CUDA_VISIBLE_DEVICES"
if ($Dev) { Write-Host "  Mode: DEVELOPMENT (--reload enabled for RAG + Login)" }
else      { Write-Host "  Mode: PRODUCTION  (no --reload)" }
Write-Host "============================================================"
Write-Host ""

Start-Server "LLM   (0.0.0.0:8000)" $LLMArgs
Start-Sleep -Milliseconds 500
Start-Server "RAG   (127.0.0.1:7000)" $RAGArgs
Start-Sleep -Milliseconds 500
Start-Server "LOGIN (127.0.0.1:7001)" $LoginArgs

Write-Host ""
Write-Host "[OK] All 3 server windows launched."
Write-Host "     Close those windows (or Ctrl+C inside them) to stop."
Write-Host ""
