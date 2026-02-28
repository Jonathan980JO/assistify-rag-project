@echo off
setlocal

REM Force Ollama to use GPU (RTX 3070) — must be set before ollama serve starts
set "CUDA_VISIBLE_DEVICES=0"
set "OLLAMA_KEEP_ALIVE=-1"
REM -1 = keep model in VRAM forever (no eviction between requests)

REM Start all Assistify servers from repo root using project venv Python
cd /d "%~dp0"

set "PYTHON_EXE=%CD%\graduation\Scripts\python.exe"
if not exist "%PYTHON_EXE%" (
	echo [ERROR] Project Python not found at:
	echo         %PYTHON_EXE%
	echo Activate or create the venv first.
	pause
	exit /b 1
)

echo ====================================
echo   Assistify Full Server Launcher
echo   (Ollama + RAG + Login + XTTS)
echo ====================================
echo Using Python: %PYTHON_EXE%
echo.

REM 1) Start Ollama in a background window
echo [1/3] Starting Ollama...
start "Ollama" cmd /c "set CUDA_VISIBLE_DEVICES=0 & set OLLAMA_KEEP_ALIVE=-1 & ollama serve"
timeout /t 3 >nul

REM 2) Start XTTS v2 microservice (port 5002) in a background window
echo [2/3] Starting XTTS v2 microservice on port 5002...
set "XTTS_PYTHON=%USERPROFILE%\miniconda3\envs\assistify_xtts\python.exe"
if exist "%XTTS_PYTHON%" (
    set "COQUI_TOS_AGREED=1"
    start "XTTS" cmd /c "set COQUI_TOS_AGREED=1 & "%XTTS_PYTHON%" -m uvicorn xtts_service.xtts_server:app --host 127.0.0.1 --port 5002 --log-level info --timeout-keep-alive 300"
) else (
    echo [WARN] XTTS conda env not found. TTS will use browser speech fallback.
)
timeout /t 2 >nul

REM 3) Start RAG + Login servers (skip LLM — Ollama replaces it)
echo [3/3] Starting RAG + Login servers...
"%PYTHON_EXE%" scripts\project_start_server.py --kill-ports --quick --no-llm
