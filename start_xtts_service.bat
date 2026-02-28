@echo off
REM ============================================================
REM  Start XTTS v2 Microservice  (assistify_xtts conda env)
REM  Port: 5002
REM  Run from: G:\Grad_Project\assistify-rag-project-main\
REM ============================================================
set COQUI_TOS_AGREED=1
set HF_HUB_DISABLE_SYMLINKS_WARNING=1
echo Starting XTTS v2 Microservice on port 5002...
echo Using: %USERPROFILE%\miniconda3\envs\assistify_xtts
echo.
%USERPROFILE%\miniconda3\envs\assistify_xtts\python.exe ^
    -m uvicorn xtts_service.xtts_server:app ^
    --host 127.0.0.1 ^
    --port 5002 ^
    --log-level info ^
    --timeout-keep-alive 300
