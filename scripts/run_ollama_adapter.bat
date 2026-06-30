@echo off
set OLLAMA_MODEL=%1
if "%OLLAMA_MODEL%"=="" set OLLAMA_MODEL=qwen2.5:3b
set PORT=%2
if "%PORT%"=="" set PORT=8100

echo Starting FromZero Ollama adapter on port %PORT% with model %OLLAMA_MODEL%

set OLLAMA_MODEL=%OLLAMA_MODEL%
python -m uvicorn backend.fromzero_ollama:app --host 0.0.0.0 --port %PORT%
