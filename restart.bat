@echo off
REM Quick restart script for Assistify servers

REM Force Ollama to use GPU (RTX 3070)
set "CUDA_VISIBLE_DEVICES=0"
REM -1 = never evict model from VRAM between requests
set "OLLAMA_KEEP_ALIVE=-1"

set "PYTHON_EXE=%~dp0graduation\Scripts\python.exe"
if not exist "%PYTHON_EXE%" (
	echo [ERROR] Project Python not found at %PYTHON_EXE%
	exit /b 1
)
echo.
echo ========================================
echo   Assistify Quick Restart
echo ========================================
echo.

REM Kill all Python processes on required ports
echo [1/2] Killing old processes...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8000" ^| findstr "LISTENING"') do taskkill /F /PID %%a >nul 2>&1
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":7000" ^| findstr "LISTENING"') do taskkill /F /PID %%a >nul 2>&1
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":7001" ^| findstr "LISTENING"') do taskkill /F /PID %%a >nul 2>&1
timeout /t 2 /nobreak >nul

echo [2/2] Starting servers...
echo.
"%PYTHON_EXE%" scripts/project_start_server.py --production --quick --kill-ports
