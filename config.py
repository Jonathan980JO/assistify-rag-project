#NEW
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
LLM_SERVER_URL = os.getenv("LLM_SERVER_URL", "http://127.0.0.1:8010")
LLM_SERVER_PORT = int(os.getenv("LLM_SERVER_PORT", "8010"))
RAG_SERVER_URL = os.getenv("RAG_SERVER_URL", "http://127.0.0.1:7000")

# Request timeouts
LLM_REQUEST_TIMEOUT = int(os.getenv("LLM_REQUEST_TIMEOUT", "30"))  # seconds

# Password hashing cost (bcrypt rounds)
BCRYPT_ROUNDS = int(os.getenv("BCRYPT_ROUNDS", "12"))

# Explicit opt-in for username==password dev logins (never enabled in production).
ALLOW_DEV_LOGIN_FALLBACK = (
    not IS_PRODUCTION
    and os.getenv("ALLOW_DEV_LOGIN_FALLBACK", "false").lower() in {"1", "true", "yes", "on"}
)

# Dev-only: create accounts on POST /register without EmailJS OTP (never in production).
SKIP_EMAIL_OTP = (
    not IS_PRODUCTION
    and os.getenv("SKIP_EMAIL_OTP", "false").lower() in {"1", "true", "yes", "on"}
)

# Public customer chat without login (enabled by default in development).
ALLOW_PUBLIC_GUEST_CHAT = os.getenv(
    "ALLOW_PUBLIC_GUEST_CHAT",
    "true" if not IS_PRODUCTION else "false",
).lower() in {"1", "true", "yes", "on"}

GUEST_ID_COOKIE = "guest_id"
GUEST_OWNER_HEADER = "X-Guest-Owner"

# Login-server proxy timeout when forwarding GET /kb_status to RAG during heavy indexing.
KB_STATUS_PROXY_TIMEOUT_S = max(
    10,
    int(os.getenv("KB_STATUS_PROXY_TIMEOUT_S", "60")),
)

# When enabled, chat/RAG queries require tenant membership (customers) or staff
# assignment (admin/employee). Off by default in development; on in production unless
# explicitly disabled via ENFORCE_CHAT_TENANT_MEMBERSHIP=false.
_ENFORCE_MEMBERSHIP_ENV = os.getenv("ENFORCE_CHAT_TENANT_MEMBERSHIP", "").strip().lower()
if _ENFORCE_MEMBERSHIP_ENV in {"1", "true", "yes", "on"}:
    ENFORCE_CHAT_TENANT_MEMBERSHIP = True
elif _ENFORCE_MEMBERSHIP_ENV in {"0", "false", "no", "off"}:
    ENFORCE_CHAT_TENANT_MEMBERSHIP = False
else:
    ENFORCE_CHAT_TENANT_MEMBERSHIP = IS_PRODUCTION

# Development fallbacks (ONLY for local development)
if not IS_PRODUCTION:
    if not SESSION_SECRET:
        # Generate a strong dev secret and persist it so sessions survive restarts.
        # This avoids noisy warnings and prevents accidentally running with a weak static secret.
        try:
            from pathlib import Path
            import secrets
            _secret_path = Path(__file__).resolve().parent / "._assistify_session_secret"
            if _secret_path.exists():
                SESSION_SECRET = _secret_path.read_text(encoding="utf-8").strip()
            else:
                SESSION_SECRET = secrets.token_hex(48)  # 96 hex chars
                _secret_path.write_text(SESSION_SECRET, encoding="utf-8")
            if len(SESSION_SECRET) < 64:
                # Extremely unlikely, but keep a safe floor
                SESSION_SECRET = (SESSION_SECRET + secrets.token_hex(48))[:96]
        except Exception:
            # Last resort fallback: keep behavior but still use a long secret
            import secrets
            SESSION_SECRET = secrets.token_hex(48)
    if not GOOGLE_CLIENT_ID:
        GOOGLE_CLIENT_ID = "YOUR_GOOGLE_CLIENT_ID"
    if not GOOGLE_CLIENT_SECRET:
        GOOGLE_CLIENT_SECRET = "YOUR_GOOGLE_CLIENT_SECRET"
    if not EMAILJS_PUBLIC_KEY:
        EMAILJS_PUBLIC_KEY = "YOUR_EMAILJS_PUBLIC_KEY"
    if not EMAILJS_PRIVATE_KEY:
        EMAILJS_PRIVATE_KEY = "YOUR_EMAILJS_PRIVATE_KEY"
    if not EMAILJS_SERVICE_ID:
        EMAILJS_SERVICE_ID = "YOUR_EMAILJS_SERVICE_ID"
    if not EMAILJS_TEMPLATE_ID:
        EMAILJS_TEMPLATE_ID = "YOUR_EMAILJS_TEMPLATE_ID"

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
        print("FATAL: Missing required environment variables for production:")
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
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "127.0.0.1")
OLLAMA_PORT = int(os.getenv("OLLAMA_PORT", "11434"))
OLLAMA_CLI = os.getenv("OLLAMA_CLI", "ollama")

# ========== GPU ALLOCATION POLICY ==========
# GPU is reserved for LLM (Ollama) and RAG (embeddings / reranker) only.
# Voice STT (faster-whisper) and TTS (Piper) always run on CPU.
RAG_USE_GPU = os.getenv("RAG_USE_GPU", "1").lower() not in {"0", "false", "no"}

# Speech Recognition - faster-whisper (replaces Vosk)
# Voice STT is CPU-only so VRAM stays available for Ollama + RAG embeddings.


def resolve_whisper_model_path(
    configured_path: Path | None = None,
    model_size: str | None = None,
) -> tuple[Path, str]:
    """Resolve faster-whisper model location for preflight and loaders.

    Returns (path, source) where source is one of: plain, cache, missing.
    When the configured plain directory is absent, checks the HuggingFace cache
    layout under backend/Models/models--Systran--faster-whisper-*/snapshots/*.
    """
    path = Path(configured_path or ROOT / "backend" / "Models" / "faster-whisper-small")
    if path.exists():
        return path, "plain"

    size = (model_size or os.getenv("WHISPER_MODEL_SIZE", "small.en")).strip()
    size_slug = size.replace(".", "-")
    models_root = ROOT / "backend" / "Models"
    cache_candidates = [
        models_root / f"models--Systran--faster-whisper-{size_slug}",
        models_root / "models--Systran--faster-whisper-small",
        models_root / "models--Systran--faster-whisper-small.en",
    ]
    seen: set[str] = set()
    for cache_dir in cache_candidates:
        key = str(cache_dir)
        if key in seen:
            continue
        seen.add(key)
        snapshots = cache_dir / "snapshots"
        if not snapshots.is_dir():
            continue
        for snapshot in sorted(snapshots.iterdir()):
            if snapshot.is_dir() and (snapshot / "model.bin").exists():
                return snapshot, "cache"

    return path, "missing"


WHISPER_MODEL_PATH = Path(os.getenv("WHISPER_MODEL_PATH", str(ROOT / "backend" / "Models" / "faster-whisper-small")))
WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "small.en")
WHISPER_MODEL_RESOLVED_PATH, WHISPER_MODEL_SOURCE = resolve_whisper_model_path(
    WHISPER_MODEL_PATH,
    WHISPER_MODEL_SIZE,
)
_requested_whisper_device = os.getenv("WHISPER_DEVICE", "cpu").strip().lower()
if _requested_whisper_device != "cpu":
    import warnings
    warnings.warn(
        f"WHISPER_DEVICE={_requested_whisper_device!r} ignored; "
        "voice STT is CPU-only (GPU reserved for LLM + RAG).",
        stacklevel=1,
    )
WHISPER_DEVICE = "cpu"
WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8")  # int8 for CPU efficiency
WHISPER_BEAM_SIZE = int(os.getenv("WHISPER_BEAM_SIZE", "1"))  # 1 for CPU speed; Arabic STT overrides to 5 in stt/transcribe.py
WHISPER_VAD_FILTER = os.getenv("WHISPER_VAD_FILTER", "true").lower() == "true"  # Voice Activity Detection

# Legacy (deprecated - keeping for migration)
VOSK_MODEL_PATH = Path(os.getenv("VOSK_MODEL_PATH", str(ROOT / "backend" / "Models" / "vosk-model-en-us-0.22-lgraph")))

# Persistence paths
CHROMA_DB_PATH = Path(os.getenv("CHROMA_DB_PATH", str(ROOT / "backend" / "chroma_db_v3")))
DB_PATH = Path(os.getenv("DB_PATH", str(ROOT / "backend" / "conversations.db")))
ANALYTICS_DB = Path(os.getenv("ANALYTICS_DB", str(ROOT / "backend" / "analytics.db")))

# Assets
ASSETS_DIR = Path(os.getenv("ASSETS_DIR", str(ROOT / "backend" / "assets")))
ASSETS_DIR.mkdir(parents=True, exist_ok=True)

# ========== MULTI-TENANCY ==========
# Tenant isolation uses collection-per-tenant for the vector store and a
# shared DB + tenant_id column for relational data. The default tenant keeps
# the historical collection / asset names so existing single-tenant data
# continues to work with zero migration.
DEFAULT_TENANT_ID = int(os.getenv("DEFAULT_TENANT_ID", "1"))


def _coerce_tenant_id(tenant_id) -> int:
    """Best-effort conversion of a tenant id to a positive int.

    Falls back to DEFAULT_TENANT_ID for None / blank / invalid values so
    callers never accidentally build a collection name like 'tNone_...'.
    """
    try:
        tid = int(tenant_id)
    except (TypeError, ValueError):
        return DEFAULT_TENANT_ID
    return tid if tid > 0 else DEFAULT_TENANT_ID


def tenant_collection_base(tenant_id) -> str:
    """Base ChromaDB collection name for a tenant.

    Tenant 1 (default) reuses the historical 'support_docs_v3' base so the
    existing collections stay the active KB. Other tenants are namespaced as
    't<id>_support_docs_v3'.
    """
    tid = _coerce_tenant_id(tenant_id)
    if tid == DEFAULT_TENANT_ID:
        return "support_docs_v3"
    return f"t{tid}_support_docs_v3"


def tenant_collection_name(tenant_id) -> str:
    """Active ('_latest') collection name for a tenant."""
    return f"{tenant_collection_base(tenant_id)}_latest"


def tenant_assets_dir(tenant_id) -> Path:
    """Per-tenant uploads directory (created on demand)."""
    tid = _coerce_tenant_id(tenant_id)
    directory = ASSETS_DIR / f"tenant_{tid}"
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return directory


def kb_asset_search_dirs(scope_tid: int | None) -> list[Path]:
    """Asset directories for KB list/delete for a tenant admin scope.

    ``scope_tid`` is the value from ``_kb_admin_scope_tenant``: ``None`` for the
    default tenant (legacy root + tenant subdir), otherwise the tenant id.
    Tenant subdir is listed first so callers deduplicating by filename prefer it
    over legacy root copies.
    """
    if scope_tid is None:
        return [tenant_assets_dir(DEFAULT_TENANT_ID), ASSETS_DIR]
    return [tenant_assets_dir(scope_tid)]

# Embedding model
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "intfloat/multilingual-e5-base")

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


def assert_production_config() -> None:
    """Fail fast when production is misconfigured. Call from server startup."""
    if not IS_PRODUCTION:
        return
    if not SESSION_SECRET or len(SESSION_SECRET) < 64:
        raise RuntimeError(
            "SESSION_SECRET must be set to 64+ bytes when ENVIRONMENT=production"
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
    "RAG_USE_GPU",
    "VOSK_MODEL_PATH",  # deprecated
    "CHROMA_DB_PATH",
    "DB_PATH",
    "ANALYTICS_DB",
    "ASSETS_DIR",
    "DEFAULT_TENANT_ID",
    "tenant_collection_base",
    "tenant_collection_name",
    "tenant_assets_dir",
    "EMBEDDING_MODEL",
    "DEVELOPMENT",
    "MODEL_PATH",
    "OLLAMA_MODEL",
    "OLLAMA_HOST",
    "OLLAMA_PORT",
    "OLLAMA_CLI",
    "ALLOW_DEV_LOGIN_FALLBACK",
    "SKIP_EMAIL_OTP",
    "ALLOW_PUBLIC_GUEST_CHAT",
    "GUEST_ID_COOKIE",
    "GUEST_OWNER_HEADER",
    "KB_STATUS_PROXY_TIMEOUT_S",
    "ENFORCE_CHAT_TENANT_MEMBERSHIP",
    "LLM_SERVER_PORT",
    "assert_production_config",
]
