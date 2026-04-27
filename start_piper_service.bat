@echo off
REM ============================================================
REM  Start Piper TTS Microservice  (assistify_main conda env)
REM  Port: 5002   (drop-in replacement for the old XTTS service)
REM  Engine: Piper - CPU only, no GPU usage
REM  Run from: G:\Grad_Project\assistify-rag-project-main\
REM ============================================================
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
echo Starting Piper TTS Microservice on port 5002...
echo Using: %USERPROFILE%\miniconda3\envs\assistify_main
echo.
%USERPROFILE%\miniconda3\envs\assistify_main\python.exe ^
    -m uvicorn tts_service.piper_server:app ^
    --host 127.0.0.1 ^
    --port 5002 ^
    --log-level info ^
    --timeout-keep-alive 300
