"""
Project configuration centralization.

This file reads configuration from environment variables.
CRITICAL: All secrets MUST be set in environment variables for production.
"""
import os
import sys
from pathlib import Path

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("[WARNING] python-dotenv not installed. Install with: pip install python-dotenv")

# Project root
ROOT = Path(__file__).resolve().parent

# Environment detection
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")  # development | production
IS_PRODUCTION = ENVIRONMENT == "production"

# ========== SECURITY REQUIREMENTS ==========
# Session secret MUST be 64+ bytes in production
SESSION_SECRET = os.getenv("SESSION_SECRET")
SESSION_COOKIE = os.getenv("SESSION_COOKIE", "session")

# OAuth credentials
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:7001/auth/google/callback")

# EmailJS credentials (for OTP)
EMAILJS_PUBLIC_KEY = os.getenv("EMAILJS_PUBLIC_KEY")
EMAILJS_PRIVATE_KEY = os.getenv("EMAILJS_PRIVATE_KEY")
EMAILJS_SERVICE_ID = os.getenv("EMAILJS_SERVICE_ID")
EMAILJS_TEMPLATE_ID = os.getenv("EMAILJS_TEMPLATE_ID")

# Security flags
ENFORCE_HTTPS = os.getenv("ENFORCE_HTTPS", "false").lower() == "true"
_hosts = os.getenv("ALLOWED_HOSTS", "").strip()
ALLOWED_HOSTS = _hosts.split(",") if _hosts else ["*"]  # comma-separated or * for all

# Rate limiting (requests per minute)
RATE_LIMIT_LOGIN = int(os.getenv("RATE_LIMIT_LOGIN", "5"))
RATE_LIMIT_REGISTER = int(os.getenv("RATE_LIMIT_REGISTER", "3"))
RATE_LIMIT_OTP = int(os.getenv("RATE_LIMIT_OTP", "3"))

# Service URLs (configurable for deployment)
BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:7001")
LLM_SERVER_URL = os.getenv("LLM_SERVER_URL", "http://127.0.0.1:8000")
RAG_SERVER_URL = os.getenv("RAG_SERVER_URL", "http://127.0.0.1:7000")

# Request timeouts
LLM_REQUEST_TIMEOUT = int(os.getenv("LLM_REQUEST_TIMEOUT", "30"))  # seconds

# Password hashing cost (bcrypt rounds)
BCRYPT_ROUNDS = int(os.getenv("BCRYPT_ROUNDS", "12"))

# Development fallbacks (ONLY for local development)
if not IS_PRODUCTION:
    if not SESSION_SECRET:
        print("[WARNING] Using default SESSION_SECRET for development only!")
        SESSION_SECRET = "dev_secret_change_in_production_min_64_bytes_required_for_security"
    if not GOOGLE_CLIENT_ID:
        GOOGLE_CLIENT_ID = "YOUR_GOOGLE_CLIENT_ID"
        print("[WARNING] GOOGLE_CLIENT_ID not set - OAuth will not work")
    if not GOOGLE_CLIENT_SECRET:
        GOOGLE_CLIENT_SECRET = "YOUR_GOOGLE_CLIENT_SECRET"
        print("[WARNING] GOOGLE_CLIENT_SECRET not set - OAuth will not work")
    if not EMAILJS_PUBLIC_KEY:
        EMAILJS_PUBLIC_KEY = "YOUR_EMAILJS_PUBLIC_KEY"
        print("[WARNING] EMAILJS_PUBLIC_KEY not set - Email sending will not work")
    if not EMAILJS_PRIVATE_KEY:
        EMAILJS_PRIVATE_KEY = "YOUR_EMAILJS_PRIVATE_KEY"
        print("[WARNING] EMAILJS_PRIVATE_KEY not set - Email sending will not work")
    if not EMAILJS_SERVICE_ID:
        EMAILJS_SERVICE_ID = "YOUR_EMAILJS_SERVICE_ID"
        print("[WARNING] EMAILJS_SERVICE_ID not set - Email sending will not work")
    if not EMAILJS_TEMPLATE_ID:
        EMAILJS_TEMPLATE_ID = "YOUR_EMAILJS_TEMPLATE_ID"
        print("[WARNING] EMAILJS_TEMPLATE_ID not set - Email sending will not work")

# Production validation
if IS_PRODUCTION:
    missing_secrets = []
    
    if not SESSION_SECRET or len(SESSION_SECRET) < 64:
        missing_secrets.append("SESSION_SECRET (must be 64+ bytes)")
    if not GOOGLE_CLIENT_ID:
        missing_secrets.append("GOOGLE_CLIENT_ID")
    if not GOOGLE_CLIENT_SECRET:
        missing_secrets.append("GOOGLE_CLIENT_SECRET")
    if not EMAILJS_PUBLIC_KEY:
        missing_secrets.append("EMAILJS_PUBLIC_KEY")
    if not EMAILJS_PRIVATE_KEY:
        missing_secrets.append("EMAILJS_PRIVATE_KEY")
    if not EMAILJS_SERVICE_ID:
        missing_secrets.append("EMAILJS_SERVICE_ID")
    if not EMAILJS_TEMPLATE_ID:
        missing_secrets.append("EMAILJS_TEMPLATE_ID")
    
    if missing_secrets:
        print("\n" + "="*70)
        print("🚨 FATAL: Missing required environment variables for production:")
        for secret in missing_secrets:
            print(f"  - {secret}")
        print("\nSet these in your environment before starting the server.")
        print("="*70 + "\n")
        sys.exit(1)
    
    if not ENFORCE_HTTPS:
        print("\n⚠️  WARNING: HTTPS not enforced. Set ENFORCE_HTTPS=true in production!\n")

# Validate session secret length
if len(SESSION_SECRET) < 32:
    print("\n🚨 WARNING: SESSION_SECRET is too short! Use at least 64 bytes.\n")


# Google OAuth Configuration
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "YOUR_GOOGLE_CLIENT_ID_HERE")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "YOUR_GOOGLE_CLIENT_SECRET_HERE")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:7001/auth/google/callback")

# Model & service endpoints
# Points directly to Ollama's built-in OpenAI-compatible endpoint.
# main_llm_server.py is NOT used — it was just a redundant middleman.
LLM_URL = os.getenv("LLM_URL", "http://127.0.0.1:11434/api/chat")

# Ollama configuration — GPU inference via local Ollama service
# Model name must match exactly what `ollama list` shows
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "127.0.0.1")
OLLAMA_PORT = int(os.getenv("OLLAMA_PORT", "11434"))
OLLAMA_CLI = os.getenv("OLLAMA_CLI", "ollama")

# Speech Recognition - faster-whisper (replaces Vosk)
# STABILIZATION: tiny.en on CPU with int8 to free GPU entirely for LLM + XTTS
WHISPER_MODEL_PATH = Path(os.getenv("WHISPER_MODEL_PATH", str(ROOT / "backend" / "Models" / "faster-whisper-tiny.en")))
WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "tiny.en")  # tiny.en — CPU-only, frees GPU
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cpu")  # cpu — GPU reserved for LLM + XTTS
WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8")  # int8 for CPU efficiency
WHISPER_BEAM_SIZE = int(os.getenv("WHISPER_BEAM_SIZE", "1"))  # beam=1 for speed
WHISPER_VAD_FILTER = os.getenv("WHISPER_VAD_FILTER", "true").lower() == "true"  # Voice Activity Detection

# Legacy (deprecated - keeping for migration)
VOSK_MODEL_PATH = Path(os.getenv("VOSK_MODEL_PATH", str(ROOT / "backend" / "Models" / "vosk-model-en-us-0.22-lgraph")))

# Persistence paths
CHROMA_DB_PATH = Path(os.getenv("CHROMA_DB_PATH", str(ROOT / "backend" / "chroma_db")))
DB_PATH = Path(os.getenv("DB_PATH", str(ROOT / "backend" / "conversations.db")))
ANALYTICS_DB = Path(os.getenv("ANALYTICS_DB", str(ROOT / "backend" / "analytics.db")))

# Assets
ASSETS_DIR = Path(os.getenv("ASSETS_DIR", str(ROOT / "backend" / "assets")))
ASSETS_DIR.mkdir(parents=True, exist_ok=True)

# Embedding model
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")

# Development flags
DEVELOPMENT = os.getenv("DEVELOPMENT", "1") != "0"

# LLM / GPU settings
# GPU offloading is handled entirely by Ollama (ggml-cuda backend).
# Set CUDA_VISIBLE_DEVICES=0 in your environment before starting Ollama
# to ensure it loads the model onto your NVIDIA GPU.
# The old llama-cpp-python settings (ENFORCE_GPU, N_GPU_LAYERS, N_CTX, N_BATCH)
# are no longer used — Ollama manages layer offloading automatically.
MODEL_PATH = os.getenv(
    "MODEL_PATH",
    str(
        Path(
            ROOT
        )
        / "backend"
        / "Models"
        / "Qwen2.5-7B-LLM"
    ),
)


__all__ = [
    "ROOT",
    "SESSION_SECRET",
    "SESSION_COOKIE",
    "LLM_URL",
    "WHISPER_MODEL_PATH",
    "WHISPER_MODEL_SIZE",
    "WHISPER_DEVICE",
    "WHISPER_COMPUTE_TYPE",
    "WHISPER_BEAM_SIZE",
    "WHISPER_VAD_FILTER",
    "VOSK_MODEL_PATH",  # deprecated
    "CHROMA_DB_PATH",
    "DB_PATH",
    "ANALYTICS_DB",
    "ASSETS_DIR",
    "EMBEDDING_MODEL",
    "DEVELOPMENT",
    "MODEL_PATH",
    "OLLAMA_MODEL",
    "OLLAMA_HOST",
    "OLLAMA_PORT",
    "OLLAMA_CLI",
]
