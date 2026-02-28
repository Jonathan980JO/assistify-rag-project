@echo off
REM ============================================================
REM  Start Main Project Servers  (assistify_main conda env)
REM  RAG (7000) + Login (7001)
REM  NOTE: Start Ollama and XTTS manually when needed.
REM  Run from: G:\Grad_Project\assistify-rag-project-main\
REM  Safe to run multiple times — kills old instances first.
REM ============================================================
set PYTHONPATH=%~dp0
set HF_HUB_DISABLE_SYMLINKS_WARNING=1
set CUDA_VISIBLE_DEVICES=0

echo ====================================
echo   Assistify Main Server Launcher
echo   (RAG + Login only)
echo ====================================

REM ---- Kill any existing server processes on our ports ----
echo [0/2] Stopping any old server instances...
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr ":7000 "') do (
    if not "%%a"=="0" (
        taskkill /F /PID %%a >nul 2>nul
    )
)
for /f "tokens=5" %%a in ('netstat -aon 2^>nul ^| findstr ":7001 "') do (
    if not "%%a"=="0" (
        taskkill /F /PID %%a >nul 2>nul
    )
)
timeout /t 2 /nobreak >nul
echo       Done.

REM 1) RAG Server
echo [1/2] Starting RAG Server (port 7000)...
start "RAG Server - Assistify" %USERPROFILE%\miniconda3\envs\assistify_main\python.exe ^
    -u -m uvicorn backend.assistify_rag_server:app ^
    --host 127.0.0.1 --port 7000 --log-level info --timeout-keep-alive 120

timeout /t 5 /nobreak >nul

REM 2) Login Server
echo [2/2] Starting Login Server (port 7001)...
start "Login Server - Assistify" %USERPROFILE%\miniconda3\envs\assistify_main\python.exe ^
    -u -m uvicorn Login_system.login_server:app ^
    --host 127.0.0.1 --port 7001 --log-level info --timeout-keep-alive 75

echo.
echo Servers launched in separate windows.
echo   RAG   : http://localhost:7000
echo   Login : http://localhost:7001
echo.
echo Start Ollama manually : ollama serve
echo Start XTTS manually   : start_xtts_service.bat
echo.
echo TIP: Do NOT close the "RAG Server" and "Login Server" windows.
