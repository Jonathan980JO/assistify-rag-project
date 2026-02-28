@echo off
REM Quick restart - RAG server only (keeps LLM running)
set "PYTHON_EXE=%~dp0graduation\Scripts\python.exe"
if not exist "%PYTHON_EXE%" (
	echo [ERROR] Project Python not found at %PYTHON_EXE%
	exit /b 1
)

echo Restarting RAG server only...

REM Kill RAG server
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :7000') do taskkill /F /PID %%a 2>nul
timeout /t 2 /nobreak >nul

REM Restart RAG server
start "RAG Server" cmd /k "\"%PYTHON_EXE%\" -m uvicorn backend.assistify_rag_server:app --host 127.0.0.1 --port 7000"

echo RAG server restarted! Wait 10 seconds then refresh browser.
timeout /t 10 /nobreak
echo Ready!
pause
