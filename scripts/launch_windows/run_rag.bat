@echo off
title Assistify RAG
call "%~dp0_env.bat"
cd /d "%REPO_ROOT%"
echo Starting RAG on port 7000...
"%PYTHON_EXE%" -u "%REPO_ROOT%\scripts\run_with_log.py" "%REPO_ROOT%\logs\rag.log" "%PYTHON_EXE%" -u -m uvicorn backend.assistify_rag_server:app --host 127.0.0.1 --port 7000 --log-level info --timeout-keep-alive 120
pause
