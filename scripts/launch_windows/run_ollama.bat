@echo off
title Assistify Ollama
call "%~dp0_env.bat"
cd /d "%REPO_ROOT%"
echo Ollama binary: %OLLAMA_EXE%
powershell -NoProfile -Command "if ((Test-NetConnection -ComputerName 127.0.0.1 -Port 11434 -WarningAction SilentlyContinue).TcpTestSucceeded) { exit 0 } else { exit 1 }" >nul 2>&1
if not errorlevel 1 goto :already_running
if exist "%OLLAMA_EXE%" goto :run_ollama
where ollama >nul 2>&1
if not errorlevel 1 (
  set "OLLAMA_EXE=ollama"
  goto :run_ollama
)
echo [ERROR] Ollama not found at "%OLLAMA_EXE%"
echo Install from https://ollama.com/download or open the Ollama tray app
echo Re-run launcher with --no-ollama if Ollama is already managed externally
pause
exit /b 1
:already_running
echo [OLLAMA] Already running on port 11434
echo.
echo Installed models:
if exist "%OLLAMA_EXE%" ("%OLLAMA_EXE%" list) else (ollama list)
echo.
echo Do NOT run 'ollama serve' while port 11434 is in use.
echo For a clean restart: python start_main_servers.py --restart-ollama
echo.
echo Monitor window — safe to close; does not stop tray Ollama.
cmd /k
:run_ollama
echo Starting Ollama on port 11434...
"%PYTHON_EXE%" -u "%REPO_ROOT%\scripts\run_with_log.py" "%REPO_ROOT%\logs\ollama.log" "%OLLAMA_EXE%" serve
if errorlevel 1 (
  echo.
  echo [ERROR] ollama serve failed — port 11434 may already be in use.
  echo Quit Ollama from the system tray, then run:
  echo   python start_main_servers.py --restart-ollama
)
pause
