@echo off
title Assistify LLM
call "%~dp0_env.bat"
cd /d "%REPO_ROOT%"
echo Starting LLM on port 8010...
"%PYTHON_EXE%" -u "%REPO_ROOT%\scripts\run_with_log.py" "%REPO_ROOT%\logs\llm.log" "%PYTHON_EXE%" -u -m uvicorn backend.main_llm_server:app --host 0.0.0.0 --port 8010 --log-level info --timeout-keep-alive 300
pause
