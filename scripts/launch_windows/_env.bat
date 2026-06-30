@echo off
cd /d "%~dp0..\.."
set "REPO_ROOT=%CD%"
if defined CONDA_PREFIX (
  set "PYTHON_EXE=%CONDA_PREFIX%\python.exe"
) else (
  set "PYTHON_EXE=python"
)
set "PYTHONPATH=%REPO_ROOT%"
set "KMP_DUPLICATE_LIB_OK=TRUE"
set "CUDA_VISIBLE_DEVICES=0"
set "OLLAMA_KEEP_ALIVE=5m"
where ollama >nul 2>&1
if %ERRORLEVEL%==0 (
  set "OLLAMA_EXE=ollama"
) else (
  set "OLLAMA_EXE=%LOCALAPPDATA%\Programs\Ollama\ollama.exe"
)
set "LLM_SERVER_URL=http://127.0.0.1:8010"
set "LLM_SERVER_PORT=8010"
set "OLLAMA_MODEL=qwen2.5:7b"
set "RAG_USE_GPU=1"
set "PIPER_EN_VOICE_PATH=%REPO_ROOT%\models\piper\en\voice.onnx"
set "PIPER_AR_VOICE_PATH=%REPO_ROOT%\models\piper\ar\voice.onnx"
set "WHISPER_DEVICE=cpu"
set "WHISPER_COMPUTE_TYPE=int8"
set "WHISPER_CHUNK_MS=800"
