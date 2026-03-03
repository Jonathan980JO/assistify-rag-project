"""
main_llm_server.py — Assistify LLM Server (Ollama backend)

All generation is delegated to the local Ollama service, which handles
GPU offloading internally.  No llama-cpp-python, no GPU enforcement code.

Startup requirements:
  - Ollama installed and running  (ollama serve)
  - Model pulled:  ollama pull qwen2.5:3b
                   (or whatever OLLAMA_MODEL is set to)
"""

import logging
import time
import httpx
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from typing import List, Optional

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
try:
    from config import OLLAMA_MODEL, OLLAMA_HOST, OLLAMA_PORT, BASE_URL
except ImportError:
    OLLAMA_MODEL = "qwen2.5:3b"
    OLLAMA_HOST = "127.0.0.1"
    OLLAMA_PORT = 11434
    BASE_URL = "http://127.0.0.1:7001"

OLLAMA_BASE = f"http://{OLLAMA_HOST}:{OLLAMA_PORT}"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("MainLLM")

# ---------------------------------------------------------------------------
# Shared async HTTP client (reused across requests)
# ---------------------------------------------------------------------------
http_client: Optional[httpx.AsyncClient] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global http_client
    # ---- startup ----
    http_client = httpx.AsyncClient(base_url=OLLAMA_BASE, timeout=120.0)
    logger.info("=" * 60)
    logger.info(f"Ollama base URL : {OLLAMA_BASE}")
    logger.info(f"Default model   : {OLLAMA_MODEL}")

    # Quick health-check: ask Ollama for the list of local models
    try:
        r = await http_client.get("/api/tags")
        r.raise_for_status()
        models = [m["name"] for m in r.json().get("models", [])]
        logger.info(f"Ollama models available: {models}")
        if OLLAMA_MODEL not in models:
            logger.warning(
                f"Model '{OLLAMA_MODEL}' not found in Ollama! "
                f"Run:  ollama pull {OLLAMA_MODEL}"
            )
        else:
            logger.info(f"[OK] Model '{OLLAMA_MODEL}' is ready.")
    except Exception as e:
        logger.error(f"Cannot reach Ollama at {OLLAMA_BASE}: {e}")
        logger.error("Make sure Ollama is running:  ollama serve")

    # Check if Ollama is using GPU (log a warning if not)
    try:
        ps = await http_client.get("/api/ps")
        if ps.status_code == 200:
            running = ps.json().get("models", [])
            for m in running:
                size_vram = m.get("size_vram", 0)
                processor = "GPU" if size_vram > 0 else "CPU"
                logger.info(f"[GPU CHECK] {m.get('name')} — processor: {processor} (VRAM: {size_vram} bytes)")
                if size_vram == 0:
                    logger.warning(
                        "Model is running on CPU only! "
                        "Make sure CUDA_VISIBLE_DEVICES=0 is set before starting Ollama. "
                        "Run: ollama stop <model> then restart Ollama with GPU env vars."
                    )
    except Exception:
        pass  # /api/ps may not be available in older builds

    logger.info("=" * 60)
    yield

    # ---- shutdown ----
    await http_client.aclose()
    logger.info("HTTP client closed.")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(title="Assistify LLM (Ollama)", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class ChatRequest(BaseModel):
    model: Optional[str] = None
    messages: List[dict]
    max_tokens: int = 512
    temperature: float = 0.7
    stream: bool = False
    stop: Optional[list] = None  # accepted but not forwarded to Ollama


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/")
def root():
    return {
        "status": "Assistify LLM Running",
        "backend": "Ollama",
        "model": OLLAMA_MODEL,
        "ollama_url": OLLAMA_BASE,
    }


@app.get("/logout")
def logout_redirect():
    return RedirectResponse(f"{BASE_URL}/logout", status_code=302)


@app.get("/internal/gpu-status")
async def gpu_status():
    """Return Ollama model list as a proxy for GPU/model status."""
    try:
        r = await http_client.get("/api/tags")
        r.raise_for_status()
        models = r.json().get("models", [])
        return {
            "ollama_reachable": True,
            "ollama_url": OLLAMA_BASE,
            "models": [m["name"] for m in models],
            "active_model": OLLAMA_MODEL,
        }
    except Exception as e:
        return {"ollama_reachable": False, "error": str(e)}


@app.post("/v1/chat/completions")
async def chat_completions(request: ChatRequest):
    """
    OpenAI-compatible chat endpoint.  Forwards the request to Ollama's
    /v1/chat/completions which is built into Ollama >= 0.1.24.
    """
    # Always use the configured Ollama model regardless of what the caller sends
    model = OLLAMA_MODEL

    # num_gpu=-1 tells Ollama to offload ALL layers to GPU (RTX 3070)
    GPU_LAYERS = 99  # large number = "put everything on GPU"

    try:
        # Try OpenAI-compatible endpoint first (Ollama >= 0.1.24)
        resp = await http_client.post("/v1/chat/completions", json={
            "model": model,
            "messages": request.messages,
            "max_tokens": min(request.max_tokens, 180),
            "temperature": 0.6,
            "stream": False,
            "keep_alive": -1,
            "options": {
                "num_ctx": 2048,
                "temperature": 0.6,
                "top_p": 0.9,
                "num_predict": 180,
                "num_gpu": GPU_LAYERS,
            },
        })

        if resp.status_code == 200:
            return resp.json()

        # Fallback: use Ollama's native /api/chat endpoint
        logger.warning(
            f"/v1/chat/completions returned {resp.status_code}, "
            "falling back to /api/chat"
        )

        resp2 = await http_client.post("/api/chat", json={
            "model": model,
            "messages": request.messages,
            "keep_alive": -1,
            "options": {
                "num_ctx": 2048,
                "temperature": 0.6,
                "top_p": 0.9,
                "num_predict": 180,
                "num_gpu": GPU_LAYERS,
            },
            "stream": False,
        })
        resp2.raise_for_status()
        data = resp2.json()

        # Wrap in OpenAI-compatible shape
        content = data.get("message", {}).get("content", "")
        return {
            "id": "chatcmpl-ollama",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": data.get("done_reason", "stop"),
                }
            ],
            "usage": {
                "prompt_tokens": data.get("prompt_eval_count", 0),
                "completion_tokens": data.get("eval_count", 0),
                "total_tokens": data.get("prompt_eval_count", 0) + data.get("eval_count", 0),
            },
        }

    except httpx.ConnectError:
        logger.error(f"Cannot connect to Ollama at {OLLAMA_BASE}")
        raise HTTPException(
            status_code=503,
            detail=f"Ollama service unreachable at {OLLAMA_BASE}. Run: ollama serve",
        )
    except httpx.TimeoutException:
        logger.error("Ollama request timed out")
        raise HTTPException(status_code=504, detail="Ollama request timed out")
    except Exception as e:
        logger.exception(f"Unexpected error calling Ollama: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    # When running the file directly, run the local `app` object to avoid
    # importing by module path which can be shadowed by other packages.
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)
