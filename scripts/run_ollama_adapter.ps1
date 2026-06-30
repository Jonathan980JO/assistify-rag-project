# Run the FromZero Ollama adapter (PowerShell)
param(
    [string]$Model = $env:OLLAMA_MODEL -or "qwen2.5:3b",
    [string]$Port = $env:OLLAMA_ADAPTER_PORT -or "8100"
)

Write-Host "Starting FromZero Ollama adapter on port $Port with model $Model"

$env:OLLAMA_MODEL = $Model

python -m uvicorn backend.fromzero_ollama:app --host 0.0.0.0 --port $Port
