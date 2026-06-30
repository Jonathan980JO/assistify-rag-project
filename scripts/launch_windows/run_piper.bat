@echo off
title Assistify Piper
call "%~dp0_env.bat"
cd /d "%REPO_ROOT%"
echo Starting Piper TTS on port 5002...
"%PYTHON_EXE%" -u "%REPO_ROOT%\scripts\run_with_log.py" "%REPO_ROOT%\logs\piper.log" "%PYTHON_EXE%" -u -m uvicorn tts_service.piper_server:app --host 127.0.0.1 --port 5002 --log-level info --timeout-keep-alive 300
pause
