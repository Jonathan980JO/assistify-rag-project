@echo off
cd /d "G:\Grad_Project\assistify-rag-project-main"
title RAG Server - Assistify
mode con: cols=160 lines=9999
echo Logging live to: G:\Grad_Project\assistify-rag-project-main\logs\rag_20260411_031231.log
echo.
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "PYTHONPATH=G:\Grad_Project\assistify-rag-project-main"
set "HF_HUB_DISABLE_SYMLINKS_WARNING=1"
set "CUDA_VISIBLE_DEVICES=0"
set "ASSISTIFY_SAFE_MODE=1"
set "ASSISTIFY_DISABLE_TTS=1"
set "ASSISTIFY_DISABLE_RERANKER=1"
set "ASSISTIFY_DISABLE_WHISPER=1"
set "ASSISTIFY_DISABLE_WARMUP=0"
set "ASSISTIFY_DOC_MODE=single"
set "ASSISTIFY_ENABLE_DOMAIN_SPECIFIC_HEURISTICS=0"
set "ASSISTIFY_EMBED_DEVICE=cuda"
"C:\Users\MK\miniconda3\envs\assistify_main\python.exe" -X utf8 -u -m uvicorn backend.assistify_rag_server:app --host 127.0.0.1 --port 7000 --log-level info --timeout-keep-alive 120 >> "G:\Grad_Project\assistify-rag-project-main\logs\rag_20260411_031231.log" 2>&1
echo.
echo RAG server exited. Check log:
echo G:\Grad_Project\assistify-rag-project-main\logs\rag_20260411_031231.log
pause
