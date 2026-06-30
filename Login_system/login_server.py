from fastapi import FastAPI, Request, Form, Depends, status, HTTPException, WebSocket
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
import os
import backend.sqlite_compat  # noqa: F401 — patches sys.modules["sqlite3"] if needed
# Disable chromadb telemetry BEFORE any chromadb/knowledge_base imports
os.environ['ANONYMIZED_TELEMETRY'] = 'False'
os.environ['CHROMA_TELEMETRY_IMPL'] = 'none'
import logging
logging.getLogger('chromadb.telemetry.product.posthog').setLevel(logging.CRITICAL)
# Ensure posthog.capture compatibility (stub if needed) to avoid telemetry exceptions
try:
    import posthog
    def _safe_capture(*a, **k):
        try:
            return posthog.capture(*a, **k)
        except Exception:
            return None
    posthog.capture = _safe_capture
except Exception:
    import sys
    class _PosthogStub:
        @staticmethod
        def capture(*a, **k):
            return None
        @staticmethod
        def identify(*a, **k):
            return None
    sys.modules['posthog'] = _PosthogStub()
from fastapi import UploadFile, File
from pathlib import Path
import shutil
import asyncio
import aiohttp
from authlib.integrations.starlette_client import OAuth
import httpx
import random
import string
import re
from datetime import datetime, timedelta
import requests
import hashlib
import secrets
from collections import defaultdict
import time
import json
import base64
from logging.handlers import RotatingFileHandler

from passlib.context import CryptContext
from itsdangerous import URLSafeSerializer
import sqlite3
import uuid
from fastapi import Header
from typing import Optional
from pydantic import BaseModel, validator, constr, EmailStr

# Import secure configuration
from config import (
    SESSION_SECRET, SESSION_COOKIE, 
    GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REDIRECT_URI,
    EMAILJS_PUBLIC_KEY, EMAILJS_PRIVATE_KEY, EMAILJS_SERVICE_ID, EMAILJS_TEMPLATE_ID,
    ENFORCE_HTTPS, ALLOWED_HOSTS, IS_PRODUCTION,
    RATE_LIMIT_LOGIN, RATE_LIMIT_REGISTER, RATE_LIMIT_OTP,
    BCRYPT_ROUNDS, DEFAULT_TENANT_ID, kb_asset_search_dirs,
    ALLOW_DEV_LOGIN_FALLBACK, SKIP_EMAIL_OTP, ALLOW_PUBLIC_GUEST_CHAT, assert_production_config,
    KB_STATUS_PROXY_TIMEOUT_S,
)
from Login_system import guest_session

try:
    from Login_system.persistent_state import (
        ensure_persistent_state_schema,
        is_session_invalidated,
        invalidate_session as persist_invalidate_session,
        track_user_session,
        touch_user_session,
        get_session_last_activity,
        check_rate_limit as persist_check_rate_limit,
        check_account_lockout as persist_check_account_lockout,
        record_failed_login as persist_record_failed_login,
        set_account_lockout,
        clear_failed_attempts as persist_clear_failed_attempts,
        get_failed_attempt_count,
    )
except ImportError:
    from persistent_state import (
        ensure_persistent_state_schema,
        is_session_invalidated,
        invalidate_session as persist_invalidate_session,
        track_user_session,
        touch_user_session,
        get_session_last_activity,
        check_rate_limit as persist_check_rate_limit,
        check_account_lockout as persist_check_account_lockout,
        record_failed_login as persist_record_failed_login,
        set_account_lockout,
        clear_failed_attempts as persist_clear_failed_attempts,
        get_failed_attempt_count,
    )

try:
    from Login_system.memberships import (
        ensure_membership_schema,
        list_memberships_for_user,
        list_memberships_for_tenant,
        get_membership,
        get_membership_by_id,
        create_access_request,
        update_membership_status,
        approved_memberships,
        resolve_active_tenant_id,
        customer_has_approved_access,
        backfill_default_tenant_memberships,
    )
except ImportError:
    from memberships import (
        ensure_membership_schema,
        list_memberships_for_user,
        list_memberships_for_tenant,
        get_membership,
        get_membership_by_id,
        create_access_request,
        update_membership_status,
        approved_memberships,
        resolve_active_tenant_id,
        customer_has_approved_access,
        backfill_default_tenant_memberships,
    )

try:
    from Login_system.rbac import (
        assert_can_assign_role,
        assert_can_manage_user,
        sql_role_filter_for_caller,
        roles_assignable_by,
        MASTER_ADMIN_OR_HIGHER,
        TENANT_STAFF_ROLES,
    )
except ImportError:
    from rbac import (
        assert_can_assign_role,
        assert_can_manage_user,
        sql_role_filter_for_caller,
        roles_assignable_by,
        MASTER_ADMIN_OR_HIGHER,
        TENANT_STAFF_ROLES,
    )

# Password hashing with configurable cost
# Use bcrypt_sha256 (no 72-byte limit) + pbkdf2_sha256 (legacy) for backward compatibility
pwd_context = CryptContext(
    schemes=["bcrypt_sha256", "pbkdf2_sha256"], 
    default="bcrypt_sha256",
    deprecated=["pbkdf2_sha256"],  # Auto-upgrade to bcrypt_sha256 on login
    bcrypt_sha256__rounds=BCRYPT_ROUNDS
)

serializer = URLSafeSerializer(SESSION_SECRET)

# Security event logging setup
os.makedirs('logs', exist_ok=True)
security_logger = logging.getLogger('security')
security_logger.setLevel(logging.INFO)
security_handler = RotatingFileHandler(
    'logs/security.log',
    maxBytes=10*1024*1024,  # 10MB
    backupCount=5
)
security_handler.setFormatter(logging.Formatter('%(message)s'))
security_logger.addHandler(security_handler)

# General-purpose logger for this module (used for informational/debug logs)
logger = logging.getLogger('login_server')
logger.setLevel(logging.INFO)
login_handler = RotatingFileHandler(
    'logs/login.log',
    maxBytes=5*1024*1024,
    backupCount=3
)
login_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
logger.addHandler(login_handler)
logger.propagate = False


class _ExpectedUnauthProfileAccessLogFilter(logging.Filter):
    """Hide expected logged-out probes on /api/my-profile from uvicorn access logs."""

    _NEEDLE = '"GET /api/my-profile HTTP/1.1" 401'

    def filter(self, record: logging.LogRecord) -> bool:
        return self._NEEDLE not in record.getMessage()


logging.getLogger("uvicorn.access").addFilter(_ExpectedUnauthProfileAccessLogFilter())

_UUID_FILENAME_PREFIX = re.compile(r"^[0-9a-f]{8}_(.+)$", re.IGNORECASE)
_PDF_TEXT_CACHE = {}
_PDF_TEXT_CACHE_MAX = 16


def _display_filename(stored_name: str) -> str:
    from urllib.parse import unquote
    match = _UUID_FILENAME_PREFIX.match(stored_name or "")
    name = match.group(1) if match else (stored_name or "")
    return unquote(name)


def _cache_pdf_text(cache_key: str, mtime: float, content: str) -> None:
    _PDF_TEXT_CACHE[cache_key] = (mtime, content)
    while len(_PDF_TEXT_CACHE) > _PDF_TEXT_CACHE_MAX:
        _PDF_TEXT_CACHE.pop(next(iter(_PDF_TEXT_CACHE)))


def _extract_pdf_text_cached(file_path: Path) -> str:
    cache_key = str(file_path)
    mtime = file_path.stat().st_mtime
    cached = _PDF_TEXT_CACHE.get(cache_key)
    if cached and cached[0] == mtime:
        return cached[1]

    from PyPDF2 import PdfReader
    reader = PdfReader(file_path)
    pages = []
    for p in reader.pages:
        try:
            pages.append(p.extract_text() or "")
        except Exception:
            pages.append("")

    content = "\n\n".join(pages)
    _cache_pdf_text(cache_key, mtime, content)
    return content

def log_security_event(event_type: str, details: dict, severity: str = "INFO"):
    """Log security-relevant events in structured JSON format"""
    event = {
        "timestamp": datetime.utcnow().isoformat(),
        "event_type": event_type,
        "severity": severity,
        **details
    }
    security_logger.info(json.dumps(event))

app = FastAPI()

# Global exception handler to prevent sensitive data exposure
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle all unhandled exceptions to prevent information disclosure"""
    # Don't catch HTTPException - let FastAPI handle those (auth, validation, etc.)
    if isinstance(exc, HTTPException):
        raise exc
    
    # Log full error details server-side
    import traceback
    log_security_event("unhandled_exception", {
        "error_type": type(exc).__name__,
        "error_message": str(exc),
        "path": request.url.path,
        "method": request.method,
        "client_ip": request.client.host if request.client else "unknown",
        "traceback": traceback.format_exc() if not IS_PRODUCTION else None
    }, severity="ERROR")
    
    # Return generic error to user (hide sensitive details in production)
    if IS_PRODUCTION:
        msg = "Internal server error. Please contact support."
        return JSONResponse(
            status_code=500,
            content={"detail": msg, "error": msg}
        )
    else:
        # Show details in development for debugging
        msg = str(exc)
        return JSONResponse(
            status_code=500,
            content={
                "detail": msg,
                "error": msg,
                "type": type(exc).__name__,
                "path": request.url.path
            }
        )

# Security middleware
@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    """Add security headers to all responses"""
    try:
        response = await call_next(request)
    except Exception as e:
        # If call_next fails, don't add headers
        raise
    
    # Only add security headers to successful responses (not errors/redirects that might fail)
    if response.status_code < 400:
        # Security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        is_inline_pdf_preview = (
            request.url.path.startswith("/api/knowledge/files/") and (
                request.url.path.endswith("/preview") or
                (request.url.path.endswith("/download") and request.query_params.get("inline") in {"1", "true", "True"})
            )
        )
        if is_inline_pdf_preview:
            response.headers["X-Frame-Options"] = "SAMEORIGIN"
        else:
            response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        
        # Content Security Policy (only for HTML responses)
        if "text/html" in response.headers.get("content-type", ""):
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' https://cdn.emailjs.com https://cdn.jsdelivr.net; "
                "style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data: blob: https:; "
                "connect-src 'self' https://api.emailjs.com ws: wss:; "
                "font-src 'self' data:; "
                "media-src 'self' blob: data:; "
                "frame-src 'self' blob: data:; "
                "object-src 'self' blob: data:; "
                "worker-src 'self' blob:; "
                "frame-ancestors 'none';"
            )
        
        # HTTPS enforcement in production
        if ENFORCE_HTTPS:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        
        # Set CSRF token cookie if not present
        if not request.cookies.get("csrf_token"):
            csrf_token_value = secrets.token_urlsafe(32)
            response.set_cookie(
                key="csrf_token",
                value=csrf_token_value,
                httponly=False,
                secure=ENFORCE_HTTPS,
                samesite="lax",
                max_age=86400  # 24 hours
            )
    
    return response

# Trusted host middleware (prevent host header injection)
# Only enable if specific hosts are configured (not wildcard)
if ALLOWED_HOSTS and ALLOWED_HOSTS != ["*"] and ALLOWED_HOSTS[0] != "*":
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)

# CORS (adjust for your needs)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:7001", "http://127.0.0.1:7001"] if not IS_PRODUCTION else ALLOWED_HOSTS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

# Initialize OAuth
oauth = OAuth()
oauth.register(
    name='google',
    client_id=GOOGLE_CLIENT_ID,
    client_secret=GOOGLE_CLIENT_SECRET,
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'}
)

# WebSocket proxy target (RAG server)
RAG_WS_URL = "ws://127.0.0.1:7000/ws"
RAG_HTTP_BASE = "http://127.0.0.1:7000"

# Last successful kb_status snapshot per process (used when RAG is slow to respond).
_last_kb_status_snapshot: dict = {}


def _rag_proxy_headers(request: Request) -> dict:
    headers = {}
    cookie_header = request.headers.get("cookie")
    if cookie_header:
        headers["Cookie"] = cookie_header
    csrf = request.headers.get("x-csrf-token") or request.cookies.get("csrf_token")
    if csrf:
        headers["x-csrf-token"] = csrf
    return headers


def _guest_rag_proxy_headers(request: Request) -> dict:
    guest_id = guest_session.get_guest_id(request)
    if not guest_id:
        raise HTTPException(status_code=401, detail="Guest session required.")
    return guest_session.guest_rag_headers(request, guest_id)


def _require_public_guest_chat() -> None:
    if not ALLOW_PUBLIC_GUEST_CHAT:
        raise HTTPException(status_code=403, detail="Public guest chat is disabled.")


async def _rag_json_or_error(resp: aiohttp.ClientResponse):
    try:
        data = await resp.json(content_type=None)
    except Exception:
        data = {"detail": await resp.text()}
    if resp.status >= 400:
        raise HTTPException(status_code=resp.status, detail=data)
    return data

# Session management constants
SESSION_ABSOLUTE_TIMEOUT = 86400  # 24 hours
SESSION_IDLE_TIMEOUT = 1800  # 30 minutes
MAX_CONCURRENT_SESSIONS = 3

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_DURATION = 900  # 15 minutes

def check_rate_limit(identifier: str, limit: int, window_seconds: int = 60) -> bool:
    """Check if request is within rate limit. Returns True if allowed."""
    return persist_check_rate_limit(identifier, limit, window_seconds)

def check_account_lockout(username: str) -> tuple[bool, int]:
    """Check if account is locked out. Returns (is_locked, remaining_seconds)"""
    return persist_check_account_lockout(username)

def record_failed_login(username: str, ip_address: str):
    """Record failed login attempt and lock account if threshold exceeded"""
    count = persist_record_failed_login(username)

    log_security_event("login_failure", {
        "username": username,
        "ip_address": ip_address,
        "attempt_count": count
    }, severity="WARNING")

    if count >= MAX_FAILED_ATTEMPTS:
        set_account_lockout(username, time.time() + LOCKOUT_DURATION)
        log_security_event("account_lockout", {
            "username": username,
            "ip_address": ip_address,
            "lockout_duration_seconds": LOCKOUT_DURATION
        }, severity="CRITICAL")

def clear_failed_attempts(username: str):
    """Clear failed login attempts after successful login"""
    persist_clear_failed_attempts(username)

def create_session_token(username: str, role: str, auth_provider: str = "local", **extra_data) -> str:
    """Create a new session token with security metadata"""
    session_id = secrets.token_urlsafe(32)
    now = time.time()
    
    session_data = {
        "username": username,
        "role": role,
        "auth_provider": auth_provider,
        "session_id": session_id,
        "created_at": now,
        "last_activity": now,
        **extra_data
    }
    
    # Get user ID + tenant for session tracking and tenant resolution.
    conn = get_db()
    c = conn.cursor()
    c.execute(
        """
        SELECT u.id, u.tenant_id, t.slug
        FROM users u
        LEFT JOIN tenants t ON u.tenant_id = t.id
        WHERE u.username=?
        """,
        (username,),
    )
    row = c.fetchone()
    conn.close()

    # Embed tenant identity in the signed cookie so downstream services
    # (e.g. the RAG server) can scope every request without another DB hit.
    # Caller-provided tenant_id (via **extra_data) wins if present.
    if "tenant_id" not in session_data:
        session_data["tenant_id"] = (row[1] if row and row[1] is not None else DEFAULT_TENANT_ID)
    if "tenant_slug" not in session_data and row and len(row) > 2 and row[2]:
        session_data["tenant_slug"] = row[2]

    role_val = str(session_data.get("role") or role or "").lower()
    username_val = str(session_data.get("username") or username or "")
    user_tenant_raw = session_data.get("tenant_id")
    if user_tenant_raw is None and row and row[1] is not None:
        user_tenant_raw = row[1]

    if "active_tenant_id" not in session_data:
        conn_active = get_db()
        active_tid = resolve_active_tenant_id(
            conn_active,
            role=role_val,
            username=username_val,
            user_tenant_id=user_tenant_raw,
            session_active_tenant_id=extra_data.get("active_tenant_id"),
            requested_tenant_id=extra_data.get("active_tenant_id"),
        )
        conn_active.close()
        if active_tid is not None:
            session_data["active_tenant_id"] = active_tid
        elif role_val != "customer":
            session_data["active_tenant_id"] = int(user_tenant_raw or DEFAULT_TENANT_ID)

    if role_val == "customer" and session_data.get("active_tenant_id"):
        session_data["tenant_id"] = session_data["active_tenant_id"]
        conn_slug = get_db()
        c_slug = conn_slug.cursor()
        c_slug.execute("SELECT slug FROM tenants WHERE id=?", (session_data["active_tenant_id"],))
        slug_row = c_slug.fetchone()
        conn_slug.close()
        if slug_row and slug_row[0]:
            session_data["tenant_slug"] = slug_row[0]

    if row:
        user_id = row[0]
        evicted_session = track_user_session(
            user_id, session_id, now, MAX_CONCURRENT_SESSIONS
        )
        if evicted_session:
            log_security_event("concurrent_session_limit", {
                "username": username,
                "user_id": user_id,
                "max_sessions": MAX_CONCURRENT_SESSIONS,
                "invalidated_session": evicted_session
            })
    
    return serializer.dumps(session_data)

def validate_session(session_data: dict) -> tuple[bool, str]:
    """Validate session hasn't expired or been invalidated. Returns (is_valid, error_message)"""
    session_id = session_data.get("session_id")
    if session_id and is_session_invalidated(session_id):
        return False, "Session invalidated"

    created_at = session_data.get("created_at", 0)
    now = time.time()

    if now - created_at > SESSION_ABSOLUTE_TIMEOUT:
        return False, "Session expired (absolute timeout)"

    # Use the DB-persisted last_activity (updated on every request via touch_user_session)
    # instead of the cookie value which is frozen at login time.
    db_last_activity = get_session_last_activity(session_id) if session_id else None
    last_activity = db_last_activity if db_last_activity is not None else session_data.get("last_activity", created_at)

    if now - last_activity > SESSION_IDLE_TIMEOUT:
        return False, "Session expired (idle timeout)"

    session_data["last_activity"] = now
    if session_id:
        touch_user_session(session_id, now)

    return True, ""

def invalidate_session(session_id: str):
    """Mark a session as invalidated"""
    persist_invalidate_session(session_id)

class WebSocketRateLimiter:
    """Rate limiter for WebSocket messages to prevent flooding"""
    def __init__(self, max_messages: int = 20, window_seconds: int = 60):
        self.max_messages = max_messages
        self.window_seconds = window_seconds
        self.messages = []
    
    def is_allowed(self) -> bool:
        """Check if a new message is allowed within rate limit"""
        now = time.time()
        # Remove messages outside the time window
        self.messages = [msg_time for msg_time in self.messages if now - msg_time <= self.window_seconds]
        
        if len(self.messages) >= self.max_messages:
            return False
        
        self.messages.append(now)
        return True
    
    def get_remaining_time(self) -> int:
        """Get seconds until rate limit resets"""
        if not self.messages:
            return 0
        now = time.time()
        oldest = min(self.messages)
        remaining = self.window_seconds - (now - oldest)
        return max(0, int(remaining))

# --- Phase 1 refactor: pure validation/OTP helpers moved to Login_system.utils ---
# Definitions now live in Login_system/utils/validation.py and Login_system/utils/otp.py.
# Re-imported here to preserve the original module-level public names and behavior.
from Login_system.utils.otp import hash_otp, verify_otp_hash, generate_otp
from Login_system.utils.validation import (
    validate_password,
    validate_email,
    validate_username,
    sanitize_input,
)

# Phase 7 cleanup: removed dead helper verify_otp_hash_old (no call sites in the
# codebase; superseded by verify_otp_hash in Login_system/utils/otp.py).

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _resolve_react_ui_build_dir() -> Path:
    """Locate exported React UI (Next.js `out/`, or legacy dist/build folder names)."""
    for name in ("out", "dist", "build"):
        candidate = _REPO_ROOT / "assistify-ui-design" / name
        if (candidate / "index.html").is_file():
            return candidate
    return _REPO_ROOT / "assistify-ui-design" / "out"


REACT_UI_DIR = _resolve_react_ui_build_dir()
REACT_UI_NEXT_DIR = REACT_UI_DIR / "_next"
FAVICON_PATH = Path(__file__).resolve().parent / "static" / "favicon.ico"
REACT_PUBLIC_PATH_PREFIXES = (
    "login",
    "register",
    "verify-otp",
    "forgot-password",
    "reset-password",
    "change-username",
    "guest",
)


def react_redirect(path: str, query: str = "") -> str:
    """Map legacy path to static React export under /frontend/."""
    normalized = path if path.startswith("/") else f"/{path}"
    normalized = normalized.rstrip("/") or "/"
    if normalized == "/":
        url = "/frontend/"
    else:
        url = f"/frontend{normalized}/"
    if query:
        q = query.lstrip("?")
        url = f"{url}?{q}"
    return url


def _react_path_is_public(path: str) -> bool:
    normalized = (path or "").strip("/").lower()
    if not normalized:
        return False
    first = normalized.split("/")[0]
    return first in REACT_PUBLIC_PATH_PREFIXES


def _frontend_relative_path(path: str) -> str:
    """Strip /frontend prefix for public-path checks."""
    if path == "/frontend":
        return ""
    if path.startswith("/frontend/"):
        return path[len("/frontend/"):].lstrip("/")
    return path


def _should_set_guest_cookie(path: str) -> bool:
    if not ALLOW_PUBLIC_GUEST_CHAT:
        return False
    return (
        path.startswith("/frontend/guest")
        or path.startswith("/api/guest")
        or path == "/api/public/chat-tenants"
    )


def auth_form_redirect(path: str, **params: str) -> RedirectResponse:
    from urllib.parse import urlencode
    q = urlencode({k: v for k, v in params.items() if v is not None and v != ""})
    return RedirectResponse(url=react_redirect(path, q), status_code=status.HTTP_303_SEE_OTHER)


def _optional_login_for_react(path: str):
    if _react_path_is_public(path):
        return None
    return Depends(require_login())


if REACT_UI_NEXT_DIR.is_dir():
    app.mount(
        "/frontend/_next",
        StaticFiles(directory=str(REACT_UI_NEXT_DIR)),
        name="react_ui_assets",
    )

# --- Phase 2 refactor: users-DB connection factory moved to repositories.db ---
# DB_PATH + get_db now live in Login_system/repositories/db.py. Re-imported here
# to preserve the original module-level names and the exact users.db path.
from Login_system.repositories.db import DB_PATH, get_db


def create_user(username, password, role, mfa_enabled=0, mfa_secret=None, tenant_id=None):
    if tenant_id is None:
        tenant_id = DEFAULT_TENANT_ID
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        INSERT OR IGNORE INTO users (username, password_hash, role, mfa_enabled, mfa_secret, tenant_id)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (username, pwd_context.hash(password), role, int(mfa_enabled), mfa_secret, tenant_id))
    conn.commit()
    conn.close()



def verify_csrf(request: Request, *, form_token: str | None = None):
    """Simple CSRF verification: header X-CSRF-Token or form csrf_token must match cookie."""
    cookie = request.cookies.get("csrf_token")
    if not cookie:
        raise HTTPException(status_code=403, detail="CSRF token missing or invalid")
    header = request.headers.get("x-csrf-token")
    if header == cookie or (form_token and form_token == cookie):
        return
    raise HTTPException(status_code=403, detail="CSRF token missing or invalid")


def init_db():
    conn = get_db()
    c = conn.cursor()

    # ----- Multi-tenancy: central tenants registry -----
    # Authoritative list of tenants. Each domain manager (admin) and their
    # users belong to exactly one tenant; the default tenant keeps legacy data.
    c.execute("""
        CREATE TABLE IF NOT EXISTS tenants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            slug TEXT UNIQUE NOT NULL,
            active INTEGER DEFAULT 1,
            plan TEXT DEFAULT 'standard',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Ensure the default tenant exists with the canonical id.
    c.execute("SELECT id FROM tenants WHERE id=?", (DEFAULT_TENANT_ID,))
    if not c.fetchone():
        c.execute(
            "INSERT INTO tenants (id, name, slug, active, plan) VALUES (?, ?, ?, 1, 'standard')",
            (DEFAULT_TENANT_ID, "Default", "default"),
        )
    ensure_membership_schema(c)
    conn.commit()

    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users';")
    if not c.fetchone():
        c.execute("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE,
                password_hash TEXT,
                role TEXT,
                mfa_enabled INTEGER DEFAULT 0,
                mfa_secret TEXT,
                active INTEGER DEFAULT 1,
                google_id TEXT UNIQUE,
                email TEXT,
                profile_picture TEXT,
                auth_provider TEXT DEFAULT 'local',
                email_verified INTEGER DEFAULT 0,
                full_name TEXT,
                tenant_id INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        try:
            from Login_system.dev_users import seed_dev_users
        except ImportError:
            from dev_users import seed_dev_users

        seed_dev_users(c, pwd_context, tenant_id=DEFAULT_TENANT_ID)
        conn.commit()
        backfill_default_tenant_memberships(conn, DEFAULT_TENANT_ID)
        conn.commit()
    else:
        # Migrate legacy schema before membership backfill (needs users.tenant_id).
        c.execute("PRAGMA table_info(users)")
        columns = [col[1] for col in c.fetchall()]
        if 'active' not in columns:
            c.execute("ALTER TABLE users ADD COLUMN active INTEGER DEFAULT 1")
            conn.commit()
        if 'google_id' not in columns:
            c.execute("ALTER TABLE users ADD COLUMN google_id TEXT")
            conn.commit()
        if 'email' not in columns:
            c.execute("ALTER TABLE users ADD COLUMN email TEXT")
            conn.commit()
        if 'profile_picture' not in columns:
            c.execute("ALTER TABLE users ADD COLUMN profile_picture TEXT")
            conn.commit()
        if 'auth_provider' not in columns:
            c.execute("ALTER TABLE users ADD COLUMN auth_provider TEXT DEFAULT 'local'")
            conn.commit()
        if 'email_verified' not in columns:
            c.execute("ALTER TABLE users ADD COLUMN email_verified INTEGER DEFAULT 0")
            conn.commit()
        if 'full_name' not in columns:
            c.execute("ALTER TABLE users ADD COLUMN full_name TEXT")
            conn.commit()
        if 'created_at' not in columns:
            c.execute("ALTER TABLE users ADD COLUMN created_at TIMESTAMP")
            # Set default value for existing rows
            c.execute("UPDATE users SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL")
            conn.commit()
        if 'tenant_id' not in columns:
            c.execute(f"ALTER TABLE users ADD COLUMN tenant_id INTEGER DEFAULT {DEFAULT_TENANT_ID}")
            # Backfill existing rows onto the default tenant.
            c.execute("UPDATE users SET tenant_id=? WHERE tenant_id IS NULL", (DEFAULT_TENANT_ID,))
            conn.commit()
        backfill_default_tenant_memberships(conn, DEFAULT_TENANT_ID)
        conn.commit()
    
    # Add username_changed_at column
    c.execute("PRAGMA table_info(users)")
    columns = [col[1] for col in c.fetchall()]
    if 'username_changed_at' not in columns:
        c.execute("ALTER TABLE users ADD COLUMN username_changed_at TIMESTAMP")
        conn.commit()
    
    # Create OTP verification table
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='otp_verification';")
    if not c.fetchone():
        c.execute("""
            CREATE TABLE otp_verification (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL,
                otp_code TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL,
                verified INTEGER DEFAULT 0,
                temp_user_data TEXT,
                purpose TEXT DEFAULT 'registration'
            )
        """)
        conn.commit()
    else:
        # Add purpose column if it doesn't exist
        c.execute("PRAGMA table_info(otp_verification)")
        columns = [col[1] for col in c.fetchall()]
        if 'purpose' not in columns:
            c.execute("ALTER TABLE otp_verification ADD COLUMN purpose TEXT DEFAULT 'registration'")
            conn.commit()
    
    # Create audit logs table for admin monitoring
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='audit_logs';")
    if not c.fetchone():
        c.execute("""
            CREATE TABLE audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                action TEXT,
                old_value TEXT,
                new_value TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                ip_address TEXT,
                performed_by TEXT
            )
        """)
        conn.commit()
    else:
        # Add performed_by column if it doesn't exist
        c.execute("PRAGMA table_info(audit_logs)")
        columns = [col[1] for col in c.fetchall()]
        if 'performed_by' not in columns:
            c.execute("ALTER TABLE audit_logs ADD COLUMN performed_by TEXT")
            conn.commit()
    
    # Create customer support notes table
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='customer_notes';")
    if not c.fetchone():
        c.execute("""
            CREATE TABLE customer_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER NOT NULL,
                customer_username TEXT NOT NULL,
                note TEXT NOT NULL,
                created_by TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (customer_id) REFERENCES users (id)
            )
        """)
        conn.commit()
    
    # Create feedback/support tickets table
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='support_tickets';")
    if not c.fetchone():
        c.execute("""
            CREATE TABLE support_tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_number TEXT UNIQUE NOT NULL,
                customer_id INTEGER NOT NULL,
                customer_username TEXT NOT NULL,
                subject TEXT NOT NULL,
                description TEXT NOT NULL,
                status TEXT DEFAULT 'open',
                priority TEXT DEFAULT 'normal',
                assigned_to TEXT,
                assigned_to_role TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                resolved_at TIMESTAMP,
                escalated_to_admin INTEGER DEFAULT 0,
                resolution_notes TEXT,
                FOREIGN KEY (customer_id) REFERENCES users (id)
            )
        """)
        conn.commit()
    
    # Create ticket messages/updates table
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ticket_messages';")
    if not c.fetchone():
        c.execute("""
            CREATE TABLE ticket_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id INTEGER NOT NULL,
                sender_username TEXT NOT NULL,
                sender_role TEXT NOT NULL,
                message TEXT NOT NULL,
                is_internal_note INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (ticket_id) REFERENCES support_tickets (id)
            )
        """)
        conn.commit()
    
    # Create notifications table
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='notifications';")
    if not c.fetchone():
        c.execute("""
            CREATE TABLE notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_username TEXT NOT NULL,
                user_role TEXT NOT NULL,
                notification_type TEXT NOT NULL,
                title TEXT NOT NULL,
                message TEXT NOT NULL,
                link TEXT,
                is_read INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                priority TEXT DEFAULT 'normal',
                related_ticket_id INTEGER,
                FOREIGN KEY (related_ticket_id) REFERENCES support_tickets (id)
            )
        """)
        conn.commit()

    # Multi-tenant: scope support tickets to a business so admins/employees of
    # one tenant can never see another tenant's customer support tickets.
    c.execute("PRAGMA table_info(support_tickets)")
    _ticket_cols = [col[1] for col in c.fetchall()]
    if "tenant_id" not in _ticket_cols:
        c.execute(f"ALTER TABLE support_tickets ADD COLUMN tenant_id INTEGER DEFAULT {DEFAULT_TENANT_ID}")
        c.execute("UPDATE support_tickets SET tenant_id=? WHERE tenant_id IS NULL", (DEFAULT_TENANT_ID,))
        conn.commit()

    # Create query feedback table (thumbs up/down)
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='query_feedback';")
    if not c.fetchone():
        c.execute("""
            CREATE TABLE query_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                user_role TEXT NOT NULL,
                query_text TEXT NOT NULL,
                response_text TEXT NOT NULL,
                feedback_type TEXT NOT NULL,
                feedback_comment TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                ticket_created INTEGER DEFAULT 0,
                ticket_id INTEGER,
                FOREIGN KEY (ticket_id) REFERENCES support_tickets (id)
            )
        """)
        conn.commit()
    
    conn.close()


    ensure_persistent_state_schema()


@app.on_event("startup")
def on_startup():
    assert_production_config()
    init_db()


def auth_user(username_or_email, password):
    """Authenticate user with username OR email."""
    conn = get_db()
    c = conn.cursor()
    
    # Try to find user by username or email
    c.execute("""
        SELECT username, password_hash, role, active 
        FROM users 
        WHERE username=? OR email=?
    """, (username_or_email, username_or_email))
    res = c.fetchone()
    conn.close()
    
    if res:
        username, password_hash, role, is_active = res
        # Check if user is active
        if not is_active:
            return None, None
        
        # Development fallback: only when explicitly enabled (never in production).
        if ALLOW_DEV_LOGIN_FALLBACK and (not password_hash or password_hash.strip() == ""):
            if password == username:
                return username, role

        # Verify password against hash
        try:
            if pwd_context.verify(password, password_hash):
                # Check if password needs rehashing (e.g., deprecated scheme)
                if pwd_context.needs_update(password_hash):
                    conn = get_db()
                    c = conn.cursor()
                    new_hash = pwd_context.hash(password)
                    c.execute("UPDATE users SET password_hash=? WHERE username=?", (new_hash, username))
                    conn.commit()
                    conn.close()
                return username, role
        except Exception:
            if ALLOW_DEV_LOGIN_FALLBACK and password == username:
                return username, role
    return None, None


def _resolve_post_login_redirect(role: str, username: str) -> str:
    role = str(role or "").lower()
    if role == "superadmin":
        return "/superadmin"
    if role == "master_admin":
        return "/master_admin"
    if role == "admin":
        return "/admin"
    if role == "employee":
        return "/employee"
    conn = get_db()
    approved = approved_memberships(conn, username)
    conn.close()
    if not approved:
        return "/select-business"
    return "/main"


def _assert_target_user_in_caller_tenant(caller: dict, target_user_id: int) -> dict:
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id, username, role, tenant_id FROM users WHERE id=?", (int(target_user_id),))
    row = c.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    caller_role = str((caller or {}).get("role") or "").lower()
    if caller_role == "superadmin":
        target = {"id": row[0], "username": row[1], "role": row[2], "tenant_id": row[3]}
        return target
    caller_tid = int((caller or {}).get("tenant_id") or DEFAULT_TENANT_ID)
    target_tid = row[3]
    if target_tid is None or int(target_tid) != caller_tid:
        raise HTTPException(status_code=403, detail="Cannot manage users outside your business")
    target = {"id": row[0], "username": row[1], "role": row[2], "tenant_id": row[3]}
    assert_can_manage_user(caller, target)
    return target


def _tenant_scope_sql(user) -> tuple[str, list]:
    role = str((user or {}).get("role") or "").lower()
    if role == "superadmin":
        return "", []
    tid = int((user or {}).get("tenant_id") or DEFAULT_TENANT_ID)
    return " AND tenant_id = ?", [tid]


def get_or_create_google_user(google_id: str, email: str, name: str, picture: str):
    """Get existing Google user or create new customer account."""
    conn = get_db()
    c = conn.cursor()
    
    # Check if user exists by google_id
    c.execute("SELECT username, role, active FROM users WHERE google_id=?", (google_id,))
    res = c.fetchone()
    
    if res:
        conn.close()
        return {"username": res[0], "role": res[1]}
    
    # Check if email already exists
    c.execute("SELECT username FROM users WHERE email=?", (email,))
    existing = c.fetchone()
    
    if existing:
        # Link Google account to existing user
        c.execute("UPDATE users SET google_id=?, profile_picture=?, auth_provider='google' WHERE email=?", 
                  (google_id, picture, email))
        conn.commit()
        c.execute("SELECT username, role FROM users WHERE email=?", (email,))
        res = c.fetchone()
        conn.close()
        return {"username": res[0], "role": res[1]}
    
    # Create new customer account
    username = email.split('@')[0]
    base_username = username
    counter = 1
    
    # Ensure unique username
    while True:
        c.execute("SELECT username FROM users WHERE username=?", (username,))
        if not c.fetchone():
            break
        username = f"{base_username}{counter}"
        counter += 1
    
    # Insert new Google user as customer (default tenant for self-service signups)
    c.execute("""
        INSERT INTO users (username, password_hash, role, google_id, email, profile_picture, auth_provider, active, tenant_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (username, "", "customer", google_id, email, picture, "google", 1, None))
    
    conn.commit()
    conn.close()
    
    return {"username": username, "role": "customer"}


def _create_local_registered_user(
    *,
    username: str,
    password_hash: str,
    email: str,
    full_name: str,
    role: str = "customer",
    email_verified: int = 0,
) -> None:
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        INSERT INTO users (username, password_hash, role, email, full_name, email_verified, auth_provider, active, tenant_id)
        VALUES (?, ?, ?, ?, ?, ?, 'local', 1, ?)
    """, (username, password_hash, role, email, full_name, email_verified, DEFAULT_TENANT_ID))
    conn.commit()
    conn.close()


# generate_otp moved to Login_system/utils/otp.py (Phase 1 refactor); imported above.


# --- Phase 3 refactor: OTP persistence/email business logic moved to services ---
# store_otp, send_otp_email and verify_otp now live in
# Login_system/services/otp_service.py. Re-imported here to preserve the
# original module-level public names and behavior.
from Login_system.services.otp_service import store_otp, send_otp_email, verify_otp


def get_current_user(request: Request):
    token = request.cookies.get(SESSION_COOKIE)
    try:
        if token:
            data = serializer.loads(token)
            
            # Validate session (check timeouts and invalidation)
            is_valid, error_msg = validate_session(data)
            if not is_valid:
                log_security_event("session_validation_failed", {
                    "username": data.get("username"),
                    "session_id": data.get("session_id"),
                    "reason": error_msg
                }, severity="INFO")
                return None
            
            # Session is valid and last_activity was updated
            # Note: In a production system, you'd want to refresh the cookie
            # with updated last_activity, but that requires response access
            return data
    except Exception as e:
        log_security_event("session_decode_failed", {
            "error": str(e)
        }, severity="WARNING")
        return None


def _is_api_style_request(request: Request) -> bool:
    """JSON/API clients must get 401, not HTML redirects."""
    path = request.url.path
    if path.startswith("/api/") or path.startswith("/conversations"):
        return True
    accept = request.headers.get("accept", "")
    return "application/json" in accept


def _browser_login_redirect() -> RedirectResponse:
    return RedirectResponse(
        url=react_redirect("/login", "error=login"),
        status_code=status.HTTP_307_TEMPORARY_REDIRECT,
    )


@app.middleware("http")
async def frontend_auth_middleware(request: Request, call_next):
    """Require login for protected React export paths before static HTML is served."""
    path = request.url.path
    method = request.method.upper()

    if method in ("GET", "HEAD") and (path == "/frontend" or path.startswith("/frontend/")):
        if path.startswith("/frontend/_next"):
            return await call_next(request)

        relative = _frontend_relative_path(path)
        if not _react_path_is_public(relative) and not get_current_user(request):
            if method == "HEAD":
                return Response(status_code=401)
            return RedirectResponse(url=react_redirect("/login"), status_code=status.HTTP_307_TEMPORARY_REDIRECT)

    return await call_next(request)


@app.middleware("http")
async def guest_cookie_middleware(request: Request, call_next):
    """Issue guest identity only for guest-chat routes (not globally)."""
    response = await call_next(request)
    path = request.url.path
    if (
        response.status_code < 400
        and _should_set_guest_cookie(path)
        and not guest_session.get_guest_id(request)
    ):
        guest_session.set_guest_cookie(response, guest_session.new_guest_id())
    return response


def require_login(role=None):
    def wrapper(request: Request):
        user = get_current_user(request)
        if not user or (role and user.get("role") != role):
            if _is_api_style_request(request):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication required",
                )
            return _browser_login_redirect()
        return user
    return wrapper


def require_api_auth(role=None):
    """API authentication - returns 401 instead of redirect"""
    def wrapper(request: Request):
        user = get_current_user(request)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required"
            )
        if role and user.get("role") != role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions"
            )
        return user
    return wrapper


def require_role(*allowed_roles):
    """Require user to have one of the specified roles."""
    def wrapper(request: Request):
        user = get_current_user(request)
        if not user:
            if _is_api_style_request(request):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication required",
                )
            return _browser_login_redirect()
        if allowed_roles and user.get("role") not in allowed_roles:
            # Log unauthorized access attempt
            log_security_event("unauthorized_access", {
                "username": user.get("username"),
                "user_role": user.get("role"),
                "required_roles": list(allowed_roles),
                "endpoint": str(request.url.path)
            }, severity="WARNING")
            
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions"
            )
        return user
    return wrapper


def require_api_role(*allowed_roles):
    """API version - Require user to have one of the specified roles."""
    def wrapper(request: Request):
        user = get_current_user(request)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required"
            )
        if allowed_roles and user.get("role") not in allowed_roles:
            # Log unauthorized access attempt
            log_security_event("unauthorized_access", {
                "username": user.get("username"),
                "user_role": user.get("role"),
                "required_roles": list(allowed_roles),
                "endpoint": str(request.url.path)
            }, severity="WARNING")
            
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions"
            )
        return user
    return wrapper


def require_master_admin_or_higher():
    return require_api_role("master_admin", "superadmin")


def require_tenant_staff():
    return require_api_role("admin", "master_admin")


def require_normal_admin():
    return require_role("admin")


def require_tenant_staff_page():
    return require_role("admin", "master_admin")


def require_master_admin_page():
    return require_role("master_admin")


@app.get("/register", response_class=HTMLResponse)
def register_form(request: Request):
    error = request.query_params.get("error")
    q = f"error={error}" if error else ""
    return RedirectResponse(url=react_redirect("/register", q), status_code=status.HTTP_303_SEE_OTHER)


@app.post("/register")
async def register_user(
    request: Request,
    full_name: str = Form(...),
    email: str = Form(...),
    username: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...)
):
    """Handle user registration and send OTP."""
    import json
    
    # Rate limiting - 3 attempts per minute per IP
    client_ip = request.client.host
    if not check_rate_limit(f"register:{client_ip}", RATE_LIMIT_REGISTER, 60):
        return RedirectResponse(url="/register?error=rate_limit", status_code=status.HTTP_303_SEE_OTHER)
    
    # Sanitize inputs first
    full_name = sanitize_input(full_name, 100)
    email = sanitize_input(email, 254).lower()
    username = sanitize_input(username, 50)
    
    # Validate email format
    if not validate_email(email):
        return RedirectResponse(url="/register?error=invalid_email", status_code=status.HTTP_303_SEE_OTHER)
    
    # Validate username format
    is_valid, error_msg = validate_username(username)
    if not is_valid:
        return RedirectResponse(url="/register?error=invalid_username", status_code=status.HTTP_303_SEE_OTHER)
    
    # Validate passwords match
    if password != confirm_password:
        return RedirectResponse(url="/register?error=passwords_dont_match", status_code=status.HTTP_303_SEE_OTHER)
    
    # Validate password strength and length
    is_valid, error_msg = validate_password(password)
    if not is_valid:
        return RedirectResponse(url=f"/register?error=weak_password", status_code=status.HTTP_303_SEE_OTHER)
    
    # Check if username already exists
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT username FROM users WHERE username=?", (username,))
    if c.fetchone():
        conn.close()
        return RedirectResponse(url="/register?error=username_exists", status_code=status.HTTP_303_SEE_OTHER)
    
    # Check if email already exists
    c.execute("SELECT email FROM users WHERE email=?", (email,))
    if c.fetchone():
        conn.close()
        return RedirectResponse(url="/register?error=email_exists", status_code=status.HTTP_303_SEE_OTHER)
    
    conn.close()
    
    # Hash password with error handling
    try:
        password_hash = pwd_context.hash(password)
    except ValueError as e:
        return RedirectResponse(url="/register?error=invalid_password", status_code=status.HTTP_303_SEE_OTHER)
    except Exception as e:
        return RedirectResponse(url="/register?error=server_error", status_code=status.HTTP_303_SEE_OTHER)

    if SKIP_EMAIL_OTP:
        _create_local_registered_user(
            username=username,
            password_hash=password_hash,
            email=email,
            full_name=full_name,
            role="customer",
            email_verified=0,
        )
        print(f"[DEV] SKIP_EMAIL_OTP: created user {username} without OTP")
        return RedirectResponse(
            url="/?success=registration_complete",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    # Generate OTP
    otp_code = generate_otp()
    
    # Store temporary user data
    temp_user_data = json.dumps({
        "full_name": full_name,
        "email": email,
        "username": username,
        "password_hash": password_hash,
        "role": "customer"
    })
    
    # Store OTP
    store_otp(email, otp_code, temp_user_data)
    
    # Send OTP email server-side (secure)
    print(f"[EMAIL] Attempting to send OTP to {email}")
    email_sent = send_otp_email(email, full_name, otp_code)
    print(f"[EMAIL] Email sent status: {email_sent}")
    
    # Redirect to OTP verification page WITHOUT exposing OTP in URL
    return RedirectResponse(
        url=react_redirect("/verify-otp", f"email={email}"),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@app.get("/verify-otp", response_class=HTMLResponse)
def verify_otp_form(request: Request):
    email = request.query_params.get("email", "")
    error = request.query_params.get("error", "")
    q = "&".join(p for p in [f"email={email}" if email else "", f"error={error}" if error else ""] if p)
    return RedirectResponse(url=react_redirect("/verify-otp", q), status_code=status.HTTP_303_SEE_OTHER)


@app.post("/verify-otp")
async def verify_otp_code(
    request: Request,
    email: str = Form(...),
    otp_code: str = Form(...)
):
    """Verify OTP and create user account."""
    import json
    
    # Rate limiting - 3 attempts per minute per IP
    client_ip = request.client.host
    if not check_rate_limit(f"verify_otp:{client_ip}", RATE_LIMIT_OTP, 60):
        return RedirectResponse(
            url=f"/verify-otp?email={email}&error=rate_limit", 
            status_code=status.HTTP_303_SEE_OTHER
        )
    
    # Verify OTP
    temp_user_data = verify_otp(email, otp_code)
    
    if not temp_user_data:
        # Log failed OTP attempt for security monitoring
        conn = get_db()
        c = conn.cursor()
        c.execute("""
            INSERT INTO audit_logs (user_id, username, action, new_value, ip_address, performed_by)
            VALUES (NULL, ?, 'failed_otp_verification', ?, ?, 'system')
        """, (email, otp_code[:2] + "****", client_ip))  # Only log first 2 digits for security
        conn.commit()
        conn.close()
        
        return RedirectResponse(
            url=f"/verify-otp?email={email}&error=invalid_or_expired_otp", 
            status_code=status.HTTP_303_SEE_OTHER
        )
    
    # Parse user data
    user_data = json.loads(temp_user_data)

    # Create user account
    _create_local_registered_user(
        username=user_data["username"],
        password_hash=user_data["password_hash"],
        email=user_data["email"],
        full_name=user_data["full_name"],
        role=user_data["role"],
        email_verified=1,
    )
    
    # Redirect to login with success message
    return RedirectResponse(url="/?success=registration_complete", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/change-username", response_class=HTMLResponse)
def change_username_form(request: Request):
    error = request.query_params.get("error", "")
    success = request.query_params.get("success", "")
    q = "&".join(p for p in [f"error={error}" if error else "", f"success={success}" if success else ""] if p)
    return RedirectResponse(url=react_redirect("/change-username", q), status_code=status.HTTP_303_SEE_OTHER)


@app.post("/change-username")
async def change_username(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    new_username: str = Form(...),
    csrf_token: str = Form(None),
):
    """Process username change request (one-time only)."""
    verify_csrf(request, form_token=csrf_token)
    import re
    
    # Validate new username format
    if not re.match(r'^[a-zA-Z0-9_]{3,20}$', new_username):
        return RedirectResponse(
            url="/change-username?error=invalid_username",
            status_code=status.HTTP_303_SEE_OTHER
        )
    
    # Authenticate user with email and password
    conn = get_db()
    c = conn.cursor()
    
    c.execute("SELECT id, username, password_hash, username_changed_at FROM users WHERE email=?", (email,))
    user = c.fetchone()
    
    if not user or not pwd_context.verify(password, user[2]):
        conn.close()
        return RedirectResponse(
            url="/change-username?error=invalid_credentials",
            status_code=status.HTTP_303_SEE_OTHER
        )
    
    user_id, old_username, _, username_changed_at = user
    
    # Check if username was already changed
    if username_changed_at:
        conn.close()
        return RedirectResponse(
            url="/change-username?error=already_changed",
            status_code=status.HTTP_303_SEE_OTHER
        )
    
    # Check if new username is already taken
    c.execute("SELECT id FROM users WHERE username=?", (new_username,))
    if c.fetchone():
        conn.close()
        return RedirectResponse(
            url="/change-username?error=username_taken",
            status_code=status.HTTP_303_SEE_OTHER
        )
    
    # Get client IP for audit log
    client_ip = request.client.host if request.client else "unknown"
    
    # Update username and set changed timestamp
    c.execute("""
        UPDATE users 
        SET username=?, username_changed_at=CURRENT_TIMESTAMP 
        WHERE id=?
    """, (new_username, user_id))
    
    # Log the change in audit table
    c.execute("""
        INSERT INTO audit_logs (user_id, username, action, old_value, new_value, ip_address, performed_by)
        VALUES (?, ?, 'USERNAME_CHANGE', ?, ?, ?, ?)
    """, (user_id, new_username, old_username, new_username, client_ip, old_username))
    
    conn.commit()
    conn.close()
    
    print(f"[AUDIT] Username changed: {old_username} -> {new_username} (User ID: {user_id}, IP: {client_ip})")
    
    return RedirectResponse(url="/?success=username_changed", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/auth/google/login")
async def google_login(request: Request):
    """Initiate Google OAuth login flow."""
    redirect_uri = GOOGLE_REDIRECT_URI
    return await oauth.google.authorize_redirect(request, redirect_uri)


@app.get("/auth/google/callback")
async def google_callback(request: Request):
    """Handle Google OAuth callback."""
    try:
        # Exchange authorization code for access token
        token = await oauth.google.authorize_access_token(request)
        
        # Get user info from Google
        user_info = token.get('userinfo')
        if not user_info:
            # Fetch userinfo if not included in token
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    'https://www.googleapis.com/oauth2/v3/userinfo',
                    headers={'Authorization': f"Bearer {token['access_token']}"}
                )
                user_info = resp.json()
        
        google_id = user_info.get('sub')
        email = user_info.get('email')
        name = user_info.get('name', email.split('@')[0])
        picture = user_info.get('picture', '')
        
        if not google_id or not email:
            return RedirectResponse(url="/?error=google_auth_failed")
        
        # Get or create user (always as customer role)
        user_data = get_or_create_google_user(google_id, email, name, picture)
        
        # Create new session with security metadata
        session_token = create_session_token(
            user_data["username"], 
            user_data["role"], 
            auth_provider="google",
            email=email,
            picture=picture
        )
        
        # Log successful login
        log_security_event("login_success", {
            "username": user_data["username"],
            "role": user_data["role"],
            "auth_provider": "google",
            "email": email
        })
        
        csrf_token = str(uuid.uuid4())
        
        # Redirect based on role / membership
        response = RedirectResponse(
            url=_resolve_post_login_redirect(user_data["role"], user_data["username"]),
            status_code=status.HTTP_303_SEE_OTHER,
        )
        response.set_cookie(
            key=SESSION_COOKIE, 
            value=session_token, 
            httponly=True, 
            secure=ENFORCE_HTTPS, 
            samesite="strict"
        )
        response.set_cookie(
            key="csrf_token", 
            value=csrf_token, 
            httponly=False, 
            secure=ENFORCE_HTTPS, 
            samesite="strict"
        )
        
        return response
        
    except Exception as e:
        print(f"Google OAuth error: {e}")
        return RedirectResponse(url="/?error=google_auth_failed")


@app.get("/", response_class=HTMLResponse)
def root_redirect(request: Request):
    """Redirect root to React login or role home."""
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url=react_redirect("/login"), status_code=status.HTTP_303_SEE_OTHER)
    role = user.get("role")
    if role == "admin":
        return RedirectResponse(url=react_redirect("/admin"), status_code=status.HTTP_303_SEE_OTHER)
    if role == "master_admin":
        return RedirectResponse(url=react_redirect("/master_admin"), status_code=status.HTTP_303_SEE_OTHER)
    if role == "employee":
        return RedirectResponse(url=react_redirect("/employee"), status_code=status.HTTP_303_SEE_OTHER)
    if role == "superadmin":
        return RedirectResponse(url=react_redirect("/superadmin"), status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse(url=react_redirect("/main"), status_code=status.HTTP_303_SEE_OTHER)


@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    """Redirect to React login page."""
    error = request.query_params.get("error")
    q = f"error={error}" if error else ""
    return RedirectResponse(url=react_redirect("/login", q), status_code=status.HTTP_303_SEE_OTHER)


@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    # Rate limiting - 5 attempts per minute per IP
    client_ip = request.client.host
    if not check_rate_limit(f"login:{client_ip}", RATE_LIMIT_LOGIN, 60):
        log_security_event("rate_limit_exceeded", {
            "endpoint": "/login",
            "ip_address": client_ip,
            "limit": RATE_LIMIT_LOGIN
        }, severity="WARNING")
        return auth_form_redirect("/login", error="Too many login attempts. Please try again later.")
    
    # Check account lockout
    is_locked, remaining_seconds = check_account_lockout(username)
    if is_locked:
        minutes_remaining = (remaining_seconds + 59) // 60  # Round up
        log_security_event("lockout_attempt", {
            "username": username,
            "ip_address": client_ip,
            "remaining_seconds": remaining_seconds
        }, severity="WARNING")
        return auth_form_redirect(
            "/login",
            error=f"Account locked. Try again in {minutes_remaining} minute(s).",
        )
    
    # Accept username OR email for login
    actual_username, role = auth_user(username, password)
    if role:
        # Check if MFA is enabled for this user
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT id, mfa_enabled, mfa_secret FROM users WHERE username=?", (actual_username,))
        row = c.fetchone()
        conn.close()

        if row and row[1]:
            # MFA enabled, require mfa_token in form
            form = await request.form()
            mfa_token = form.get("mfa_token")
            if not mfa_token:
                return auth_form_redirect("/login", error="MFA token required")
            try:
                import pyotp
                totp = pyotp.TOTP(row[2])
                if not totp.verify(mfa_token):
                    record_failed_login(actual_username, client_ip)
                    return auth_form_redirect("/login", error="Invalid MFA token")
            except Exception:
                return auth_form_redirect("/login", error="MFA verification failed (pyotp required)")

        # Successful login - clear failed attempts and create session
        clear_failed_attempts(actual_username)
        
        # Invalidate any old session tokens for this user (prevent session fixation)
        old_session_token = request.cookies.get(SESSION_COOKIE)
        if old_session_token:
            try:
                old_session_data = serializer.loads(old_session_token)
                old_session_id = old_session_data.get("session_id")
                if old_session_id:
                    invalidate_session(old_session_id)
            except:
                pass  # Invalid old token, ignore
        
        # Create new session with security metadata
        token = create_session_token(actual_username, role, auth_provider="local")
        
        # Log successful login
        log_security_event("login_success", {
            "username": actual_username,
            "role": role,
            "ip_address": client_ip,
            "auth_provider": "local"
        })
        
        redirect_url = react_redirect(_resolve_post_login_redirect(role, actual_username))
        response = RedirectResponse(url=redirect_url, status_code=302)
        response.set_cookie(
            SESSION_COOKIE,
            token,
            httponly=True,
            secure=ENFORCE_HTTPS,
            samesite="strict",
            max_age=86400  # 24 hours
        )
        # set a CSRF cookie for form submissions
        csrf = uuid.uuid4().hex
        response.set_cookie(
            "csrf_token", 
            csrf, 
            httponly=False, 
            secure=ENFORCE_HTTPS, 
            samesite="strict",
            max_age=86400
        )
        return response
    else:
        # Failed login
        record_failed_login(username, client_ip)
        return auth_form_redirect("/login", error="Invalid credentials")


@app.get("/users")
def list_users(request: Request, user=Depends(require_tenant_staff())):
    conn = get_db()
    c = conn.cursor()
    scope_sql, scope_params = _tenant_scope_sql(user)
    role_sql, role_params = sql_role_filter_for_caller(user.get("role"))
    c.execute(
        f"SELECT id, username, role, mfa_enabled FROM users WHERE 1=1{scope_sql}{role_sql}",
        scope_params + role_params,
    )
    rows = c.fetchall()
    conn.close()
    users = [{"id": r[0], "username": r[1], "role": r[2], "mfa_enabled": bool(r[3])} for r in rows]
    return {"users": users}



class UserCreate(BaseModel):
    username: str
    password: str
    role: str
    
    @validator('username')
    def validate_username_format(cls, v):
        """Validate username format"""
        is_valid, error = validate_username(v)
        if not is_valid:
            raise ValueError(error)
        return v
    
    @validator('password')
    def validate_password_strength(cls, v):
        """Validate password meets security requirements"""
        is_valid, error = validate_password(v)
        if not is_valid:
            raise ValueError(error)
        return v
    
    @validator('role')
    def validate_role(cls, v):
        """Validate role is one of allowed values"""
        allowed_roles = ['employee', 'customer']
        if v not in allowed_roles:
            raise ValueError(f"Role must be one of: {', '.join(allowed_roles)}")
        return v



@app.post("/users")
def create_user_api(request: Request, data: UserCreate, admin=Depends(require_tenant_staff())):
    verify_csrf(request)
    assert_can_assign_role(admin.get("role"), data.role)
    tenant_id = int(admin.get("tenant_id") or DEFAULT_TENANT_ID)
    create_user(data.username, data.password, data.role, tenant_id=tenant_id)
    return {"status": "created", "username": data.username}



class UserUpdate(BaseModel):
    role: Optional[str] = None
    password: Optional[str] = None
    
    @validator('role')
    def validate_role(cls, v):
        """Validate role if provided"""
        if v is not None:
            allowed_roles = ['employee', 'customer']
            if v not in allowed_roles:
                raise ValueError(f"Role must be one of: {', '.join(allowed_roles)}")
        return v
    
    @validator('password')
    def validate_password_strength(cls, v):
        """Validate password if provided"""
        if v is not None:
            is_valid, error = validate_password(v)
            if not is_valid:
                raise ValueError(error)
        return v



@app.put("/users/{user_id}")
def update_user(request: Request, user_id: int, data: UserUpdate, admin=Depends(require_tenant_staff())):
    verify_csrf(request)
    target = _assert_target_user_in_caller_tenant(admin, user_id)
    if data.role:
        assert_can_assign_role(admin.get("role"), data.role)
    conn = get_db()
    c = conn.cursor()
    if data.role:
        c.execute("UPDATE users SET role=? WHERE id=?", (data.role, user_id))
    if data.password:
        c.execute("UPDATE users SET password_hash=? WHERE id=?", (pwd_context.hash(data.password), user_id))
    conn.commit()
    conn.close()
    return {"status": "updated"}



@app.delete("/users/{user_id}")
def delete_user(request: Request, user_id: int, admin=Depends(require_tenant_staff())):
    verify_csrf(request)
    _assert_target_user_in_caller_tenant(admin, user_id)
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM users WHERE id=?", (user_id,))
    conn.commit()
    conn.close()
    return {"status": "deleted"}



@app.post("/users/{user_id}/mfa-enable")
def enable_mfa(request: Request, user_id: int, admin=Depends(require_tenant_staff())):
    verify_csrf(request)
    _assert_target_user_in_caller_tenant(admin, user_id)
    try:
        import pyotp
    except Exception:
        raise HTTPException(status_code=500, detail="pyotp is required for MFA support")
    secret = pyotp.random_base32()
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE users SET mfa_enabled=1, mfa_secret=? WHERE id=?", (secret, user_id))
    c.execute("SELECT username FROM users WHERE id=?", (user_id,))
    row = c.fetchone()
    conn.commit()
    conn.close()
    username = row[0] if row else "user"
    uri = pyotp.totp.TOTP(secret).provisioning_uri(name=username, issuer_name="Assistify")
    return {"mfa_secret": secret, "provisioning_uri": uri}


@app.get("/admin")
def admin_dashboard(request: Request, user=Depends(require_normal_admin())):
    """Admin dashboard - returns HTML for browsers, JSON for API requests"""
    # Check if client wants JSON (API request)
    accept_header = request.headers.get("accept", "")
    if "application/json" in accept_header:
        return JSONResponse({"status": "ok", "role": "admin", "username": user.get("username")})
    # Return HTML for browser
    return RedirectResponse(url=react_redirect("/admin"), status_code=status.HTTP_302_FOUND)


@app.get("/employee")
def employee_dashboard(request: Request, user=Depends(require_role("admin", "master_admin", "employee"))):
    """Employee dashboard - returns HTML for browsers, JSON for API requests"""
    # Check if client wants JSON (API request)
    accept_header = request.headers.get("accept", "")
    if "application/json" in accept_header:
        return JSONResponse({"status": "ok", "role": "employee", "username": user.get("username")})
    # Return HTML for browser
    return RedirectResponse(url=react_redirect("/employee"), status_code=status.HTTP_302_FOUND)


@app.get("/master_admin")
def master_admin_dashboard(request: Request, user=Depends(require_master_admin_page())):
    accept_header = request.headers.get("accept", "")
    if "application/json" in accept_header:
        return JSONResponse({"status": "ok", "role": "master_admin", "username": user.get("username")})
    return RedirectResponse(url=react_redirect("/master_admin"), status_code=status.HTTP_302_FOUND)


@app.get("/master_admin/admins", response_class=HTMLResponse)
def master_admin_admins_page(request: Request, user=Depends(require_master_admin_page())):
    return RedirectResponse(url=react_redirect("/master_admin/admins"), status_code=status.HTTP_302_FOUND)


@app.get("/master_admin/users", response_class=HTMLResponse)
def master_admin_users_page(request: Request, user=Depends(require_master_admin_page())):
    return RedirectResponse(url=react_redirect("/master_admin/users"), status_code=status.HTTP_302_FOUND)


@app.get("/master_admin/knowledge", response_class=HTMLResponse)
def master_admin_knowledge_page(request: Request, user=Depends(require_master_admin_page())):
    return RedirectResponse(url=react_redirect("/master_admin/knowledge"), status_code=status.HTTP_302_FOUND)


@app.get("/master_admin/analytics", response_class=HTMLResponse)
def master_admin_analytics_page(request: Request, user=Depends(require_master_admin_page())):
    return RedirectResponse(url=react_redirect("/master_admin/analytics"), status_code=status.HTTP_302_FOUND)


@app.get("/master_admin/access-requests", response_class=HTMLResponse)
def master_admin_access_requests_page(request: Request, user=Depends(require_master_admin_page())):
    return RedirectResponse(url=react_redirect("/master_admin/access-requests"), status_code=status.HTTP_302_FOUND)


@app.get("/master_admin/tickets", response_class=HTMLResponse)
def master_admin_tickets_page(request: Request, user=Depends(require_master_admin_page())):
    return RedirectResponse(url=react_redirect("/master_admin/tickets"), status_code=status.HTTP_302_FOUND)


@app.get("/master_admin/audit-logs", response_class=HTMLResponse)
def master_admin_audit_logs_page(request: Request, user=Depends(require_master_admin_page())):
    return RedirectResponse(url=react_redirect("/master_admin/audit-logs"), status_code=status.HTTP_302_FOUND)


@app.get("/api/audit-logs")
def api_audit_logs(request: Request, user=Depends(require_api_role("admin", "master_admin")), limit: int = 200):
    """JSON audit logs for React admin UI (tenant-scoped for business admins)."""
    conn = get_db()
    c = conn.cursor()
    role = user.get("role")
    if role in ("master_admin", "admin"):
        tenant_id = int(user.get("tenant_id") or DEFAULT_TENANT_ID)
        c.execute(
            """
            SELECT id, username, action, old_value, new_value, ip_address, performed_by, timestamp
            FROM audit_logs
            WHERE user_id IN (SELECT id FROM users WHERE tenant_id=?)
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (tenant_id, int(limit)),
        )
    else:
        c.execute(
            """
            SELECT id, username, action, old_value, new_value, ip_address, performed_by, timestamp
            FROM audit_logs
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (int(limit),),
        )
    rows = c.fetchall()
    conn.close()
    logs = []
    for row in rows:
        logs.append({
            "id": row[0],
            "username": row[1],
            "action": row[2],
            "old_value": row[3],
            "new_value": row[4],
            "ip_address": row[5],
            "performed_by": row[6],
            "created_at": row[7],
        })
    return {"logs": logs}


@app.get("/customer")
def customer_dashboard(request: Request, user=Depends(require_login("customer"))):
    """Customer dashboard - returns HTML for browsers, JSON for API requests"""
    # Check if client wants JSON (API request)
    accept_header = request.headers.get("accept", "")
    if "application/json" in accept_header:
        return JSONResponse({"status": "ok", "role": "customer", "username": user.get("username")})
    # Return HTML for browser (redirect to main for customers)
    return RedirectResponse(url=react_redirect("/main"), status_code=status.HTTP_302_FOUND)


@app.get("/admin/users", response_class=HTMLResponse)
def admin_users_page(request: Request, user=Depends(require_normal_admin())):
    return RedirectResponse(url=react_redirect("/admin/users"), status_code=status.HTTP_302_FOUND)


@app.get("/admin/knowledge", response_class=HTMLResponse)
def admin_knowledge_page(request: Request, user=Depends(require_normal_admin())):
    return RedirectResponse(url=react_redirect("/admin/knowledge"), status_code=status.HTTP_302_FOUND)


@app.get("/admin/analytics", response_class=HTMLResponse)
def admin_analytics_page(request: Request, user=Depends(require_normal_admin())):
    return RedirectResponse(url=react_redirect("/admin/analytics"), status_code=status.HTTP_302_FOUND)


@app.get("/admin/audit-logs", response_class=HTMLResponse)
def admin_audit_logs_page(request: Request, user=Depends(require_normal_admin())):
    return RedirectResponse(url=react_redirect("/admin/audit-logs"), status_code=status.HTTP_302_FOUND)


@app.get("/api/users")
def list_users_api(request: Request, user=Depends(require_tenant_staff())):
    """Tenant staff: list users visible to caller's role within their business."""
    conn = get_db()
    c = conn.cursor()
    scope_sql, scope_params = _tenant_scope_sql(user)
    role_sql, role_params = sql_role_filter_for_caller(user.get("role"))
    c.execute(
        f"SELECT id, username, role, active, email, full_name FROM users WHERE 1=1{scope_sql}{role_sql} ORDER BY id",
        scope_params + role_params,
    )
    rows = c.fetchall()
    conn.close()
    users = []
    for row in rows:
        users.append({
            "id": row[0],
            "username": row[1],
            "role": row[2],
            "active": bool(row[3]) if len(row) > 3 else True,
            "email": row[4] if len(row) > 4 else None,
            "full_name": row[5] if len(row) > 5 else None
        })
    return users


@app.get("/api/customers")
def list_customers(request: Request, user=Depends(require_api_role("admin", "master_admin", "employee"))):
    """Tenant-scoped customer accounts (approved memberships for this business)."""
    conn = get_db()
    c = conn.cursor()
    tenant_id = int(user.get("tenant_id") or DEFAULT_TENANT_ID)
    c.execute(
        """
        SELECT u.id, u.username, u.active, u.email, u.full_name, u.created_at, m.status
        FROM tenant_memberships m
        JOIN users u ON u.username = m.username
        WHERE m.tenant_id = ? AND m.status = 'approved' AND u.role = 'customer'
        ORDER BY u.id
        """,
        (tenant_id,),
    )
    rows = c.fetchall()
    conn.close()
    customers = []
    for row in rows:
        customers.append({
            "id": row[0],
            "username": row[1],
            "active": bool(row[2]) if row[2] is not None else True,
            "email": row[3],
            "full_name": row[4],
            "created_at": row[5],
            "membership_status": row[6],
        })
    return customers


@app.post("/api/users/create")
async def create_new_user(request: Request, user=Depends(require_tenant_staff())):
    verify_csrf(request)
    data = await request.json()
    username = data.get("username")
    password = data.get("password")
    role = data.get("role", "customer")
    
    if not username or not password:
        raise HTTPException(status_code=400, detail="Username and password required")
    
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    
    assert_can_assign_role(user.get("role"), role)
    
    tenant_id = int(user.get("tenant_id") or DEFAULT_TENANT_ID)
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("""
            INSERT INTO users (username, password_hash, role, active, tenant_id)
            VALUES (?, ?, ?, 1, ?)
        """, (username, pwd_context.hash(password), role, tenant_id))
        conn.commit()
        conn.close()
        return {"status": "created", "username": username}
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Username already exists")


@app.post("/api/users/{user_id}/deactivate")
async def deactivate_user_api(request: Request, user_id: int, user=Depends(require_tenant_staff())):
    verify_csrf(request)
    target = _assert_target_user_in_caller_tenant(user, user_id)
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE users SET active=0 WHERE id=?", (user_id,))
    c.execute(
        """
        INSERT INTO audit_logs (user_id, username, action, old_value, new_value, ip_address, performed_by)
        VALUES (?, ?, 'ACCOUNT_DEACTIVATED', 'active', 'inactive', ?, ?)
        """,
        (user_id, target["username"], request.client.host, user.get("username")),
    )
    conn.commit()
    conn.close()
    return {"status": "deactivated"}


@app.post("/api/users/{user_id}/activate")
async def activate_user_api(request: Request, user_id: int, user=Depends(require_tenant_staff())):
    verify_csrf(request)
    target = _assert_target_user_in_caller_tenant(user, user_id)
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE users SET active=1 WHERE id=?", (user_id,))
    c.execute(
        """
        INSERT INTO audit_logs (user_id, username, action, old_value, new_value, ip_address, performed_by)
        VALUES (?, ?, 'ACCOUNT_ACTIVATED', 'inactive', 'active', ?, ?)
        """,
        (user_id, target["username"], request.client.host, user.get("username")),
    )
    conn.commit()
    conn.close()
    return {"status": "activated"}


@app.delete("/api/users/{user_id}/delete")
def delete_user_api(request: Request, user_id: int, user=Depends(require_tenant_staff())):
    verify_csrf(request)
    target = _assert_target_user_in_caller_tenant(user, user_id)
    if target["username"] == user.get("username"):
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    conn = get_db()
    c = conn.cursor()
    _purge_user_dependencies(c, user_id, target["username"])
    c.execute("DELETE FROM users WHERE id=?", (user_id,))
    conn.commit()
    conn.close()
    return {"status": "deleted"}


# ========== MASTER ADMIN: NORMAL ADMIN MANAGEMENT ==========

@app.get("/api/tenant-admins")
def list_tenant_admins(request: Request, user=Depends(require_master_admin_or_higher())):
    """Master admin: list normal admins in caller's tenant."""
    conn = get_db()
    c = conn.cursor()
    if user.get("role") == "superadmin":
        tenant_id = int(request.query_params.get("tenant_id") or DEFAULT_TENANT_ID)
    else:
        tenant_id = int(user.get("tenant_id") or DEFAULT_TENANT_ID)
    c.execute(
        """
        SELECT id, username, role, active, email, full_name
        FROM users
        WHERE tenant_id=? AND role='admin'
        ORDER BY username
        """,
        (tenant_id,),
    )
    rows = c.fetchall()
    conn.close()
    return [
        {
            "id": row[0],
            "username": row[1],
            "role": row[2],
            "active": bool(row[3]),
            "email": row[4],
            "full_name": row[5],
        }
        for row in rows
    ]


@app.post("/api/tenant-admins/create")
async def create_tenant_admin(request: Request, user=Depends(require_master_admin_or_higher())):
    """Master admin: create a normal admin in their tenant."""
    verify_csrf(request)
    data = await request.json()
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    full_name = (data.get("full_name") or "").strip() or None
    email = (data.get("email") or "").strip() or None

    if not username or not password:
        raise HTTPException(status_code=400, detail="Username and password required")
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    caller_role = user.get("role")
    assert_can_assign_role(caller_role, "admin")
    tenant_id = int(user.get("tenant_id") or DEFAULT_TENANT_ID)

    conn = get_db()
    c = conn.cursor()
    try:
        c.execute(
            """
            INSERT INTO users (username, password_hash, role, active, tenant_id, full_name, email)
            VALUES (?, ?, 'admin', 1, ?, ?, ?)
            """,
            (username, pwd_context.hash(password), tenant_id, full_name, email),
        )
        conn.commit()
        conn.close()
        return {"status": "created", "username": username}
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(status_code=400, detail="Username already exists")


@app.patch("/api/tenant-admins/{user_id}")
async def update_tenant_admin(request: Request, user_id: int, user=Depends(require_master_admin_or_higher())):
    verify_csrf(request)
    tenant_id = int(user.get("tenant_id") or DEFAULT_TENANT_ID)
    target = _get_tenant_normal_admin(user_id, tenant_id)
    assert_can_manage_user(user, target)
    data = await request.json()

    conn = get_db()
    c = conn.cursor()
    updates = []
    params = []

    if "full_name" in data:
        updates.append("full_name=?")
        params.append((data.get("full_name") or "").strip() or None)
    if "email" in data:
        updates.append("email=?")
        params.append((data.get("email") or "").strip() or None)
    if data.get("password"):
        if len(data["password"]) < 8:
            conn.close()
            raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
        updates.append("password_hash=?")
        params.append(pwd_context.hash(data["password"]))
    if "active" in data:
        updates.append("active=?")
        params.append(1 if data.get("active") else 0)

    if not updates:
        conn.close()
        return {"status": "unchanged"}

    params.append(user_id)
    c.execute(f"UPDATE users SET {', '.join(updates)} WHERE id=?", tuple(params))
    conn.commit()
    conn.close()
    return {"status": "updated", "username": target["username"]}


@app.delete("/api/tenant-admins/{user_id}")
async def delete_tenant_admin(request: Request, user_id: int, user=Depends(require_master_admin_or_higher())):
    verify_csrf(request)
    tenant_id = int(user.get("tenant_id") or DEFAULT_TENANT_ID)
    target = _get_tenant_normal_admin(user_id, tenant_id)
    assert_can_manage_user(user, target)
    if target["username"] == user.get("username"):
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    conn = get_db()
    c = conn.cursor()
    _purge_user_dependencies(c, user_id, target["username"])
    c.execute("DELETE FROM users WHERE id=?", (user_id,))
    conn.commit()
    conn.close()
    return {"status": "deleted", "username": target["username"]}


# ========== SUPERADMIN: TENANT & DOMAIN-MANAGER MANAGEMENT ==========
# These JSON APIs are restricted to the platform owner (superadmin). They let
# the owner provision tenants and seed each tenant's first domain manager
# (an 'admin' user bound to that tenant_id). They mirror the style of the
# /api/users/... endpoints above (CSRF on mutating POSTs, sqlite3 error
# handling, JSON request bodies).

_MEMBERSHIP_STATUSES = ("pending", "approved", "rejected", "revoked")
_ROLE_COUNT_ROLES = ("master_admin", "admin", "employee", "customer")


def _empty_membership_stats() -> dict[str, int]:
    return {status: 0 for status in _MEMBERSHIP_STATUSES}


def _empty_role_counts() -> dict[str, int]:
    return {role: 0 for role in _ROLE_COUNT_ROLES}


def build_tenant_details(conn, tenant_ids: list[int]) -> dict[int, dict]:
    """Assemble per-tenant rosters and membership stats for superadmin listing."""
    if not tenant_ids:
        return {}

    details = {
        tid: {
            "role_counts": _empty_role_counts(),
            "master_admins": [],
            "admins": [],
            "employees": [],
            "membership_customers": [],
            "membership_stats": _empty_membership_stats(),
        }
        for tid in tenant_ids
    }

    c = conn.cursor()
    placeholders = ",".join("?" * len(tenant_ids))

    c.execute(
        f"""
        SELECT tenant_id, role, COUNT(*)
        FROM users
        WHERE tenant_id IN ({placeholders})
          AND role IN ('master_admin', 'admin', 'employee', 'customer')
        GROUP BY tenant_id, role
        """,
        tenant_ids,
    )
    for tenant_id, role, count in c.fetchall():
        bucket = details.get(tenant_id)
        if bucket and role in bucket["role_counts"]:
            bucket["role_counts"][role] = count

    c.execute(
        f"""
        SELECT id, username, email, full_name, active, tenant_id, role
        FROM users
        WHERE tenant_id IN ({placeholders})
          AND role IN ('master_admin', 'admin', 'employee')
        ORDER BY tenant_id, role, username
        """,
        tenant_ids,
    )
    for row in c.fetchall():
        tenant_id = row[5]
        bucket = details.get(tenant_id)
        if not bucket:
            continue
        user = {
            "id": row[0],
            "username": row[1],
            "email": row[2],
            "full_name": row[3],
            "active": bool(row[4]) if row[4] is not None else True,
        }
        if row[6] == "master_admin":
            bucket["master_admins"].append(user)
        elif row[6] == "admin":
            bucket["admins"].append(user)
        else:
            bucket["employees"].append(user)

    c.execute(
        f"""
        SELECT tenant_id, status, COUNT(*)
        FROM tenant_memberships
        WHERE tenant_id IN ({placeholders})
        GROUP BY tenant_id, status
        """,
        tenant_ids,
    )
    for tenant_id, status, count in c.fetchall():
        bucket = details.get(tenant_id)
        if bucket and status in bucket["membership_stats"]:
            bucket["membership_stats"][status] = count

    c.execute(
        f"""
        SELECT u.id, u.username, u.email, u.full_name, u.active, m.tenant_id, m.reviewed_at
        FROM tenant_memberships m
        JOIN users u ON u.username = m.username
        WHERE m.tenant_id IN ({placeholders})
          AND m.status = 'approved'
          AND u.role = 'customer'
        ORDER BY m.tenant_id, u.username
        """,
        tenant_ids,
    )
    for row in c.fetchall():
        tenant_id = row[5]
        bucket = details.get(tenant_id)
        if not bucket:
            continue
        bucket["membership_customers"].append({
            "id": row[0],
            "username": row[1],
            "email": row[2],
            "full_name": row[3],
            "active": bool(row[4]) if row[4] is not None else True,
            "approved_at": row[6],
        })

    return details


@app.get("/api/tenants")
def list_tenants(request: Request, user=Depends(require_api_role("superadmin"))):
    """Superadmin: list all tenants with rosters and membership stats."""
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT id, name, slug, active, plan, created_at,
               COALESCE(allow_multiple_admins, 0) AS allow_multiple_admins
        FROM tenants
        ORDER BY id
    """)
    rows = c.fetchall()
    tenant_ids = [row[0] for row in rows]

    user_counts: dict[int, int] = {}
    if tenant_ids:
        placeholders = ",".join("?" * len(tenant_ids))
        c.execute(
            f"SELECT tenant_id, COUNT(*) FROM users WHERE tenant_id IN ({placeholders}) GROUP BY tenant_id",
            tenant_ids,
        )
        for tenant_id, count in c.fetchall():
            user_counts[tenant_id] = count

    extra_by_tenant = build_tenant_details(conn, tenant_ids)
    conn.close()

    tenants = []
    for row in rows:
        tenant_id = row[0]
        extra = extra_by_tenant.get(tenant_id, {
            "role_counts": _empty_role_counts(),
            "admins": [],
            "employees": [],
            "membership_customers": [],
            "membership_stats": _empty_membership_stats(),
        })
        tenants.append({
            "id": tenant_id,
            "name": row[1],
            "slug": row[2],
            "active": bool(row[3]) if row[3] is not None else True,
            "plan": row[4],
            "created_at": row[5],
            "allow_multiple_admins": bool(row[6]) if len(row) > 6 else False,
            "admin_count": int((extra.get("role_counts") or {}).get("admin", 0)),
            "user_count": user_counts.get(tenant_id, 0),
            **extra,
        })
    return tenants


@app.post("/api/tenants/create")
async def create_tenant_api(request: Request, user=Depends(require_api_role("superadmin"))):
    """Superadmin: create a new tenant. Body: {name, slug, plan?}."""
    verify_csrf(request)
    data = await request.json()
    name = (data.get("name") or "").strip()
    slug = (data.get("slug") or "").strip().lower()
    plan = (data.get("plan") or "standard").strip() or "standard"

    if not name:
        raise HTTPException(status_code=400, detail="Tenant name required")
    if not slug:
        raise HTTPException(status_code=400, detail="Tenant slug required")
    if not re.match(r"^[a-z0-9-]+$", slug):
        raise HTTPException(
            status_code=400,
            detail="Slug must contain only lowercase letters, numbers, and hyphens",
        )

    try:
        conn = get_db()
        c = conn.cursor()
        c.execute(
            "INSERT INTO tenants (name, slug, active, plan) VALUES (?, ?, 1, ?)",
            (name, slug, plan),
        )
        tenant_id = c.lastrowid
        conn.commit()
        conn.close()
        return {"status": "created", "id": tenant_id, "slug": slug}
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="slug already exists")


@app.post("/api/tenants/{tenant_id}/managers")
async def create_tenant_manager_api(request: Request, tenant_id: int, user=Depends(require_api_role("superadmin"))):
    """Superadmin: create a domain manager ('admin') bound to a tenant.

    Body: {username, password, full_name?, email?}.
    """
    verify_csrf(request)
    data = await request.json()
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    full_name = (data.get("full_name") or "").strip() or None
    email = (data.get("email") or "").strip() or None

    if not username or not password:
        raise HTTPException(status_code=400, detail="Username and password required")
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    if email and not validate_email(email):
        raise HTTPException(status_code=400, detail="Invalid email format")

    # The target tenant must exist before we bind a manager to it.
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id FROM tenants WHERE id=?", (tenant_id,))
    if not c.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Tenant not found")

    if email:
        c.execute("SELECT id FROM users WHERE email=? AND email IS NOT NULL", (email,))
        if c.fetchone():
            conn.close()
            raise HTTPException(status_code=400, detail="Email already registered")

    try:
        c.execute(
            "SELECT COUNT(*) FROM users WHERE tenant_id=? AND role='master_admin' AND active=1",
            (tenant_id,),
        )
        if (c.fetchone() or [0])[0] >= 1:
            conn.close()
            raise HTTPException(
                status_code=403,
                detail="This tenant already has a master admin. Delete or deactivate the existing one first.",
            )

        c.execute("""
            INSERT INTO users (username, password_hash, role, active, tenant_id, auth_provider, full_name, email)
            VALUES (?, ?, 'master_admin', 1, ?, 'local', ?, ?)
        """, (username, pwd_context.hash(password), tenant_id, full_name, email))
        conn.commit()
        conn.close()
        return {"status": "created", "username": username, "tenant_id": tenant_id}
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(status_code=400, detail="Username already exists")


def _get_tenant_master_admin(user_id: int, tenant_id: int) -> dict:
    """Load a tenant-bound master_admin user or raise 404."""
    conn = get_db()
    c = conn.cursor()
    c.execute(
        """
        SELECT id, username, role, tenant_id, full_name, email, active
        FROM users
        WHERE id=? AND tenant_id=? AND role='master_admin'
        """,
        (int(user_id), int(tenant_id)),
    )
    row = c.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Master admin not found for this business")
    return {
        "id": row[0],
        "username": row[1],
        "role": row[2],
        "tenant_id": row[3],
        "full_name": row[4],
        "email": row[5],
        "active": bool(row[6]) if row[6] is not None else True,
    }


def _get_tenant_normal_admin(user_id: int, tenant_id: int) -> dict:
    """Load a tenant-bound normal admin user or raise 404."""
    conn = get_db()
    c = conn.cursor()
    c.execute(
        """
        SELECT id, username, role, tenant_id, full_name, email, active
        FROM users
        WHERE id=? AND tenant_id=? AND role='admin'
        """,
        (int(user_id), int(tenant_id)),
    )
    row = c.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Admin not found for this business")
    return {
        "id": row[0],
        "username": row[1],
        "role": row[2],
        "tenant_id": row[3],
        "full_name": row[4],
        "email": row[5],
        "active": bool(row[6]) if row[6] is not None else True,
    }


def _get_tenant_admin(user_id: int, tenant_id: int) -> dict:
    """Backward-compatible alias for superadmin manager endpoints (master_admin)."""
    return _get_tenant_master_admin(user_id, tenant_id)


def _purge_user_dependencies(cursor, user_id: int, username: str | None = None) -> None:
    """Remove rows that block deleting a user (support data, memberships)."""
    from Login_system.tenant_lifecycle import purge_user_dependencies

    purge_user_dependencies(cursor, user_id, username)


@app.patch("/api/tenants/{tenant_id}/managers/{user_id}")
async def update_tenant_manager_api(
    request: Request,
    tenant_id: int,
    user_id: int,
    user=Depends(require_api_role("superadmin")),
):
    """Superadmin: update a tenant admin profile (full_name, email, password, active)."""
    verify_csrf(request)
    data = await request.json()

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id FROM tenants WHERE id=?", (tenant_id,))
    if not c.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Tenant not found")

    target = _get_tenant_master_admin(user_id, tenant_id)
    updates = []
    params = []
    audit_logs = []

    if "full_name" in data:
        new_name = (data.get("full_name") or "").strip() or None
        if new_name != target["full_name"]:
            updates.append("full_name=?")
            params.append(new_name)
            audit_logs.append(("FULL_NAME_UPDATE", target["full_name"], new_name))

    if "email" in data:
        new_email = (data.get("email") or "").strip() or None
        if new_email and not validate_email(new_email):
            conn.close()
            raise HTTPException(status_code=400, detail="Invalid email format")
        if new_email:
            c.execute(
                "SELECT id FROM users WHERE email=? AND email IS NOT NULL AND id<>?",
                (new_email, user_id),
            )
            if c.fetchone():
                conn.close()
                raise HTTPException(status_code=400, detail="Email already registered")
        if new_email != target["email"]:
            updates.append("email=?")
            params.append(new_email)
            audit_logs.append(("EMAIL_UPDATE", target["email"], new_email))

    if "password" in data and data.get("password"):
        password = data["password"]
        if len(password) < 8:
            conn.close()
            raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
        updates.append("password_hash=?")
        params.append(pwd_context.hash(password))
        audit_logs.append(("PASSWORD_UPDATE", None, "(redacted)"))

    if "active" in data:
        new_active = 1 if data.get("active") else 0
        if bool(new_active) != target["active"]:
            updates.append("active=?")
            params.append(new_active)
            audit_logs.append(
                ("ACCOUNT_ACTIVE", str(int(target["active"])), str(new_active))
            )

    if not updates:
        conn.close()
        return {"status": "unchanged", "username": target["username"]}

    params.append(user_id)
    c.execute(f"UPDATE users SET {', '.join(updates)} WHERE id=?", tuple(params))

    performer = user.get("username") or "superadmin"
    for action, old_val, new_val in audit_logs:
        c.execute(
            """
            INSERT INTO audit_logs (user_id, username, action, old_value, new_value, ip_address, performed_by)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, target["username"], f"SUPERADMIN_ADMIN_{action}", old_val, new_val, request.client.host, performer),
        )

    conn.commit()
    conn.close()
    return {"status": "updated", "username": target["username"], "tenant_id": tenant_id}


@app.delete("/api/tenants/{tenant_id}/managers/{user_id}")
async def delete_tenant_manager_api(
    request: Request,
    tenant_id: int,
    user_id: int,
    user=Depends(require_api_role("superadmin")),
):
    """Superadmin: permanently delete a tenant admin."""
    verify_csrf(request)
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id FROM tenants WHERE id=?", (tenant_id,))
    if not c.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Tenant not found")

    target = _get_tenant_master_admin(user_id, tenant_id)
    try:
        _purge_user_dependencies(c, user_id, target["username"])
        c.execute("DELETE FROM users WHERE id=?", (user_id,))
        c.execute(
            """
            INSERT INTO audit_logs (user_id, username, action, old_value, new_value, ip_address, performed_by)
            VALUES (?, ?, 'SUPERADMIN_ADMIN_DELETE', ?, 'deleted', ?, ?)
            """,
            (user_id, target["username"], target["username"], request.client.host, user.get("username") or "superadmin"),
        )
        conn.commit()
    except sqlite3.IntegrityError as exc:
        conn.rollback()
        conn.close()
        raise HTTPException(
            status_code=409,
            detail="Cannot delete admin: related records still reference this account",
        ) from exc
    conn.close()
    return {"status": "deleted", "username": target["username"], "tenant_id": tenant_id}


@app.post("/api/tenants/{tenant_id}/deactivate")
async def deactivate_tenant_api(request: Request, tenant_id: int, user=Depends(require_api_role("superadmin"))):
    """Superadmin: deactivate a tenant (sets tenants.active = 0)."""
    verify_csrf(request)
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id FROM tenants WHERE id=?", (tenant_id,))
    if not c.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Tenant not found")
    c.execute("UPDATE tenants SET active=0 WHERE id=?", (tenant_id,))
    conn.commit()
    conn.close()
    return {"status": "deactivated", "tenant_id": tenant_id}


@app.post("/api/tenants/{tenant_id}/activate")
async def activate_tenant_api(request: Request, tenant_id: int, user=Depends(require_api_role("superadmin"))):
    """Superadmin: activate a tenant (sets tenants.active = 1)."""
    verify_csrf(request)
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id FROM tenants WHERE id=?", (tenant_id,))
    if not c.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Tenant not found")
    c.execute("UPDATE tenants SET active=1 WHERE id=?", (tenant_id,))
    conn.commit()
    conn.close()
    return {"status": "activated", "tenant_id": tenant_id}


@app.delete("/api/tenants/{tenant_id}")
async def delete_tenant_api(
    request: Request,
    tenant_id: int,
    user=Depends(require_api_role("superadmin")),
):
    """Superadmin: permanently delete an inactive tenant and all scoped data."""
    verify_csrf(request)
    if int(tenant_id) == int(DEFAULT_TENANT_ID):
        raise HTTPException(status_code=403, detail="Cannot delete the default business")

    try:
        data = await request.json()
    except Exception:
        data = {}
    confirm_slug = (data.get("confirm_slug") or "").strip().lower()

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id, slug, active FROM tenants WHERE id=?", (int(tenant_id),))
    row = c.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Tenant not found")
    if int(row[2] or 0) == 1:
        conn.close()
        raise HTTPException(
            status_code=409,
            detail="Business must be deactivated before it can be deleted",
        )
    expected_slug = str(row[1] or "").strip().lower()
    if not confirm_slug or confirm_slug != expected_slug:
        conn.close()
        raise HTTPException(status_code=400, detail="Confirmation slug does not match")

    from Login_system.tenant_lifecycle import delete_tenant_permanently

    try:
        result = delete_tenant_permanently(
            conn,
            int(tenant_id),
            performed_by=user.get("username") or "superadmin",
            ip_address=request.client.host if request.client else None,
        )
    except PermissionError:
        conn.close()
        raise HTTPException(status_code=403, detail="Cannot delete the default business")
    except ValueError:
        conn.close()
        raise HTTPException(status_code=404, detail="Tenant not found")
    except RuntimeError:
        conn.close()
        raise HTTPException(
            status_code=409,
            detail="Business must be deactivated before it can be deleted",
        )
    except sqlite3.IntegrityError as exc:
        conn.rollback()
        conn.close()
        raise HTTPException(
            status_code=409,
            detail="Cannot delete business: related records still reference this tenant",
        ) from exc
    conn.close()
    return result


# ========== TENANT MEMBERSHIPS & CUSTOMER ACCESS WORKFLOW ==========

@app.get("/api/businesses")
def list_businesses(user=Depends(require_api_auth())):
    """List active businesses customers can request access to."""
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "SELECT id, name, slug, plan FROM tenants WHERE active=1 ORDER BY name"
    )
    rows = c.fetchall()
    conn.close()
    return [
        {"id": r[0], "name": r[1], "slug": r[2], "plan": r[3]}
        for r in rows
    ]


@app.get("/api/chat-tenants")
def list_chat_tenants(user=Depends(require_api_auth())):
    """All active tenants available in the chat tenant selector (no membership filter)."""
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id, name, slug FROM tenants WHERE active=1 ORDER BY name")
    rows = c.fetchall()
    conn.close()
    return {"tenants": [{"id": r[0], "name": r[1], "slug": r[2]} for r in rows]}


@app.get("/api/my-memberships")
def my_memberships(user=Depends(require_api_auth("customer"))):
    conn = get_db()
    memberships = list_memberships_for_user(conn, user.get("username"))
    conn.close()
    return {"memberships": memberships}


@app.post("/api/access-requests")
async def submit_access_request(request: Request, user=Depends(require_api_auth("customer"))):
    verify_csrf(request)
    data = await request.json()
    tenant_id = data.get("tenant_id")
    if tenant_id is None:
        raise HTTPException(status_code=400, detail="tenant_id required")
    conn = get_db()
    try:
        membership = create_access_request(conn, user.get("username"), int(tenant_id))
    except ValueError as exc:
        conn.close()
        code = str(exc)
        if code == "tenant_not_found":
            raise HTTPException(status_code=404, detail="Business not found")
        if code == "tenant_inactive":
            raise HTTPException(status_code=400, detail="Business is not active")
        if code == "already_requested":
            raise HTTPException(status_code=400, detail="Request already pending or approved")
        raise HTTPException(status_code=400, detail=code)
    c = conn.cursor()
    c.execute("SELECT name FROM tenants WHERE id=?", (int(tenant_id),))
    tenant_name = (c.fetchone() or [f"Business {tenant_id}"])[0]
    c.execute(
        "SELECT username FROM users WHERE role='admin' AND tenant_id=? AND active=1",
        (int(tenant_id),),
    )
    for (admin_username,) in c.fetchall():
        create_notification(
            admin_username,
            "admin",
            "access_requested",
            "New access request",
            f"{user.get('username')} requested access to {tenant_name}.",
            link="/admin/access-requests",
            priority="normal",
        )
    conn.close()
    return {"status": "pending", "membership": membership}


@app.get("/api/access-requests")
def list_access_requests(
    request: Request,
    user=Depends(require_api_role("admin", "master_admin")),
    status: str = "pending",
):
    tenant_id = int(user.get("tenant_id") or DEFAULT_TENANT_ID)
    conn = get_db()
    memberships = list_memberships_for_tenant(conn, tenant_id, status=status or None)
    conn.close()
    return {"requests": memberships}


@app.post("/api/access-requests/{membership_id}/approve")
async def approve_access_request(
    request: Request,
    membership_id: int,
    user=Depends(require_api_role("admin", "master_admin")),
):
    verify_csrf(request)
    tenant_id = int(user.get("tenant_id") or DEFAULT_TENANT_ID)
    conn = get_db()
    membership = get_membership_by_id(conn, membership_id)
    if not membership or int(membership["tenant_id"]) != tenant_id:
        conn.close()
        raise HTTPException(status_code=404, detail="Access request not found")
    updated = update_membership_status(
        conn, membership_id, "approved", user.get("username")
    )
    conn.close()
    create_notification(
        membership["username"],
        "customer",
        "access_approved",
        "Access approved",
        f"Your access to {membership.get('tenant_name', 'the business')} was approved.",
        link="/select-business",
        priority="normal",
    )
    return {"status": "approved", "membership": updated}


@app.post("/api/access-requests/{membership_id}/reject")
async def reject_access_request(
    request: Request,
    membership_id: int,
    user=Depends(require_api_role("admin", "master_admin")),
):
    verify_csrf(request)
    data = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    notes = (data or {}).get("notes")
    tenant_id = int(user.get("tenant_id") or DEFAULT_TENANT_ID)
    conn = get_db()
    membership = get_membership_by_id(conn, membership_id)
    if not membership or int(membership["tenant_id"]) != tenant_id:
        conn.close()
        raise HTTPException(status_code=404, detail="Access request not found")
    updated = update_membership_status(
        conn, membership_id, "rejected", user.get("username"), notes=notes
    )
    conn.close()
    create_notification(
        membership["username"],
        "customer",
        "access_rejected",
        "Access request declined",
        f"Your access request to {membership.get('tenant_name', 'the business')} was declined.",
        link="/select-business",
        priority="normal",
    )
    return {"status": "rejected", "membership": updated}


@app.post("/api/memberships/{membership_id}/revoke")
async def revoke_membership(
    request: Request,
    membership_id: int,
    user=Depends(require_api_role("admin", "master_admin")),
):
    verify_csrf(request)
    tenant_id = int(user.get("tenant_id") or DEFAULT_TENANT_ID)
    conn = get_db()
    membership = get_membership_by_id(conn, membership_id)
    if not membership or int(membership["tenant_id"]) != tenant_id:
        conn.close()
        raise HTTPException(status_code=404, detail="Membership not found")
    updated = update_membership_status(
        conn, membership_id, "revoked", user.get("username")
    )
    conn.close()
    create_notification(
        membership["username"],
        "customer",
        "access_revoked",
        "Access revoked",
        f"Your access to {membership.get('tenant_name', 'the business')} was revoked.",
        link="/select-business",
        priority="high",
    )
    return {"status": "revoked", "membership": updated}


@app.post("/api/session/active-tenant")
async def set_active_tenant(request: Request, user=Depends(require_api_auth("customer"))):
    verify_csrf(request)
    data = await request.json()
    tenant_id = data.get("tenant_id")
    if tenant_id is None:
        raise HTTPException(status_code=400, detail="tenant_id required")
    conn = get_db()
    membership = get_membership(conn, user.get("username"), int(tenant_id))
    if not membership or membership["status"] != "approved" or not membership.get("tenant_active", True):
        conn.close()
        raise HTTPException(status_code=403, detail="No approved access to this business")
    conn.close()
    token = create_session_token(
        user.get("username"),
        user.get("role"),
        auth_provider=user.get("auth_provider", "local"),
        active_tenant_id=int(tenant_id),
        tenant_id=int(tenant_id),
    )
    response = JSONResponse({"status": "ok", "active_tenant_id": int(tenant_id)})
    response.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        secure=ENFORCE_HTTPS,
        samesite="strict",
        max_age=86400,
    )
    return response


@app.get("/select-business", response_class=HTMLResponse)
def select_business_page(request: Request, user=Depends(require_login("customer"))):
    return RedirectResponse(url=react_redirect("/select-business"), status_code=status.HTTP_302_FOUND)


@app.get("/superadmin", response_class=HTMLResponse)
def superadmin_page(request: Request, user=Depends(require_login("superadmin"))):
    return RedirectResponse(url=react_redirect("/superadmin"), status_code=status.HTTP_302_FOUND)


@app.get("/admin/access-requests", response_class=HTMLResponse)
def admin_access_requests_page(request: Request, user=Depends(require_normal_admin())):
    return RedirectResponse(url=react_redirect("/admin/access-requests"), status_code=status.HTTP_302_FOUND)


@app.post("/api/tenants/{tenant_id}/settings")
async def update_tenant_settings_api(
    request: Request,
    tenant_id: int,
    user=Depends(require_api_role("superadmin")),
):
    verify_csrf(request)
    data = await request.json()
    allow_multiple = 1 if data.get("allow_multiple_admins") else 0
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "UPDATE tenants SET allow_multiple_admins=? WHERE id=?",
        (allow_multiple, int(tenant_id)),
    )
    conn.commit()
    conn.close()
    return {"status": "updated", "allow_multiple_admins": bool(allow_multiple)}


# Employee-specific customer activation/deactivation
@app.post("/api/customers/{customer_id}/deactivate")
async def deactivate_customer_api(request: Request, customer_id: int, user=Depends(require_role("admin", "master_admin", "employee"))):
    """Employee: Deactivate customer account only"""
    verify_csrf(request)
    conn = get_db()
    c = conn.cursor()
    
    # Verify it's a customer
    c.execute("SELECT username, role FROM users WHERE id=?", (customer_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Customer not found")
    
    username, role = row
    
    # Employees can only deactivate customers
    if user.get("role") == "employee" and role != "customer":
        conn.close()
        raise HTTPException(status_code=403, detail="Employees can only deactivate customer accounts")
    
    c.execute("UPDATE users SET active=0 WHERE id=?", (customer_id,))
    
    # Audit log
    c.execute("""
        INSERT INTO audit_logs (user_id, username, action, old_value, new_value, ip_address, performed_by)
        VALUES (?, ?, 'CUSTOMER_DEACTIVATED', 'active', 'inactive', ?, ?)
    """, (customer_id, username, request.client.host, user.get("username")))
    
    conn.commit()
    conn.close()
    return {"status": "deactivated", "username": username}


@app.post("/api/customers/{customer_id}/activate")
async def activate_customer_api(request: Request, customer_id: int, user=Depends(require_role("admin", "master_admin", "employee"))):
    """Employee: Activate customer account only"""
    verify_csrf(request)
    conn = get_db()
    c = conn.cursor()
    
    # Verify it's a customer
    c.execute("SELECT username, role FROM users WHERE id=?", (customer_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Customer not found")
    
    username, role = row
    
    # Employees can only activate customers
    if user.get("role") == "employee" and role != "customer":
        conn.close()
        raise HTTPException(status_code=403, detail="Employees can only activate customer accounts")
    
    c.execute("UPDATE users SET active=1 WHERE id=?", (customer_id,))
    
    # Audit log
    c.execute("""
        INSERT INTO audit_logs (user_id, username, action, old_value, new_value, ip_address, performed_by)
        VALUES (?, ?, 'CUSTOMER_ACTIVATED', 'inactive', 'active', ?, ?)
    """, (customer_id, username, request.client.host, user.get("username")))
    
    conn.commit()
    conn.close()
    return {"status": "activated", "username": username}


# ========== ADMIN: ROLE MANAGEMENT ==========

@app.post("/api/users/{user_id}/change-role")
async def change_user_role(request: Request, user_id: int, user=Depends(require_tenant_staff())):
    """Change user role within hierarchy permissions."""
    verify_csrf(request)
    data = await request.json()
    new_role = data.get("role")
    assert_can_assign_role(user.get("role"), new_role)

    target = _assert_target_user_in_caller_tenant(user, user_id)
    username = target["username"]
    old_role = target["role"]

    conn = get_db()
    c = conn.cursor()
    
    # Prevent changing your own role
    if username == user.get("username"):
        conn.close()
        raise HTTPException(status_code=400, detail="Cannot change your own role")
    
    # Update role
    c.execute("UPDATE users SET role=? WHERE id=?", (new_role, user_id))
    
    # Audit log
    c.execute("""
        INSERT INTO audit_logs (user_id, username, action, old_value, new_value, ip_address, performed_by)
        VALUES (?, ?, 'ROLE_CHANGE', ?, ?, ?, ?)
    """, (user_id, username, old_role, new_role, request.client.host, user.get("username")))
    
    conn.commit()
    conn.close()
    
    # SECURITY: Role change requires session invalidation
    # The user will need to log in again to get the new role in their session
    # Note: In a production system with Redis/database sessions, you would:
    # 1. Delete the user's active session from session store
    # 2. Force re-login on their next request
    # For now, we log this security recommendation
    import logging
    logging.getLogger("Security").warning(
        f"Role changed for user {username} ({old_role} -> {new_role}). "
        f"User should be forced to re-login for session security."
    )
    
    return {"status": "role_changed", "username": username, "new_role": new_role}


@app.post("/api/users/{user_id}/update-profile")
async def update_user_profile(request: Request, user_id: int, user=Depends(require_role("admin", "master_admin", "employee"))):
    """Admin/Employee: Update customer profile (name, email, etc.)"""
    verify_csrf(request)
    data = await request.json()
    
    conn = get_db()
    c = conn.cursor()
    
    # Get user info
    c.execute("SELECT username, role, email, full_name FROM users WHERE id=?", (user_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="User not found")
    
    username, role, old_email, old_name = row
    
    # Employee can only edit customers
    if user.get("role") == "employee" and role != "customer":
        conn.close()
        raise HTTPException(status_code=403, detail="Employees can only edit customer accounts")
    
    # Update fields
    updates = []
    params = []
    audit_logs = []
    
    if "email" in data and data["email"] != old_email:
        updates.append("email=?")
        params.append(data["email"])
        audit_logs.append(("EMAIL_UPDATE", old_email, data["email"]))
    
    if "full_name" in data and data["full_name"] != old_name:
        updates.append("full_name=?")
        params.append(data["full_name"])
        audit_logs.append(("NAME_UPDATE", old_name, data["full_name"]))
    
    if updates:
        params.append(user_id)
        c.execute(f"UPDATE users SET {', '.join(updates)} WHERE id=?", tuple(params))
        
        # Add audit logs
        for action, old_val, new_val in audit_logs:
            c.execute("""
                INSERT INTO audit_logs (user_id, username, action, old_value, new_value, ip_address, performed_by)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (user_id, username, action, old_val, new_val, request.client.host, user.get("username")))
    
    conn.commit()
    conn.close()
    
    return {"status": "updated", "username": username}


# ========== EMPLOYEE: PASSWORD RESET TRIGGER ==========

@app.post("/api/customers/{customer_id}/trigger-password-reset")
async def trigger_customer_password_reset(request: Request, customer_id: int, user=Depends(require_role("admin", "master_admin", "employee"))):
    """Employee: Trigger password reset for customer (sends OTP to customer's email)"""
    verify_csrf(request)
    
    conn = get_db()
    c = conn.cursor()
    
    # Get customer info
    c.execute("SELECT username, email, role, full_name FROM users WHERE id=?", (customer_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Customer not found")
    
    username, email, role, full_name = row
    
    # Employees can only reset customer passwords
    if user.get("role") == "employee" and role != "customer":
        conn.close()
        raise HTTPException(status_code=403, detail="Employees can only reset customer passwords")
    
    if not email:
        conn.close()
        raise HTTPException(status_code=400, detail="Customer has no email address")
    
    # Generate OTP
    otp_code = ''.join(random.choices(string.digits, k=6))
    expires_at = datetime.now() + timedelta(minutes=10)
    
    # Store OTP (hashed)
    otp_hash = hash_otp(otp_code)
    c.execute("""
        INSERT INTO otp_verification (email, otp_code, expires_at, verified, purpose)
        VALUES (?, ?, ?, 0, 'password_reset')
    """, (email, otp_hash, expires_at.isoformat()))
    
    # Audit log
    c.execute("""
        INSERT INTO audit_logs (user_id, username, action, old_value, new_value, ip_address, performed_by)
        VALUES (?, ?, 'PASSWORD_RESET_TRIGGERED', ?, ?, ?, ?)
    """, (customer_id, username, '', email, request.client.host, user.get("username")))
    
    conn.commit()
    conn.close()
    
    # Send OTP email
    send_otp_email(email, full_name or username, otp_code)
    
    return {"status": "sent", "email": email, "message": "Password reset email sent to customer"}


# ========== EMPLOYEE: CUSTOMER NOTES ==========

@app.get("/api/customers/{customer_id}/notes")
def get_customer_notes(request: Request, customer_id: int, user=Depends(require_role("admin", "master_admin", "employee"))):
    """Get support notes for a customer"""
    conn = get_db()
    c = conn.cursor()
    
    # Verify customer exists and is actually a customer
    c.execute("SELECT role FROM users WHERE id=?", (customer_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Customer not found")
    
    if user.get("role") == "employee" and row[0] != "customer":
        conn.close()
        raise HTTPException(status_code=403, detail="Employees can only view customer notes")
    
    # Get notes
    c.execute("""
        SELECT id, note, created_by, created_at
        FROM customer_notes
        WHERE customer_id=?
        ORDER BY created_at DESC
    """, (customer_id,))
    rows = c.fetchall()
    conn.close()
    
    notes = []
    for row in rows:
        notes.append({
            "id": row[0],
            "note": row[1],
            "created_by": row[2],
            "created_at": row[3]
        })
    
    return notes


@app.post("/api/customers/{customer_id}/notes")
async def add_customer_note(request: Request, customer_id: int, user=Depends(require_role("admin", "master_admin", "employee"))):
    """Add a support note to a customer account"""
    verify_csrf(request)
    data = await request.json()
    note = data.get("note", "").strip()
    
    if not note:
        raise HTTPException(status_code=400, detail="Note cannot be empty")
    
    conn = get_db()
    c = conn.cursor()
    
    # Verify customer exists
    c.execute("SELECT username, role FROM users WHERE id=?", (customer_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Customer not found")
    
    username, role = row
    
    # Employees can only add notes to customers
    if user.get("role") == "employee" and role != "customer":
        conn.close()
        raise HTTPException(status_code=403, detail="Employees can only add notes to customer accounts")
    
    # Insert note
    c.execute("""
        INSERT INTO customer_notes (customer_id, customer_username, note, created_by)
        VALUES (?, ?, ?, ?)
    """, (customer_id, username, note, user.get("username")))
    
    conn.commit()
    note_id = c.lastrowid
    conn.close()
    
    return {"status": "created", "note_id": note_id}


@app.delete("/api/customers/{customer_id}/notes/{note_id}")
async def delete_customer_note(request: Request, customer_id: int, note_id: int, user=Depends(require_role("admin", "master_admin", "employee"))):
    """Delete a customer note"""
    verify_csrf(request)
    
    conn = get_db()
    c = conn.cursor()
    
    # Verify note exists and belongs to this customer
    c.execute("SELECT created_by FROM customer_notes WHERE id=? AND customer_id=?", (note_id, customer_id))
    row = c.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Note not found")
    
    created_by = row[0]
    
    # Only creator or admin can delete
    if user.get("role") != "admin" and created_by != user.get("username"):
        conn.close()
        raise HTTPException(status_code=403, detail="Can only delete your own notes")
    
    c.execute("DELETE FROM customer_notes WHERE id=?", (note_id,))
    conn.commit()
    conn.close()
    
    return {"status": "deleted"}


# ========== EMPLOYEE: CUSTOMER ANALYTICS ==========

@app.get("/api/employee/analytics")
def employee_analytics(request: Request, user=Depends(require_role("admin", "master_admin", "employee"))):
    """Employee: Get customer-focused analytics scoped to the caller's tenant."""
    conn = get_db()
    c = conn.cursor()
    scope_sql, scope_params = _tenant_scope_sql(user)

    c.execute(
        f"SELECT COUNT(*) FROM users WHERE role='customer'{scope_sql}",
        scope_params,
    )
    total_customers = c.fetchone()[0]

    c.execute(
        f"SELECT COUNT(*) FROM users WHERE role='customer' AND active=1{scope_sql}",
        scope_params,
    )
    active_customers = c.fetchone()[0]

    thirty_days_ago = (datetime.now() - timedelta(days=30)).isoformat()
    c.execute(
        f"SELECT COUNT(*) FROM users WHERE role='customer' AND created_at > ?{scope_sql}",
        [thirty_days_ago, *scope_params],
    )
    recent_registrations = c.fetchone()[0]

    if scope_sql:
        c.execute(
            """
            SELECT COUNT(*) FROM customer_notes cn
            INNER JOIN users u ON cn.customer_username = u.username
            WHERE u.role='customer' AND u.tenant_id = ?
            """,
            scope_params,
        )
    else:
        c.execute("SELECT COUNT(*) FROM customer_notes")
    total_notes = c.fetchone()[0]

    conn.close()

    return {
        "total_customers": total_customers,
        "active_customers": active_customers,
        "inactive_customers": total_customers - active_customers,
        "recent_registrations_30d": recent_registrations,
        "total_support_notes": total_notes
    }


def _analytics_tenant_id(user) -> int | None:
    role = str((user or {}).get("role") or "").lower()
    if role == "superadmin":
        return None
    return int((user or {}).get("tenant_id") or DEFAULT_TENANT_ID)


@app.get("/api/analytics/comprehensive")
def api_analytics_comprehensive(
    request: Request,
    user=Depends(require_api_role("admin", "master_admin", "employee")),
    days: int = 30,
):
    """Tenant-scoped RAG analytics for React admin dashboards."""
    from backend.analytics import get_comprehensive_analytics

    return get_comprehensive_analytics(days, tenant_id=_analytics_tenant_id(user))


@app.get("/api/analytics/errors")
def api_analytics_errors(
    request: Request,
    user=Depends(require_api_role("admin", "master_admin", "employee")),
    limit: int = 50,
):
    """Recent analytics errors for React admin dashboards."""
    from backend.analytics import get_recent_errors

    tenant_id = _analytics_tenant_id(user)
    rows = get_recent_errors(limit=limit, tenant_id=tenant_id)
    return {
        "errors": [
            {"timestamp": r[0], "username": r[1], "error": r[2], "response_time": None}
            for r in rows
        ]
    }


# ========== CUSTOMER: SELF-SERVICE FEATURES ==========

@app.get("/api/my-profile")
def get_my_profile(request: Request, user=Depends(require_login())):
    """Get own profile data including active business context."""
    conn = get_db()
    c = conn.cursor()
    role = str(user.get("role") or "").lower()
    profile_tenant_id = user.get("active_tenant_id") if role == "customer" else user.get("tenant_id")
    if profile_tenant_id is None:
        profile_tenant_id = user.get("tenant_id")

    c.execute("""
        SELECT u.username, u.email, u.full_name, u.role, u.created_at, u.active,
               u.tenant_id, t.name, t.slug
        FROM users u
        LEFT JOIN tenants t ON t.id = ?
        WHERE u.username=?
    """, (profile_tenant_id, user.get("username")))
    row = c.fetchone()
    conn.close()
    
    if not row:
        raise HTTPException(status_code=404, detail="User not found")

    tenant_id = profile_tenant_id if profile_tenant_id is not None else row[6]
    tenant_name = row[7]
    tenant_slug = row[8]
    if tenant_id and (tenant_name is None or tenant_slug is None):
        conn2 = get_db()
        c2 = conn2.cursor()
        c2.execute("SELECT name, slug FROM tenants WHERE id=?", (int(tenant_id),))
        trow = c2.fetchone()
        conn2.close()
        if trow:
            tenant_name = tenant_name or trow[0]
            tenant_slug = tenant_slug or trow[1]
    
    return {
        "username": row[0],
        "email": row[1],
        "full_name": row[2],
        "role": row[3],
        "created_at": row[4],
        "active": bool(row[5]),
        "tenant_id": tenant_id,
        "tenant_name": tenant_name,
        "tenant_slug": tenant_slug,
    }


@app.get("/api/session/heartbeat")
def session_heartbeat(request: Request, user=Depends(require_api_auth())):
    """Lightweight keep-alive.

    Resolving ``require_api_auth`` runs ``get_current_user`` -> ``validate_session``,
    which refreshes the session's ``last_activity`` (both in-memory and persisted via
    ``touch_user_session``). This lets the client keep an *actively used* session from
    silently hitting the idle timeout mid-task, while a genuinely idle session still
    expires (no heartbeat is sent when there is no user activity) and returns 401.
    """
    return {"status": "ok", "role": user.get("role")}


@app.delete("/api/my-account")
async def delete_my_account(request: Request, password: str = Form(...), user=Depends(require_login())):
    """Customer: Delete own account (requires password confirmation)"""
    verify_csrf(request)
    
    conn = get_db()
    c = conn.cursor()
    
    # Verify password
    c.execute("SELECT id, password_hash, username, role FROM users WHERE username=?", (user.get("username"),))
    row = c.fetchone()
    
    if not row or not pwd_context.verify(password, row[1]):
        conn.close()
        raise HTTPException(status_code=403, detail="Invalid password")
    
    user_id, _, username, role = row
    
    # Prevent admin from deleting themselves this way
    if role == "admin":
        conn.close()
        raise HTTPException(status_code=403, detail="Admins cannot self-delete via this endpoint")
    
    # Delete user
    c.execute("DELETE FROM users WHERE id=?", (user_id,))
    
    # Audit log
    c.execute("""
        INSERT INTO audit_logs (user_id, username, action, old_value, new_value, ip_address, performed_by)
        VALUES (?, ?, 'ACCOUNT_DELETED', ?, ?, ?, ?)
    """, (user_id, username, role, 'self_deleted', request.client.host, username))
    
    conn.commit()
    conn.close()
    
    # Logout
    response = RedirectResponse(react_redirect("/login"), status_code=302)
    response.delete_cookie(SESSION_COOKIE)
    return response


@app.get("/main", response_class=HTMLResponse)
def main_dashboard(request: Request, user=Depends(require_login())):
    return RedirectResponse(url=react_redirect("/main"), status_code=status.HTTP_302_FOUND)


@app.get("/admin/tickets", response_class=HTMLResponse)
def admin_tickets_page(request: Request, user=Depends(require_normal_admin())):
    return RedirectResponse(url=react_redirect("/admin/tickets"), status_code=status.HTTP_302_FOUND)


@app.get("/employee/tickets", response_class=HTMLResponse)
def employee_tickets_page(request: Request, user=Depends(require_role("admin", "master_admin", "employee"))):
    return RedirectResponse(url=react_redirect("/employee/tickets"), status_code=status.HTTP_302_FOUND)


@app.get("/employee/customers", response_class=HTMLResponse)
def employee_customers_page(request: Request, user=Depends(require_role("admin", "master_admin", "employee"))):
    return RedirectResponse(url=react_redirect("/employee/customers"), status_code=status.HTTP_302_FOUND)


@app.get("/notifications", response_class=HTMLResponse)
def notifications_page(request: Request, user=Depends(require_login())):
    return RedirectResponse(url=react_redirect("/notifications"), status_code=status.HTTP_302_FOUND)


@app.get("/my-tickets", response_class=HTMLResponse)
def my_tickets_page(request: Request, user=Depends(require_login("customer"))):
    return RedirectResponse(url=react_redirect("/my-tickets"), status_code=status.HTTP_302_FOUND)


@app.get("/logout")
def logout(request: Request):
    # Invalidate the session
    session_token = request.cookies.get(SESSION_COOKIE)
    if session_token:
        try:
            session_data = serializer.loads(session_token)
            session_id = session_data.get("session_id")
            if session_id:
                invalidate_session(session_id)
                
            # Log logout
            log_security_event("logout", {
                "username": session_data.get("username"),
                "role": session_data.get("role"),
                "session_id": session_id
            })
        except:
            pass  # Invalid token, just delete cookie
    
    response = RedirectResponse(react_redirect("/login"), status_code=302)
    response.delete_cookie(SESSION_COOKIE)
    response.delete_cookie("csrf_token")
    return response





# ========== CONVERSATION HISTORY PROXIES ==========
@app.get("/conversations")
async def conversations_proxy(request: Request, user=Depends(require_login())):
    """Proxy conversation list requests to the RAG server."""
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.get(
                f"{RAG_HTTP_BASE}/conversations",
                headers=_rag_proxy_headers(request),
            ) as resp:
                return await _rag_json_or_error(resp)
    except HTTPException:
        raise
    except aiohttp.ClientError as e:
        raise HTTPException(status_code=502, detail=f"RAG server unreachable: {str(e)}")


@app.get("/conversations/{conversation_id}")
async def conversation_detail_proxy(conversation_id: str, request: Request, user=Depends(require_login())):
    """Proxy conversation detail requests to the RAG server."""
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.get(
                f"{RAG_HTTP_BASE}/conversations/{conversation_id}",
                headers=_rag_proxy_headers(request),
            ) as resp:
                return await _rag_json_or_error(resp)
    except HTTPException:
        raise
    except aiohttp.ClientError as e:
        raise HTTPException(status_code=502, detail=f"RAG server unreachable: {str(e)}")


@app.post("/conversations")
async def conversation_create_proxy(request: Request, user=Depends(require_login())):
    """Proxy conversation creation to the RAG server."""
    verify_csrf(request)
    body = await request.body()
    headers = _rag_proxy_headers(request)
    if body:
        headers["Content-Type"] = request.headers.get("content-type", "application/json")
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.post(
                f"{RAG_HTTP_BASE}/conversations",
                data=body if body else None,
                headers=headers,
            ) as resp:
                return await _rag_json_or_error(resp)
    except HTTPException:
        raise
    except aiohttp.ClientError as e:
        raise HTTPException(status_code=502, detail=f"RAG server unreachable: {str(e)}")


@app.patch("/conversations/{conversation_id}")
async def conversation_rename_proxy(conversation_id: str, request: Request, user=Depends(require_login())):
    """Proxy conversation rename requests to the RAG server."""
    verify_csrf(request)
    body = await request.body()
    headers = _rag_proxy_headers(request)
    headers["Content-Type"] = request.headers.get("content-type", "application/json")
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.patch(
                f"{RAG_HTTP_BASE}/conversations/{conversation_id}",
                data=body,
                headers=headers,
            ) as resp:
                return await _rag_json_or_error(resp)
    except HTTPException:
        raise
    except aiohttp.ClientError as e:
        raise HTTPException(status_code=502, detail=f"RAG server unreachable: {str(e)}")


@app.delete("/conversations")
async def conversations_clear_all_proxy(request: Request, user=Depends(require_login())):
    """Proxy bulk conversation deletion to the RAG server."""
    verify_csrf(request)
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
            async with session.delete(
                f"{RAG_HTTP_BASE}/conversations",
                headers=_rag_proxy_headers(request),
            ) as resp:
                return await _rag_json_or_error(resp)
    except HTTPException:
        raise
    except aiohttp.ClientError as e:
        raise HTTPException(status_code=502, detail=f"RAG server unreachable: {str(e)}")


@app.delete("/conversations/{conversation_id}")
async def conversation_delete_proxy(conversation_id: str, request: Request, user=Depends(require_login())):
    """Proxy conversation deletion requests to the RAG server."""
    verify_csrf(request)
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.delete(
                f"{RAG_HTTP_BASE}/conversations/{conversation_id}",
                headers=_rag_proxy_headers(request),
            ) as resp:
                return await _rag_json_or_error(resp)
    except HTTPException:
        raise
    except aiohttp.ClientError as e:
        raise HTTPException(status_code=502, detail=f"RAG server unreachable: {str(e)}")


@app.post("/conversations/{conversation_id}/message")
async def conversation_message_proxy(conversation_id: str, request: Request, user=Depends(require_login())):
    """Proxy frontend-only message persistence to the RAG server."""
    verify_csrf(request)
    body = await request.body()
    headers = _rag_proxy_headers(request)
    headers["Content-Type"] = request.headers.get("content-type", "application/json")
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.post(
                f"{RAG_HTTP_BASE}/conversations/{conversation_id}/message",
                data=body,
                headers=headers,
            ) as resp:
                return await _rag_json_or_error(resp)
    except HTTPException:
        raise
    except aiohttp.ClientError as e:
        raise HTTPException(status_code=502, detail=f"RAG server unreachable: {str(e)}")


@app.patch("/conversations/{conversation_id}/active-tenant")
async def conversation_active_tenant_proxy(
    conversation_id: str,
    request: Request,
    user=Depends(require_login()),
):
    """Proxy active tenant updates to the RAG server."""
    verify_csrf(request)
    body = await request.body()
    headers = _rag_proxy_headers(request)
    headers["Content-Type"] = request.headers.get("content-type", "application/json")
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.patch(
                f"{RAG_HTTP_BASE}/conversations/{conversation_id}/active-tenant",
                data=body,
                headers=headers,
            ) as resp:
                return await _rag_json_or_error(resp)
    except HTTPException:
        raise
    except aiohttp.ClientError as e:
        raise HTTPException(status_code=502, detail=f"RAG server unreachable: {str(e)}")


# ========== PUBLIC GUEST CHAT (no login) ==========
@app.get("/api/public/chat-tenants")
def public_chat_tenants():
    """Tenant directory for anonymous customer chat."""
    _require_public_guest_chat()
    from backend.tenant_access import list_active_chat_tenants

    return {"tenants": list_active_chat_tenants()}


@app.get("/api/guest/conversations")
async def guest_conversations_proxy(request: Request):
    _require_public_guest_chat()
    client_ip = request.client.host if request.client else "unknown"
    if not check_rate_limit(f"guest_chat:{client_ip}", 120, 60):
        raise HTTPException(status_code=429, detail="Too many requests.")
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.get(
                f"{RAG_HTTP_BASE}/conversations",
                headers=_guest_rag_proxy_headers(request),
            ) as resp:
                return await _rag_json_or_error(resp)
    except HTTPException:
        raise
    except aiohttp.ClientError as e:
        raise HTTPException(status_code=502, detail=f"RAG server unreachable: {str(e)}")


@app.get("/api/guest/conversations/{conversation_id}")
async def guest_conversation_detail_proxy(conversation_id: str, request: Request):
    _require_public_guest_chat()
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.get(
                f"{RAG_HTTP_BASE}/conversations/{conversation_id}",
                headers=_guest_rag_proxy_headers(request),
            ) as resp:
                return await _rag_json_or_error(resp)
    except HTTPException:
        raise
    except aiohttp.ClientError as e:
        raise HTTPException(status_code=502, detail=f"RAG server unreachable: {str(e)}")


@app.post("/api/guest/conversations")
async def guest_conversation_create_proxy(request: Request):
    _require_public_guest_chat()
    verify_csrf(request)
    body = await request.body()
    headers = _guest_rag_proxy_headers(request)
    if body:
        headers["Content-Type"] = request.headers.get("content-type", "application/json")
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.post(
                f"{RAG_HTTP_BASE}/conversations",
                data=body if body else None,
                headers=headers,
            ) as resp:
                return await _rag_json_or_error(resp)
    except HTTPException:
        raise
    except aiohttp.ClientError as e:
        raise HTTPException(status_code=502, detail=f"RAG server unreachable: {str(e)}")


@app.patch("/api/guest/conversations/{conversation_id}")
async def guest_conversation_rename_proxy(conversation_id: str, request: Request):
    _require_public_guest_chat()
    verify_csrf(request)
    body = await request.body()
    headers = _guest_rag_proxy_headers(request)
    headers["Content-Type"] = request.headers.get("content-type", "application/json")
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.patch(
                f"{RAG_HTTP_BASE}/conversations/{conversation_id}",
                data=body,
                headers=headers,
            ) as resp:
                return await _rag_json_or_error(resp)
    except HTTPException:
        raise
    except aiohttp.ClientError as e:
        raise HTTPException(status_code=502, detail=f"RAG server unreachable: {str(e)}")


@app.patch("/api/guest/conversations/{conversation_id}/active-tenant")
async def guest_conversation_active_tenant_proxy(conversation_id: str, request: Request):
    _require_public_guest_chat()
    verify_csrf(request)
    body = await request.body()
    headers = _guest_rag_proxy_headers(request)
    headers["Content-Type"] = request.headers.get("content-type", "application/json")
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.patch(
                f"{RAG_HTTP_BASE}/conversations/{conversation_id}/active-tenant",
                data=body,
                headers=headers,
            ) as resp:
                return await _rag_json_or_error(resp)
    except HTTPException:
        raise
    except aiohttp.ClientError as e:
        raise HTTPException(status_code=502, detail=f"RAG server unreachable: {str(e)}")


@app.delete("/api/guest/conversations")
async def guest_conversations_delete_all_proxy(request: Request):
    _require_public_guest_chat()
    verify_csrf(request)
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.delete(
                f"{RAG_HTTP_BASE}/conversations",
                headers=_guest_rag_proxy_headers(request),
            ) as resp:
                return await _rag_json_or_error(resp)
    except HTTPException:
        raise
    except aiohttp.ClientError as e:
        raise HTTPException(status_code=502, detail=f"RAG server unreachable: {str(e)}")


@app.delete("/api/guest/conversations/{conversation_id}")
async def guest_conversation_delete_proxy(conversation_id: str, request: Request):
    _require_public_guest_chat()
    verify_csrf(request)
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.delete(
                f"{RAG_HTTP_BASE}/conversations/{conversation_id}",
                headers=_guest_rag_proxy_headers(request),
            ) as resp:
                return await _rag_json_or_error(resp)
    except HTTPException:
        raise
    except aiohttp.ClientError as e:
        raise HTTPException(status_code=502, detail=f"RAG server unreachable: {str(e)}")


@app.post("/api/guest/conversations/{conversation_id}/message")
async def guest_conversation_message_proxy(conversation_id: str, request: Request):
    _require_public_guest_chat()
    verify_csrf(request)
    body = await request.body()
    headers = _guest_rag_proxy_headers(request)
    headers["Content-Type"] = request.headers.get("content-type", "application/json")
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.post(
                f"{RAG_HTTP_BASE}/conversations/{conversation_id}/message",
                data=body,
                headers=headers,
            ) as resp:
                return await _rag_json_or_error(resp)
    except HTTPException:
        raise
    except aiohttp.ClientError as e:
        raise HTTPException(status_code=502, detail=f"RAG server unreachable: {str(e)}")


# ========== ARABIC LANGUAGE SUPPORT PROXIES ==========
@app.get("/arabic/status")
async def arabic_status_proxy(request: Request):
    """Proxy Arabic model status check to the RAG server."""
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        serializer.loads(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid session")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{RAG_HTTP_BASE}/arabic/status",
                timeout=aiohttp.ClientTimeout(total=10),
                headers={"Cookie": request.headers.get("cookie", "")},
            ) as resp:
                data = await resp.json()
                return JSONResponse(content=data, status_code=resp.status)
    except Exception as e:
        return JSONResponse(content={"multilingual_model_ready": False, "error": str(e)}, status_code=200)


@app.post("/arabic/download")
async def arabic_download_proxy(request: Request):
    """Proxy Arabic model download request to the RAG server."""
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        serializer.loads(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid session")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{RAG_HTTP_BASE}/arabic/download",
                timeout=aiohttp.ClientTimeout(total=30),
                headers={"Cookie": request.headers.get("cookie", "")},
            ) as resp:
                data = await resp.json()
                return JSONResponse(content=data, status_code=resp.status)
    except Exception as e:
        return JSONResponse(content={"status": "error", "message": str(e)}, status_code=502)


# ========== TTS PROXY (forward to RAG server XTTS v2) ==========
@app.post("/tts")
async def tts_proxy(request: Request):
    """Proxy TTS requests from the frontend (port 7001) to the RAG server (port 7000)."""
    # Require login
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        serializer.loads(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid session")

    body = await request.body()
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{RAG_HTTP_BASE}/tts",
                data=body,
                headers={"Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=180, sock_connect=10, sock_read=170),
            ) as resp:
                if resp.status != 200:
                    detail = await resp.text()
                    raise HTTPException(status_code=resp.status, detail=detail)
                audio_bytes = await resp.read()
                return Response(
                    content=audio_bytes,
                    media_type=resp.content_type or "audio/wav",
                    headers={"Cache-Control": "no-cache"},
                )
    except (asyncio.TimeoutError, TimeoutError):
        raise HTTPException(status_code=504, detail="TTS request timed out — XTTS model may still be loading. Try again.")
    except aiohttp.ClientError as e:
        raise HTTPException(status_code=502, detail=f"RAG server unreachable: {e}")


@app.post("/proxy/upload_rag")
async def proxy_upload_rag(request: Request, file: UploadFile = File(...), user=Depends(require_tenant_staff())):
    """Proxy uploads to the RAG server, which is the single ingestion owner."""
    verify_csrf(request)

    # Security: File upload validation
    MAX_UPLOAD_SIZE = 20 * 1024 * 1024  # 20MB (increased for large PDFs)
    ALLOWED_EXTENSIONS = {'.txt', '.pdf'}
    
    filename = Path(file.filename).name
    file_ext = '.' + filename.split('.')[-1].lower()
    
    # Check file extension
    if file_ext not in ALLOWED_EXTENSIONS:
        log_security_event("file_upload_rejected", {
            "username": user.get("username"),
            "filename": filename,
            "extension": file_ext,
            "reason": "invalid_extension"
        }, severity="WARNING")
        return {"message": f"Unsupported file type. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"}
    
    # Read file content
    content = await file.read()
    
    # Check file size
    if len(content) > MAX_UPLOAD_SIZE:
        log_security_event("file_upload_rejected", {
            "username": user.get("username"),
            "filename": filename,
            "size_bytes": len(content),
            "reason": "file_too_large"
        }, severity="WARNING")
        raise HTTPException(413, f"File too large (max {MAX_UPLOAD_SIZE // 1024 // 1024}MB)")
    
    file_size_mb = len(content) / (1024 * 1024)
    
    # Log successful upload start
    log_security_event("file_upload_started", {
        "username": user.get("username"),
        "filename": filename,
        "size_bytes": len(content),
        "size_mb": f"{file_size_mb:.1f}",
        "extension": file_ext
    })

    try:
        form = aiohttp.FormData()
        form.add_field(
            "file",
            content,
            filename=filename,
            content_type=file.content_type or "application/octet-stream",
        )
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60)) as session:
            async with session.post(
                f"{RAG_HTTP_BASE}/upload_rag",
                data=form,
                headers=_rag_proxy_headers(request),
            ) as resp:
                data = await _rag_json_or_error(resp)
                log_security_event("file_upload_forwarded", {
                    "username": user.get("username"),
                    "filename": filename,
                    "file_size_mb": f"{file_size_mb:.1f}",
                    "rag_status": data.get("status"),
                    "source_doc_id": data.get("source_doc_id"),
                })
                return data
    except HTTPException:
        raise
    except aiohttp.ClientError as e:
        log_security_event("upload_error", {
            "username": user.get("username"),
            "filename": filename,
            "reason": "rag_proxy_failed",
            "error": str(e)
        }, severity="ERROR")
        raise HTTPException(status_code=502, detail=f"RAG server unreachable: {str(e)}")
    except Exception as e:
        log_security_event("upload_error", {
            "username": user.get("username"),
            "filename": filename,
            "reason": "rag_proxy_failed",
            "error": str(e)
        }, severity="ERROR")
        raise HTTPException(status_code=500, detail=f"Failed to forward uploaded document: {str(e)}")


# ========== TENANT-AWARE KNOWLEDGE ASSET HELPERS ==========
def _assets_root() -> Path:
    """Root assets directory shared by all tenants (each tenant gets a subdir)."""
    return Path(__file__).resolve().parent.parent / 'backend' / 'assets'


def _user_tenant_id(user) -> int:
    """Resolve the caller's tenant id from the session payload (default fallback)."""
    try:
        role = str((user or {}).get("role") or "").lower()
        if role == "customer" and (user or {}).get("active_tenant_id") is not None:
            tid = int(user.get("active_tenant_id"))
            return tid if tid > 0 else DEFAULT_TENANT_ID
        tid = int((user or {}).get("tenant_id"))
        return tid if tid > 0 else DEFAULT_TENANT_ID
    except (TypeError, ValueError):
        return DEFAULT_TENANT_ID


def _tenant_assets_dir(user) -> Path:
    """Per-tenant uploads directory (mirrors config.tenant_assets_dir on the RAG side)."""
    return _assets_root() / f"tenant_{_user_tenant_id(user)}"


def _knowledge_search_dirs(user) -> list:
    """Directories to inspect for a tenant's documents (shared with RAG delete)."""
    tid = _user_tenant_id(user)
    scope_tid = None if tid == DEFAULT_TENANT_ID else tid
    return kb_asset_search_dirs(scope_tid)


def _resolve_tenant_asset_file(user, filename):
    """Locate a stored asset for this tenant. Checks the tenant subdir first,
    then (default tenant only) the legacy root. Returns a resolved Path or None.
    Path-traversal safe: only the basename is used.

    Accepts either the on-disk stored name (with optional UUID prefix) or the
    human display name shown in the admin UI.
    """
    from urllib.parse import unquote

    try:
        from backend.knowledge_base import normalize_uploaded_filename
    except Exception:
        normalize_uploaded_filename = lambda n: (n or "").strip().lower()  # noqa: E731

    raw = str(filename or "").strip()
    if not raw:
        return None
    name = Path(unquote(raw)).name
    if not name:
        return None

    search_dirs = _knowledge_search_dirs(user)
    requested_keys = {
        name.lower(),
        normalize_uploaded_filename(name),
        _display_filename(name).lower(),
        normalize_uploaded_filename(_display_filename(name)),
    }
    requested_keys.discard("")

    def _safe_candidate(base: Path, candidate: Path) -> Path | None:
        try:
            rp = candidate.resolve()
            if not str(rp).startswith(str(base.resolve())):
                return None
            if rp.exists() and rp.is_file():
                return rp
        except Exception:
            return None
        return None

    for base in search_dirs:
        found = _safe_candidate(base, base / name)
        if found is not None:
            return found

    for base in search_dirs:
        if not base.exists():
            continue
        try:
            for file_path in base.iterdir():
                if not file_path.is_file():
                    continue
                stored = file_path.name
                display = _display_filename(stored)
                match_keys = {
                    stored.lower(),
                    display.lower(),
                    normalize_uploaded_filename(stored),
                    normalize_uploaded_filename(display),
                }
                if requested_keys & match_keys:
                    found = _safe_candidate(base, file_path)
                    if found is not None:
                        return found
        except Exception:
            continue
    return None


@app.get("/api/knowledge/files")
def list_knowledge_files(request: Request, user=Depends(require_api_role("admin", "master_admin", "employee"))):
    """List all files in the caller's tenant knowledge base assets directory."""
    chunk_map: dict[str, int] = {}
    try:
        from backend.knowledge_base import list_uploaded_files, normalize_uploaded_filename

        tid = int(user.get("tenant_id") or DEFAULT_TENANT_ID)
        scope = None if tid == DEFAULT_TENANT_ID else tid
        for entry in list_uploaded_files(tenant_id=scope):
            fn = str(entry.get("filename") or "")
            key = normalize_uploaded_filename(fn)
            if key:
                chunk_map[key] = chunk_map.get(key, 0) + int(entry.get("chunks") or 0)
    except Exception as exc:
        logging.getLogger(__name__).warning("KB chunk lookup failed: %s", exc)

    files = []
    seen = set()
    for assets_dir in _knowledge_search_dirs(user):
        if not assets_dir.exists():
            continue
        for file_path in assets_dir.iterdir():
            if not (file_path.is_file() and file_path.suffix.lower() in ['.txt', '.pdf', '.md']):
                continue
            stored_name = file_path.name
            if stored_name in seen:
                continue  # tenant subdir wins over legacy root
            seen.add(stored_name)
            stat = file_path.stat()
            try:
                from backend.knowledge_base import normalize_uploaded_filename

                lookup_keys = {
                    normalize_uploaded_filename(stored_name),
                    normalize_uploaded_filename(_display_filename(stored_name)),
                }
                indexed_chunks = max((chunk_map.get(k, 0) for k in lookup_keys if k), default=0)
            except Exception:
                indexed_chunks = 0
            files.append({
                "filename": stored_name,
                "name": stored_name,
                "stored_name": stored_name,
                "display_name": _display_filename(stored_name),
                "size": stat.st_size,
                "modified": stat.st_mtime,
                "indexed_chunks": indexed_chunks,
                "indexed": indexed_chunks > 0,
            })
    
    return sorted(files, key=lambda x: x['modified'], reverse=True)


@app.get("/api/knowledge/kb_status")
async def proxy_kb_status(request: Request, user=Depends(require_api_role("admin", "master_admin", "employee"))):
    """Proxy the RAG ingestion status for the admin knowledge page."""
    global _last_kb_status_snapshot
    try:
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=KB_STATUS_PROXY_TIMEOUT_S)
        ) as session:
            async with session.get(
                f"{RAG_HTTP_BASE}/kb_status",
                headers=_rag_proxy_headers(request),
            ) as resp:
                data = await _rag_json_or_error(resp)
                if isinstance(data, dict):
                    _last_kb_status_snapshot = dict(data)
                return data
    except HTTPException:
        raise
    except (asyncio.TimeoutError, TimeoutError):
        fallback = dict(_last_kb_status_snapshot) if _last_kb_status_snapshot else {}
        fallback.update({
            "state": fallback.get("state") or "processing",
            "message": "Knowledge base is busy — status temporarily unavailable",
            "proxy_degraded": True,
            "updated_at": time.time(),
        })
        return fallback
    except aiohttp.ClientError as e:
        raise HTTPException(status_code=502, detail=f"RAG server unreachable: {str(e)}")


@app.post("/api/knowledge/reindex-file")
async def proxy_reindex_file(request: Request, filename: str, user=Depends(require_tenant_staff())):
    """Reindex one knowledge-base file via the RAG server."""
    verify_csrf(request)
    if not filename:
        raise HTTPException(status_code=400, detail="filename is required")
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=600)) as session:
            async with session.post(
                f"{RAG_HTTP_BASE}/rag/reindex-file",
                params={"filename": Path(filename).name},
                headers=_rag_proxy_headers(request),
            ) as resp:
                return await _rag_json_or_error(resp)
    except HTTPException:
        raise
    except aiohttp.ClientError as e:
        raise HTTPException(status_code=502, detail=f"RAG server unreachable: {str(e)}")


@app.post("/api/knowledge/reindex-all")
async def proxy_reindex_all(request: Request, user=Depends(require_tenant_staff())):
    """Reindex all knowledge-base files via the RAG server."""
    verify_csrf(request)
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=1800)) as session:
            async with session.post(
                f"{RAG_HTTP_BASE}/rag/reindex-all",
                headers=_rag_proxy_headers(request),
            ) as resp:
                return await _rag_json_or_error(resp)
    except HTTPException:
        raise
    except aiohttp.ClientError as e:
        raise HTTPException(status_code=502, detail=f"RAG server unreachable: {str(e)}")


@app.get("/api/knowledge/files/{filename}")
def get_knowledge_file_content(request: Request, filename: str, user=Depends(require_role("admin", "master_admin", "employee"))):
    """Get the content of a knowledge base file (scoped to the caller's tenant)."""
    file_path = _resolve_tenant_asset_file(user, filename)
    if file_path is None:
        raise HTTPException(status_code=404, detail="File not found")
    
    display_name = _display_filename(filename)

    # Only read text files directly
    if file_path.suffix.lower() == '.txt':
        try:
            content = file_path.read_text(encoding='utf-8')
        except Exception:
            content = file_path.read_text(encoding='utf-8', errors='ignore')
        return {"content": content, "filename": filename, "stored_name": filename, "display_name": display_name}
    elif file_path.suffix.lower() == '.md':
        try:
            content = file_path.read_text(encoding='utf-8')
        except Exception:
            content = file_path.read_text(encoding='utf-8', errors='ignore')
        return {"content": content, "filename": filename, "stored_name": filename, "display_name": display_name}
    elif file_path.suffix.lower() == '.pdf':
        # Try to extract PDF text
        try:
            content = _extract_pdf_text_cached(file_path)
            return {"content": content, "filename": filename, "stored_name": filename, "display_name": display_name}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Cannot extract PDF text: {str(e)}")
    else:
        raise HTTPException(status_code=400, detail="Unsupported file type")


@app.get("/api/knowledge/files/{filename}/download")
def download_knowledge_file(request: Request, filename: str, inline: bool = False, user=Depends(require_role("admin", "master_admin", "employee"))):
    """Download a knowledge base file (scoped to the caller's tenant)."""
    file_path = _resolve_tenant_asset_file(user, filename)
    if file_path is None:
        raise HTTPException(status_code=404, detail="File not found")
    
    suffix = file_path.suffix.lower()
    media_type = 'application/pdf' if suffix == '.pdf' else 'application/octet-stream'
    response = FileResponse(
        path=str(file_path),
        filename=_display_filename(filename),
        media_type=media_type
    )
    if inline and suffix == '.pdf':
        response.headers["Content-Disposition"] = f'inline; filename="{_display_filename(filename)}"'
    return response


@app.get("/api/knowledge/files/{filename}/preview")
def preview_knowledge_pdf(request: Request, filename: str, user=Depends(require_role("admin", "master_admin", "employee"))):
    """Serve PDF as inline content for in-browser preview iframe (tenant-scoped)."""
    file_path = _resolve_tenant_asset_file(user, filename)
    if file_path is None:
        raise HTTPException(status_code=404, detail="File not found")

    if file_path.suffix.lower() != '.pdf':
        raise HTTPException(status_code=400, detail="Preview endpoint only supports PDF files")

    pdf_bytes = file_path.read_bytes()
    response = Response(content=pdf_bytes, media_type='application/pdf')
    response.headers["Content-Disposition"] = f'inline; filename="{_display_filename(filename)}"'
    response.headers["Cache-Control"] = "private, max-age=60"
    return response


@app.get("/api/knowledge/files/{filename}/pdf-data")
def get_knowledge_pdf_data(request: Request, filename: str, user=Depends(require_role("admin", "master_admin", "employee"))):
    """Return PDF bytes as base64 for reliable in-browser rendering (tenant-scoped)."""
    file_path = _resolve_tenant_asset_file(user, filename)
    if file_path is None:
        raise HTTPException(status_code=404, detail="File not found")

    if file_path.suffix.lower() != '.pdf':
        raise HTTPException(status_code=400, detail="PDF data endpoint only supports PDF files")

    pdf_bytes = file_path.read_bytes()
    stored_name = file_path.name
    b64 = base64.b64encode(pdf_bytes).decode("ascii")
    display_name = _display_filename(stored_name)
    return {
        "filename": stored_name,
        "stored_name": stored_name,
        "display_name": display_name,
        "bytes_b64": b64,
        "data": b64,
        "base64": b64,
    }


@app.put("/api/knowledge/files/{filename}")
async def update_knowledge_file(request: Request, filename: str, user=Depends(require_tenant_staff())):
    """Proxy text-file updates to the RAG server, the ingestion owner."""
    verify_csrf(request)

    # Path-traversal safety: only operate on the basename.
    safe_name = Path(str(filename or "")).name
    if not safe_name or safe_name != filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    if Path(safe_name).suffix.lower() != '.txt':
        raise HTTPException(status_code=400, detail="Can only edit text files")
    
    data = await request.json()
    content = data.get("content", "")
    
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60)) as session:
            async with session.put(
                f"{RAG_HTTP_BASE}/rag/files/{safe_name}",
                json={"content": content},
                headers=_rag_proxy_headers(request),
            ) as resp:
                data = await _rag_json_or_error(resp)
                # Evict any cached extracted text for this tenant's copy.
                _resolved = _resolve_tenant_asset_file(user, safe_name)
                if _resolved is not None:
                    _PDF_TEXT_CACHE.pop(str(_resolved), None)
                return data
    except HTTPException:
        raise
    except aiohttp.ClientError as e:
        raise HTTPException(status_code=502, detail=f"RAG server unreachable: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update file: {str(e)}")


@app.delete("/api/knowledge/files/{filename}")
async def delete_knowledge_file(request: Request, filename: str, user=Depends(require_tenant_staff())):
    """Proxy deletion to the RAG server, which owns assets and Chroma cleanup."""
    verify_csrf(request)

    # Path-traversal safety: only operate on the basename.
    safe_name = Path(str(filename or "")).name
    if not safe_name or safe_name != filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    # Resolve the tenant's copy (best-effort) for cache eviction before delete.
    _resolved = _resolve_tenant_asset_file(user, safe_name)

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=45)) as session:
            async with session.post(
                f"{RAG_HTTP_BASE}/rag/delete",
                params={"doc_prefix": safe_name},
                headers=_rag_proxy_headers(request),
            ) as resp:
                data = await _rag_json_or_error(resp)
                if _resolved is not None:
                    _PDF_TEXT_CACHE.pop(str(_resolved), None)
                return data
    except HTTPException:
        raise
    except aiohttp.ClientError as e:
        raise HTTPException(status_code=502, detail=f"RAG server unreachable: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete file: {str(e)}")


@app.post("/api/knowledge/clear-cache")
async def proxy_clear_cache(request: Request, user=Depends(require_tenant_staff())):
    """Proxy clear-cache request to the RAG server to flush all stale data.

    Clears conversation history + Ollama KV cache so the next query
    uses fully fresh KB data.
    """
    verify_csrf(request)
    try:
        import aiohttp as _aiohttp
        async with _aiohttp.ClientSession() as sess:
            async with sess.post(
                f"{RAG_HTTP_BASE}/rag/clear-cache",
                headers=_rag_proxy_headers(request),
                timeout=_aiohttp.ClientTimeout(total=15)
            ) as resp:
                return await _rag_json_or_error(resp)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Cache clear failed: {str(e)}")


_NO_CACHE_HEADERS = {
    "Cache-Control": "no-cache, no-store, must-revalidate",
    "Pragma": "no-cache",
    "Expires": "0",
}


def _safe_file_under_root(root: Path, relative_path: str) -> Path:
    """Resolve a path under the React export root (handles trailing slashes and index.html)."""
    root_resolved = root.resolve()
    cleaned = (relative_path or "").strip().strip("/")
    if not cleaned:
        candidates = [root / "index.html"]
    else:
        candidates = [
            root / cleaned,
            root / cleaned / "index.html",
            root / f"{cleaned}.html",
        ]
    for target in candidates:
        try:
            target_resolved = target.resolve()
        except Exception:
            continue
        if root_resolved not in target_resolved.parents and root_resolved != target_resolved:
            continue
        if target_resolved.is_file():
            return target_resolved
    try:
        fallback = (root / cleaned).resolve() if cleaned else (root / "index.html").resolve()
    except Exception:
        raise HTTPException(status_code=404, detail="Not Found") from None
    if root_resolved not in fallback.parents and root_resolved != fallback:
        raise HTTPException(status_code=404, detail="Not Found")
    return fallback


# --- Phase 4 refactor: /favicon.ico and /internal/check_rag_ws moved to routers ---
# Handlers live in Login_system/routers/system.py and are bound to this live
# module (factory pattern) to avoid an import cycle. Paths/methods/schema
# visibility/responses unchanged.
import sys as _sys_mod
from Login_system.routers.system import build_system_router as _build_system_router
app.include_router(_build_system_router(_sys_mod.modules[__name__]))


@app.get("/frontend")
def serve_react_frontend_root(request: Request):
    """Authenticated entry to the React chat UI."""
    if not get_current_user(request):
        return RedirectResponse(url=react_redirect("/login"), status_code=status.HTTP_307_TEMPORARY_REDIRECT)
    return RedirectResponse(url="/frontend/", status_code=status.HTTP_307_TEMPORARY_REDIRECT)


def _resolve_react_frontend_file(path: str):
    """Resolve a path under the static React export directory."""
    react_dir = REACT_UI_DIR
    if not react_dir.is_dir():
        raise HTTPException(
            status_code=503,
            detail=(
                "React UI build not found. Run: cd assistify-ui-design && npm install && npm run build"
            ),
        )

    target_resolved = _safe_file_under_root(react_dir, path)
    if not target_resolved.is_file():
        index_html = (react_dir / "index.html").resolve()
        if index_html.is_file():
            target_resolved = index_html
        else:
            raise HTTPException(status_code=404, detail="Not Found")
    return target_resolved


@app.head("/frontend")
def head_react_frontend_root(request: Request):
    if not get_current_user(request):
        return Response(status_code=401)
    return Response(status_code=200)


@app.get("/frontend/{path:path}")
def serve_react_frontend(path: str, request: Request):
    """Serve exported React UI; auth pages are public, dashboards and chat require login."""
    if not _react_path_is_public(path):
        if not get_current_user(request):
            return RedirectResponse(url=react_redirect("/login"), status_code=status.HTTP_307_TEMPORARY_REDIRECT)

    target_resolved = _resolve_react_frontend_file(path)
    return FileResponse(str(target_resolved), headers=_NO_CACHE_HEADERS)


@app.head("/frontend/{path:path}")
def head_react_frontend(path: str, request: Request):
    """Allow Next.js link prefetch without 405 log noise."""
    if not _react_path_is_public(path):
        if not get_current_user(request):
            return Response(status_code=401)
    try:
        _resolve_react_frontend_file(path)
    except HTTPException as exc:
        return Response(status_code=exc.status_code)
    return Response(status_code=200)


# ========== FORGOT PASSWORD ROUTES ==========

@app.get("/forgot-password", response_class=HTMLResponse)
async def forgot_password_page(request: Request):
    return RedirectResponse(url=react_redirect("/forgot-password"), status_code=status.HTTP_303_SEE_OTHER)


@app.post("/forgot-password")
async def forgot_password_submit(request: Request, email: str = Form(...)):
    """Handle forgot password request - send OTP to email."""
    # Rate limiting - 3 attempts per minute per IP
    client_ip = request.client.host
    if not check_rate_limit(f"forgot_password:{client_ip}", RATE_LIMIT_OTP, 60):
        return auth_form_redirect(
            "/forgot-password",
            error="Too many requests. Please try again later.",
        )
    
    # Rate limiting check - max 3 requests per email per hour
    conn = get_db()
    c = conn.cursor()
    
    # Check rate limit
    one_hour_ago = datetime.now() - timedelta(hours=1)
    c.execute("""
        SELECT COUNT(*) FROM otp_verification 
        WHERE email = ? AND created_at > ?
    """, (email, one_hour_ago.isoformat()))
    count = c.fetchone()[0]
    
    if count >= 3:
        conn.close()
        return auth_form_redirect(
            "/forgot-password",
            error="Too many requests. Please try again later.",
        )
    
    # Check if email exists
    c.execute("SELECT username FROM users WHERE email = ?", (email,))
    row = c.fetchone()
    
    if not row:
        conn.close()
        return auth_form_redirect(
            "/forgot-password",
            error="No account found with that email address.",
        )
    
    username = row[0]
    
    # Generate OTP
    otp_code = ''.join(random.choices(string.digits, k=6))
    expires_at = datetime.now() + timedelta(minutes=10)
    
    # Store OTP with purpose 'password_reset' (hashed)
    otp_hash = hash_otp(otp_code)
    c.execute("""
        INSERT INTO otp_verification (email, otp_code, expires_at, verified, purpose)
        VALUES (?, ?, ?, 0, 'password_reset')
    """, (email, otp_hash, expires_at.isoformat()))
    conn.commit()
    conn.close()
    
    # Send OTP via email
    send_otp_email(email, username, otp_code)
    
    # Redirect to reset password page with email parameter
    return RedirectResponse(
        url=react_redirect("/reset-password", f"email={email}&message=Check your email for the verification code."),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@app.get("/reset-password", response_class=HTMLResponse)
async def reset_password_page(request: Request, email: str = ""):
    q = f"email={email}" if email else ""
    return RedirectResponse(url=react_redirect("/reset-password", q), status_code=status.HTTP_303_SEE_OTHER)


@app.post("/reset-password")
async def reset_password_submit(
    request: Request,
    email: str = Form(...),
    otp_code: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...)
):
    """Verify OTP and reset password."""
    
    # Check passwords match
    if new_password != confirm_password:
        return auth_form_redirect(
            "/reset-password",
            email=email,
            error="Passwords do not match.",
        )

    # Check password strength
    if len(new_password) < 8:
        return auth_form_redirect(
            "/reset-password",
            email=email,
            error="Password must be at least 8 characters long.",
        )
    
    # Verify OTP
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT id, otp_code, expires_at, verified, purpose FROM otp_verification
        WHERE email = ? AND purpose = 'password_reset' AND verified = 0
        ORDER BY id DESC
    """, (email,))
    rows = c.fetchall()
    
    if not rows:
        conn.close()
        return auth_form_redirect(
            "/reset-password",
            email=email,
            error="Invalid or expired verification code.",
        )
    
    # Find matching OTP hash
    otp_id = None
    for row_id, stored_hash, expires_at_str, verified, purpose in rows:
        if verify_otp_hash(otp_code, stored_hash):
            # Check expiration
            expires_at = datetime.fromisoformat(expires_at_str)
            if datetime.now() > expires_at:
                conn.close()
                return auth_form_redirect(
                    "/reset-password",
                    email=email,
                    error="Invalid or expired verification code.",
                )
            otp_id = row_id
            break
    
    if not otp_id:
        conn.close()
        return auth_form_redirect(
            "/reset-password",
            email=email,
            error="Invalid or expired verification code.",
        )
    
    # Mark OTP as verified
    c.execute("UPDATE otp_verification SET verified = 1 WHERE id = ?", (otp_id,))
    
    # Update password
    password_hash = pwd_context.hash(new_password)
    c.execute("UPDATE users SET password_hash = ? WHERE email = ?", (password_hash, email))
    conn.commit()
    conn.close()
    
    # Redirect to login with success message
    return RedirectResponse(
        url=react_redirect("/login", "message=Password reset successfully. You can sign in now."),
        status_code=status.HTTP_303_SEE_OTHER,
    )


# ========== PROFILE MANAGEMENT ROUTES ==========

@app.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request, user=Depends(require_login())):
    return RedirectResponse(url=react_redirect("/profile"), status_code=status.HTTP_303_SEE_OTHER)


@app.post("/profile/change-email")
async def change_email_request(
    request: Request,
    new_email: str = Form(...),
    current_password: str = Form(...),
    csrf_token: str = Form(None),
    user=Depends(require_login())
):
    """Request email change - verify password and send OTP to new email."""
    verify_csrf(request, form_token=csrf_token)
    username = user['username']
    
    conn = get_db()
    c = conn.cursor()
    
    # Verify current password
    c.execute("SELECT password_hash, email FROM users WHERE username = ?", (username,))
    row = c.fetchone()
    
    if not row or not pwd_context.verify(current_password, row[0]):
        conn.close()
        return auth_form_redirect("/profile", error="Incorrect password.")
    
    current_email = row[1]
    
    # Check if new email is already taken
    c.execute("SELECT username FROM users WHERE email = ? AND username != ?", (new_email, username))
    if c.fetchone():
        conn.close()
        return auth_form_redirect("/profile", error="That email is already in use.")
    
    # Generate OTP
    otp_code = ''.join(random.choices(string.digits, k=6))
    expires_at = datetime.now() + timedelta(minutes=10)
    
    # Store OTP with purpose 'email_change' (hashed)
    otp_hash = hash_otp(otp_code)
    c.execute("""
        INSERT INTO otp_verification (email, otp_code, expires_at, verified, purpose)
        VALUES (?, ?, ?, 0, 'email_change')
    """, (new_email, otp_hash, expires_at.isoformat()))
    conn.commit()
    conn.close()
    
    # Send OTP to NEW email
    send_otp_email(new_email, username, otp_code)
    
    # Redirect to verification page
    return RedirectResponse(
        url=react_redirect("/profile/verify-email-change", f"new_email={new_email}"),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@app.get("/profile/verify-email-change", response_class=HTMLResponse)
async def verify_email_change_page(request: Request, new_email: str = "", user=Depends(require_login())):
    q = f"new_email={new_email}" if new_email else ""
    return RedirectResponse(url=react_redirect("/profile/verify-email-change", q), status_code=status.HTTP_302_FOUND)


@app.post("/profile/verify-email-change")
async def verify_email_change_submit(
    request: Request,
    new_email: str = Form(...),
    otp_code: str = Form(...),
    csrf_token: str = Form(None),
    user=Depends(require_login())
):
    """Verify OTP and update email."""
    verify_csrf(request, form_token=csrf_token)
    username = user['username']
    
    # Verify OTP
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT id, otp_code, expires_at, verified, purpose FROM otp_verification
        WHERE email = ? AND purpose = 'email_change' AND verified = 0
        ORDER BY id DESC
    """, (new_email,))
    rows = c.fetchall()
    
    if not rows:
        conn.close()
        return auth_form_redirect(
            "/profile/verify-email-change",
            new_email=new_email,
            error="Invalid or expired verification code.",
        )
    
    # Find matching OTP hash
    otp_id = None
    for row_id, stored_hash, expires_at_str, verified, purpose in rows:
        if verify_otp_hash(otp_code, stored_hash):
            # Check expiration
            expires_at = datetime.fromisoformat(expires_at_str)
            if datetime.now() > expires_at:
                conn.close()
                return auth_form_redirect(
                    "/profile/verify-email-change",
                    new_email=new_email,
                    error="Invalid or expired verification code.",
                )
            otp_id = row_id
            break
    
    if not otp_id:
        conn.close()
        return auth_form_redirect(
            "/profile/verify-email-change",
            new_email=new_email,
            error="Invalid or expired verification code.",
        )
    
    # Mark OTP as verified
    c.execute("UPDATE otp_verification SET verified = 1 WHERE id = ?", (otp_id,))
    
    # Get old email for audit log
    c.execute("SELECT email FROM users WHERE username = ?", (username,))
    old_email = c.fetchone()[0]
    
    # Update email
    c.execute("UPDATE users SET email = ? WHERE username = ?", (new_email, username))
    
    # Add audit log
    c.execute("""
        INSERT INTO audit_logs (user_id, username, action, old_value, new_value, ip_address, performed_by)
        SELECT id, username, 'email_change', ?, ?, ?, ?
        FROM users WHERE username = ?
    """, (old_email, new_email, request.client.host, username, username))
    
    conn.commit()
    conn.close()
    
    # Redirect to profile with success message
    return RedirectResponse(
        url=react_redirect("/profile", "message=Email updated successfully."),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@app.post("/profile/change-password")
async def change_password_request(
    request: Request,
    old_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    csrf_token: str = Form(None),
    user=Depends(require_login())
):
    """Request password change - verify old password and send OTP."""
    verify_csrf(request, form_token=csrf_token)
    username = user['username']
    
    # Check passwords match
    if new_password != confirm_password:
        return auth_form_redirect("/profile", error="New passwords do not match.")

    # Check password strength
    if len(new_password) < 8:
        return auth_form_redirect(
            "/profile",
            error="Password must be at least 8 characters long.",
        )
    
    conn = get_db()
    c = conn.cursor()
    
    # Verify old password
    c.execute("SELECT password_hash, email FROM users WHERE username = ?", (username,))
    row = c.fetchone()
    
    if not row or not pwd_context.verify(old_password, row[0]):
        conn.close()
        return auth_form_redirect("/profile", error="Current password is incorrect.")
    
    email = row[1]
    
    # Hash new password
    new_password_hash = pwd_context.hash(new_password)
    
    # Generate OTP
    otp_code = ''.join(random.choices(string.digits, k=6))
    expires_at = datetime.now() + timedelta(minutes=10)
    
    # Store OTP with purpose 'password_change' and temp password hash (hashed)
    otp_hash = hash_otp(otp_code)
    c.execute("""
        INSERT INTO otp_verification (email, otp_code, expires_at, verified, purpose, temp_user_data)
        VALUES (?, ?, ?, 0, 'password_change', ?)
    """, (email, otp_hash, expires_at.isoformat(), new_password_hash))
    conn.commit()
    conn.close()
    
    # Send OTP to current email
    send_otp_email(email, username, otp_code)
    
    # Redirect to verification page
    return RedirectResponse(
        url=react_redirect("/profile/verify-password-change"),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@app.get("/profile/verify-password-change", response_class=HTMLResponse)
async def verify_password_change_page(request: Request, user=Depends(require_login())):
    return RedirectResponse(url=react_redirect("/profile/verify-password-change"), status_code=status.HTTP_302_FOUND)


@app.post("/profile/verify-password-change")
async def verify_password_change_submit(
    request: Request,
    otp_code: str = Form(...),
    csrf_token: str = Form(None),
    user=Depends(require_login())
):
    """Verify OTP and update password."""
    verify_csrf(request, form_token=csrf_token)
    username = user['username']
    
    # Get user email
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT email FROM users WHERE username = ?", (username,))
    row = c.fetchone()
    
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="User not found")
    
    email = row[0]
    
    # Verify OTP
    c.execute("""
        SELECT id, otp_code, expires_at, verified, purpose, temp_user_data FROM otp_verification
        WHERE email = ? AND purpose = 'password_change' AND verified = 0
        ORDER BY id DESC
    """, (email,))
    rows = c.fetchall()
    
    if not rows:
        conn.close()
        return auth_form_redirect(
            "/profile/verify-password-change",
            error="Invalid or expired verification code.",
        )
    
    # Find matching OTP hash
    otp_id = None
    new_password_hash = None
    for row_id, stored_hash, expires_at_str, verified, purpose, temp_pwd_hash in rows:
        if verify_otp_hash(otp_code, stored_hash):
            # Check expiration
            expires_at = datetime.fromisoformat(expires_at_str)
            if datetime.now() > expires_at:
                conn.close()
                return auth_form_redirect(
                    "/profile/verify-password-change",
                    error="Invalid or expired verification code.",
                )
            otp_id = row_id
            new_password_hash = temp_pwd_hash
            break
    
    if not otp_id:
        conn.close()
        return auth_form_redirect(
            "/profile/verify-password-change",
            error="Invalid or expired verification code.",
        )
    
    # Mark OTP as verified
    c.execute("UPDATE otp_verification SET verified = 1 WHERE id = ?", (otp_id,))
    
    # Update password
    c.execute("UPDATE users SET password_hash = ? WHERE username = ?", (new_password_hash, username))
    
    # Add audit log
    c.execute("""
        INSERT INTO audit_logs (user_id, username, action, old_value, new_value, ip_address, performed_by)
        SELECT id, username, 'password_change', 'old_password', 'new_password', ?, ?
        FROM users WHERE username = ?
    """, (request.client.host, username, username))
    
    conn.commit()
    conn.close()
    
    # Redirect to profile with success message
    return RedirectResponse(
        url=react_redirect("/profile", "message=Password updated successfully."),
        status_code=status.HTTP_303_SEE_OTHER,
    )


# --- Phase 6 refactor: /ws and /ws/guest proxies moved to routers.ws_proxy ---
# Handlers + _bridge_rag_websocket live in Login_system/routers/ws_proxy.py and
# are bound to this live module (factory pattern). The WebSocket protocol,
# payloads, framing, auth, rate limiting and guest scoping are byte-identical.
import sys as _sys_ws
from Login_system.routers.websocket_proxy import build_ws_proxy_router as _build_ws_proxy_router
app.include_router(_build_ws_proxy_router(_sys_ws.modules[__name__]))


# /ws/guest and _bridge_rag_websocket moved to Login_system/routers/ws_proxy.py
# (Phase 6 refactor); registered via app.include_router(build_ws_proxy_router(...)) above.


# ========== FEEDBACK & SUPPORT TICKET SYSTEM ==========

def generate_ticket_number():
    """Generate unique ticket number like TKT-20251118-0001"""
    import random
    from datetime import datetime
    date_str = datetime.now().strftime("%Y%m%d")
    random_num = random.randint(1000, 9999)
    return f"TKT-{date_str}-{random_num}"

def create_notification(username, role, notification_type, title, message, link=None, priority="normal", ticket_id=None):
    """Create a notification for a user"""
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        INSERT INTO notifications (user_username, user_role, notification_type, title, message, link, priority, related_ticket_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (username, role, notification_type, title, message, link, priority, ticket_id))
    conn.commit()
    conn.close()

@app.post("/feedback")
async def submit_feedback(request: Request, user=Depends(require_api_auth())):
    """Submit feedback endpoint - alias for thumbs feedback"""
    verify_csrf(request)
    data = await request.json()
    
    feedback_type = data.get("feedback_type", "down")  # "up" or "down"
    query_text = data.get("query_text", "")
    response_text = data.get("response_text", "")
    comment = data.get("comment", "")
    
    if feedback_type not in ["up", "down"]:
        feedback_type = "down"
    
    conn = get_db()
    c = conn.cursor()
    
    # Log the feedback
    c.execute("""
        INSERT INTO query_feedback (username, user_role, query_text, response_text, feedback_type, feedback_comment)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (user.get("username"), user.get("role"), query_text, response_text, feedback_type, comment))
    
    feedback_id = c.lastrowid
    conn.commit()
    conn.close()
    
    return {"message": "Feedback submitted", "feedback_id": feedback_id}


@app.post("/api/feedback/thumbs")
async def submit_thumbs_feedback(request: Request, user=Depends(require_login())):
    """Customer submits thumbs up/down feedback on a query"""
    verify_csrf(request)
    data = await request.json()
    
    feedback_type = data.get("feedback_type")  # "up" or "down"
    query_text = data.get("query_text", "")
    response_text = data.get("response_text", "")
    comment = data.get("comment", "")
    
    if feedback_type not in ["up", "down"]:
        raise HTTPException(status_code=400, detail="Invalid feedback type")
    
    conn = get_db()
    c = conn.cursor()
    
    # Log the feedback
    c.execute("""
        INSERT INTO query_feedback (username, user_role, query_text, response_text, feedback_type, feedback_comment)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (user.get("username"), user.get("role"), query_text, response_text, feedback_type, comment))
    
    feedback_id = c.lastrowid
    conn.commit()
    conn.close()
    
    return {"message": "Feedback submitted", "feedback_id": feedback_id}

@app.post("/api/support/ticket/create")
async def create_support_ticket(request: Request, user=Depends(require_api_auth())):
    """Customer creates a support ticket (can be from negative feedback or direct request)"""
    verify_csrf(request)
    data = await request.json()
    
    subject = data.get("subject", "").strip()
    description = data.get("description", "").strip()
    priority = data.get("priority", "normal")
    feedback_id = data.get("feedback_id")  # Optional: link to thumbs down feedback
    
    if not subject or not description:
        raise HTTPException(status_code=400, detail="Subject and description required")
    
    if priority not in ["low", "normal", "high", "urgent"]:
        priority = "normal"
    
    conn = get_db()
    c = conn.cursor()
    
    # Get customer ID
    c.execute("SELECT id FROM users WHERE username=?", (user.get("username"),))
    customer_row = c.fetchone()
    if not customer_row:
        conn.close()
        raise HTTPException(status_code=404, detail="User not found")
    
    customer_id = customer_row[0]

    # Scope the ticket to the customer's active business so only that tenant's
    # staff can ever see or act on it.
    ticket_tenant_id = int(
        user.get("active_tenant_id") or user.get("tenant_id") or DEFAULT_TENANT_ID
    )

    # Generate ticket number
    ticket_number = generate_ticket_number()
    
    # Assign to employee by default (or leave unassigned)
    assigned_to_role = "employee"
    
    # Create ticket
    c.execute("""
        INSERT INTO support_tickets 
        (ticket_number, customer_id, customer_username, subject, description, status, priority, assigned_to_role, tenant_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (ticket_number, customer_id, user.get("username"), subject, description, "open", priority, assigned_to_role, ticket_tenant_id))
    
    ticket_id = c.lastrowid
    
    # Link feedback if provided
    if feedback_id:
        c.execute("UPDATE query_feedback SET ticket_created=1, ticket_id=? WHERE id=?", (ticket_id, feedback_id))
    
    # Add initial message
    c.execute("""
        INSERT INTO ticket_messages (ticket_id, sender_username, sender_role, message)
        VALUES (?, ?, ?, ?)
    """, (ticket_id, user.get("username"), user.get("role"), description))
    
    # Notify only employees of THIS business (tenant isolation).
    c.execute(
        "SELECT username FROM users WHERE role='employee' AND active=1 AND tenant_id=?",
        (ticket_tenant_id,),
    )
    employees = c.fetchall()
    for (emp_username,) in employees:
        create_notification(
            emp_username, "employee", "new_ticket",
            f"New Support Ticket: {ticket_number}",
            f"Customer {user.get('username')} created a {priority} priority ticket: {subject}",
            f"/employee/tickets",
            "high" if priority in ["high", "urgent"] else "normal",
            ticket_id
        )
    
    conn.commit()
    conn.close()
    
    return {"message": "Ticket created successfully", "ticket_id": ticket_id, "ticket_number": ticket_number}

@app.get("/tickets")
def get_tickets_page(request: Request, user=Depends(require_login())):
    """Tickets endpoint - route based on role"""
    role = user.get("role")
    if role == "customer":
        return RedirectResponse("/my-tickets", status_code=302)
    elif role == "employee":
        return RedirectResponse("/employee/tickets", status_code=302)
    elif role == "admin":
        return RedirectResponse("/admin/tickets", status_code=302)
    else:
        raise HTTPException(status_code=403, detail="Forbidden")


@app.get("/api/support/tickets")
def get_my_tickets(request: Request, user=Depends(require_api_auth())):
    """Get tickets based on user role"""
    conn = get_db()
    c = conn.cursor()
    
    if user.get("role") == "customer":
        # Customers see their own tickets
        c.execute("""
            SELECT id, ticket_number, subject, description, status, priority, 
                   assigned_to, created_at, updated_at, escalated_to_admin
            FROM support_tickets
            WHERE customer_username=?
            ORDER BY created_at DESC
        """, (user.get("username"),))
    elif user.get("role") == "employee":
        # Employees see tickets for THEIR business assigned to them or unassigned
        _tid = int(user.get("tenant_id") or DEFAULT_TENANT_ID)
        c.execute("""
            SELECT id, ticket_number, subject, description, status, priority,
                   customer_username, assigned_to, created_at, updated_at, escalated_to_admin
            FROM support_tickets
            WHERE (assigned_to_role='employee' OR assigned_to IS NULL OR assigned_to=?) 
              AND escalated_to_admin=0
              AND tenant_id=?
            ORDER BY 
                CASE priority 
                    WHEN 'urgent' THEN 1
                    WHEN 'high' THEN 2
                    WHEN 'normal' THEN 3
                    WHEN 'low' THEN 4
                END,
                created_at DESC
        """, (user.get("username"), _tid))
    elif user.get("role") in ("admin", "master_admin"):
        # Admins and master admins see all tickets for THEIR business only
        _tid = int(user.get("tenant_id") or DEFAULT_TENANT_ID)
        c.execute("""
            SELECT id, ticket_number, subject, description, status, priority,
                   customer_username, assigned_to, assigned_to_role, created_at, updated_at, escalated_to_admin
            FROM support_tickets
            WHERE tenant_id=?
            ORDER BY 
                CASE WHEN escalated_to_admin=1 THEN 0 ELSE 1 END,
                CASE priority 
                    WHEN 'urgent' THEN 1
                    WHEN 'high' THEN 2
                    WHEN 'normal' THEN 3
                    WHEN 'low' THEN 4
                END,
                created_at DESC
        """, (_tid,))
    else:
        conn.close()
        return {"tickets": []}
    
    rows = c.fetchall()
    conn.close()
    
    tickets = []
    for row in rows:
        if user.get("role") == "customer":
            tickets.append({
                "id": row[0],
                "ticket_number": row[1],
                "subject": row[2],
                "description": row[3],
                "status": row[4],
                "priority": row[5],
                "assigned_to": row[6],
                "created_at": row[7],
                "updated_at": row[8],
                "escalated": row[9] == 1
            })
        else:
            tickets.append({
                "id": row[0],
                "ticket_number": row[1],
                "subject": row[2],
                "description": row[3],
                "status": row[4],
                "priority": row[5],
                "customer": row[6],
                "assigned_to": row[7],
                "assigned_to_role": row[8] if len(row) > 8 else None,
                "created_at": row[-3],
                "updated_at": row[-2],
                "escalated": row[-1] == 1
            })
    
    return {"tickets": tickets}

@app.get("/api/support/ticket/{ticket_id}")
def get_ticket_details(ticket_id: int, request: Request, user=Depends(require_login())):
    """Get full ticket details with messages"""
    conn = get_db()
    c = conn.cursor()
    
    # Get ticket
    c.execute("""
        SELECT id, ticket_number, customer_id, customer_username, subject, description,
               status, priority, assigned_to, assigned_to_role, created_at, updated_at,
               resolved_at, escalated_to_admin, resolution_notes, tenant_id
        FROM support_tickets
        WHERE id=?
    """, (ticket_id,))
    
    ticket_row = c.fetchone()
    if not ticket_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Ticket not found")
    
    # Verify access
    _role = str(user.get("role") or "").lower()
    if _role == "customer" and ticket_row[3] != user.get("username"):
        conn.close()
        raise HTTPException(status_code=403, detail="Access denied")
    # Staff (admin/employee) may only access tickets within their own business.
    if _role in ("admin", "master_admin", "employee"):
        _ticket_tenant = ticket_row[15] if len(ticket_row) > 15 and ticket_row[15] is not None else DEFAULT_TENANT_ID
        if int(_ticket_tenant) != int(user.get("tenant_id") or DEFAULT_TENANT_ID):
            conn.close()
            raise HTTPException(status_code=403, detail="Access denied")
    
    # Get messages
    c.execute("""
        SELECT id, sender_username, sender_role, message, is_internal_note, created_at
        FROM ticket_messages
        WHERE ticket_id=?
        ORDER BY created_at ASC
    """, (ticket_id,))
    
    message_rows = c.fetchall()
    conn.close()
    
    # Filter internal notes from customers
    messages = []
    for msg in message_rows:
        if msg[4] == 1 and user.get("role") == "customer":  # is_internal_note
            continue
        messages.append({
            "id": msg[0],
            "sender": msg[1],
            "role": msg[2],
            "message": msg[3],
            "is_internal": msg[4] == 1,
            "created_at": msg[5]
        })
    
    ticket = {
        "id": ticket_row[0],
        "ticket_number": ticket_row[1],
        "customer_id": ticket_row[2],
        "customer": ticket_row[3],
        "subject": ticket_row[4],
        "description": ticket_row[5],
        "status": ticket_row[6],
        "priority": ticket_row[7],
        "assigned_to": ticket_row[8],
        "assigned_to_role": ticket_row[9],
        "created_at": ticket_row[10],
        "updated_at": ticket_row[11],
        "resolved_at": ticket_row[12],
        "escalated": ticket_row[13] == 1,
        "resolution_notes": ticket_row[14],
        "messages": messages
    }
    
    return ticket

@app.post("/api/support/ticket/{ticket_id}/message")
async def add_ticket_message(ticket_id: int, request: Request, user=Depends(require_login())):
    """Add a message to a ticket"""
    verify_csrf(request)
    data = await request.json()
    
    message = data.get("message", "").strip()
    is_internal = data.get("is_internal", False)
    
    if not message:
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    
    # Customers cannot create internal notes
    if user.get("role") == "customer" and is_internal:
        is_internal = False
    
    conn = get_db()
    c = conn.cursor()
    
    # Verify ticket exists and get customer info
    c.execute("SELECT customer_username, assigned_to, status, tenant_id FROM support_tickets WHERE id=?", (ticket_id,))
    ticket_row = c.fetchone()
    if not ticket_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Ticket not found")
    
    customer_username, assigned_to, status, ticket_tenant_id = ticket_row
    
    # Verify access
    _role = str(user.get("role") or "").lower()
    if _role == "customer" and customer_username != user.get("username"):
        conn.close()
        raise HTTPException(status_code=403, detail="Access denied")
    # Staff may only act on tickets within their own business.
    if _role in ("admin", "master_admin", "employee"):
        _tt = ticket_tenant_id if ticket_tenant_id is not None else DEFAULT_TENANT_ID
        if int(_tt) != int(user.get("tenant_id") or DEFAULT_TENANT_ID):
            conn.close()
            raise HTTPException(status_code=403, detail="Access denied")
    
    # Add message
    c.execute("""
        INSERT INTO ticket_messages (ticket_id, sender_username, sender_role, message, is_internal_note)
        VALUES (?, ?, ?, ?, ?)
    """, (ticket_id, user.get("username"), user.get("role"), message, int(is_internal)))
    
    # Update ticket timestamp
    c.execute("UPDATE support_tickets SET updated_at=CURRENT_TIMESTAMP WHERE id=?", (ticket_id,))
    
    # Send notifications
    if user.get("role") == "customer":
        # Notify assigned employee/admin
        if assigned_to:
            c.execute("SELECT role FROM users WHERE username=?", (assigned_to,))
            assignee_row = c.fetchone()
            if assignee_row:
                create_notification(
                    assigned_to, assignee_row[0], "ticket_update",
                    f"New message on ticket #{ticket_id}",
                    f"Customer {user.get('username')} replied to the ticket",
                    f"/employee/tickets",
                    "normal", ticket_id
                )
    else:
        # Notify customer
        create_notification(
            customer_username, "customer", "ticket_update",
            f"Update on your ticket #{ticket_id}",
            f"{user.get('role').capitalize()} {user.get('username')} responded to your ticket",
            f"/my-tickets",
            "normal", ticket_id
        )
    
    conn.commit()
    conn.close()
    
    return {"message": "Message added successfully"}

@app.post("/api/support/ticket/{ticket_id}/assign")
async def assign_ticket(ticket_id: int, request: Request, user=Depends(require_role("admin", "master_admin", "employee"))):
    """Employee/Admin assigns ticket to themselves or another user"""
    verify_csrf(request)
    data = await request.json()
    
    assign_to = data.get("assign_to", user.get("username"))
    
    conn = get_db()
    c = conn.cursor()
    
    # Get assignee role
    c.execute("SELECT role FROM users WHERE username=?", (assign_to,))
    assignee_row = c.fetchone()
    if not assignee_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Assignee not found")
    
    assignee_role = assignee_row[0]
    
    # Update ticket
    c.execute("""
        UPDATE support_tickets 
        SET assigned_to=?, assigned_to_role=?, updated_at=CURRENT_TIMESTAMP
        WHERE id=?
    """, (assign_to, assignee_role, ticket_id))
    
    # Get ticket info for notification
    c.execute("SELECT customer_username, ticket_number FROM support_tickets WHERE id=?", (ticket_id,))
    ticket_row = c.fetchone()
    if ticket_row:
        customer, ticket_number = ticket_row
        # Notify assignee
        create_notification(
            assign_to, assignee_role, "ticket_assigned",
            f"Ticket {ticket_number} assigned to you",
            f"You have been assigned to handle this support ticket",
            f"/employee/tickets/{ticket_id}",
            "normal", ticket_id
        )
    
    conn.commit()
    conn.close()
    
    return {"message": "Ticket assigned successfully"}

@app.post("/api/support/ticket/{ticket_id}/escalate")
async def escalate_ticket(ticket_id: int, request: Request, user=Depends(require_role("employee"))):
    """Employee escalates ticket to admin"""
    verify_csrf(request)
    data = await request.json()
    
    escalation_note = data.get("note", "").strip()
    
    if not escalation_note:
        raise HTTPException(status_code=400, detail="Escalation note required")
    
    conn = get_db()
    c = conn.cursor()
    
    # Update ticket
    c.execute("""
        UPDATE support_tickets 
        SET escalated_to_admin=1, assigned_to_role='admin', updated_at=CURRENT_TIMESTAMP
        WHERE id=?
    """, (ticket_id,))
    
    # Add internal note
    c.execute("""
        INSERT INTO ticket_messages (ticket_id, sender_username, sender_role, message, is_internal_note)
        VALUES (?, ?, ?, ?, 1)
    """, (ticket_id, user.get("username"), user.get("role"), f"[ESCALATED TO ADMIN] {escalation_note}"))
    
    # Get ticket info
    c.execute("SELECT customer_username, ticket_number, priority FROM support_tickets WHERE id=?", (ticket_id,))
    ticket_row = c.fetchone()
    if ticket_row:
        customer, ticket_number, priority = ticket_row
        
        # Notify all admins
        c.execute("SELECT username FROM users WHERE role='admin' AND active=1")
        admins = c.fetchall()
        for (admin_username,) in admins:
            create_notification(
                admin_username, "admin", "ticket_escalated",
                f"🚨 Ticket {ticket_number} escalated",
                f"Employee {user.get('username')} escalated ticket from {customer}. Priority: {priority}",
                f"/admin/tickets",
                "high", ticket_id
            )
    
    conn.commit()
    conn.close()
    
    return {"message": "Ticket escalated to admin"}

@app.post("/api/support/ticket/{ticket_id}/resolve")
async def resolve_ticket(ticket_id: int, request: Request, user=Depends(require_role("admin", "master_admin", "employee"))):
    """Employee/Admin marks ticket as resolved"""
    verify_csrf(request)
    data = await request.json()
    
    resolution_notes = data.get("resolution_notes", "").strip()
    
    conn = get_db()
    c = conn.cursor()
    
    # Update ticket
    c.execute("""
        UPDATE support_tickets 
        SET status='resolved', resolved_at=CURRENT_TIMESTAMP, resolution_notes=?, updated_at=CURRENT_TIMESTAMP
        WHERE id=?
    """, (resolution_notes, ticket_id))
    
    # Add resolution message
    if resolution_notes:
        c.execute("""
            INSERT INTO ticket_messages (ticket_id, sender_username, sender_role, message)
            VALUES (?, ?, ?, ?)
        """, (ticket_id, user.get("username"), user.get("role"), f"[RESOLVED] {resolution_notes}"))
    
    # Get ticket info
    c.execute("SELECT customer_username, ticket_number FROM support_tickets WHERE id=?", (ticket_id,))
    ticket_row = c.fetchone()
    if ticket_row:
        customer, ticket_number = ticket_row
        # Notify customer
        create_notification(
            customer, "customer", "ticket_resolved",
            f"Ticket {ticket_number} resolved",
            f"Your support ticket has been resolved by {user.get('username')}",
            f"/my-tickets",
            "normal", ticket_id
        )
    
    conn.commit()
    conn.close()
    
    return {"message": "Ticket resolved successfully"}

@app.get("/api/notifications")
def get_notifications(request: Request, user=Depends(require_login())):
    """Get notifications for current user"""
    conn = get_db()
    c = conn.cursor()
    
    c.execute("""
        SELECT id, notification_type, title, message, link, is_read, created_at, priority, related_ticket_id
        FROM notifications
        WHERE user_username=? AND user_role=?
        ORDER BY is_read ASC, created_at DESC
        LIMIT 50
    """, (user.get("username"), user.get("role")))
    
    rows = c.fetchall()
    conn.close()
    
    notifications = []
    for row in rows:
        notifications.append({
            "id": row[0],
            "type": row[1],
            "title": row[2],
            "message": row[3],
            "link": row[4],
            "is_read": row[5] == 1,
            "created_at": row[6],
            "priority": row[7],
            "ticket_id": row[8]
        })
    
    return {"notifications": notifications}

@app.get("/api/notifications/unread-count")
def get_unread_count(request: Request, user=Depends(require_login())):
    """Get count of unread notifications"""
    conn = get_db()
    c = conn.cursor()
    
    c.execute("""
        SELECT COUNT(*) FROM notifications
        WHERE user_username=? AND user_role=? AND is_read=0
    """, (user.get("username"), user.get("role")))
    
    count = c.fetchone()[0]
    conn.close()
    
    return {"unread_count": count}

@app.post("/api/notifications/{notification_id}/read")
async def mark_notification_read(notification_id: int, request: Request, user=Depends(require_login())):
    """Mark notification as read"""
    verify_csrf(request)
    
    conn = get_db()
    c = conn.cursor()
    
    c.execute("""
        UPDATE notifications 
        SET is_read=1 
        WHERE id=? AND user_username=?
    """, (notification_id, user.get("username")))
    
    conn.commit()
    conn.close()
    
    return {"message": "Notification marked as read"}

@app.post("/api/notifications/mark-all-read")
async def mark_all_read(request: Request, user=Depends(require_login())):
    """Mark all notifications as read"""
    verify_csrf(request)
    
    conn = get_db()
    c = conn.cursor()
    
    c.execute("""
        UPDATE notifications 
        SET is_read=1 
        WHERE user_username=? AND user_role=?
    """, (user.get("username"), user.get("role")))
    
    conn.commit()
    conn.close()
    
    return {"message": "All notifications marked as read"}

@app.get("/api/admin/support/summary")
def get_admin_support_summary(request: Request, user=Depends(require_role("admin", "master_admin"))):
    """Get support ticket summary for the admin's own business."""
    conn = get_db()
    c = conn.cursor()
    _tid = int(user.get("tenant_id") or DEFAULT_TENANT_ID)
    
    # Total tickets
    c.execute("SELECT COUNT(*) FROM support_tickets WHERE tenant_id=?", (_tid,))
    total_tickets = c.fetchone()[0]
    
    # Open tickets
    c.execute("SELECT COUNT(*) FROM support_tickets WHERE status='open' AND tenant_id=?", (_tid,))
    open_tickets = c.fetchone()[0]
    
    # Escalated tickets
    c.execute("SELECT COUNT(*) FROM support_tickets WHERE escalated_to_admin=1 AND status!='resolved' AND tenant_id=?", (_tid,))
    escalated_tickets = c.fetchone()[0]
    
    # Resolved today
    c.execute("SELECT COUNT(*) FROM support_tickets WHERE DATE(resolved_at)=DATE('now') AND tenant_id=?", (_tid,))
    resolved_today = c.fetchone()[0]
    
    # Tickets by priority
    c.execute("""
        SELECT priority, COUNT(*) FROM support_tickets 
        WHERE status!='resolved' AND tenant_id=?
        GROUP BY priority
    """, (_tid,))
    by_priority = {row[0]: row[1] for row in c.fetchall()}
    
    # Recent negative feedback without tickets
    c.execute("""
        SELECT COUNT(*) FROM query_feedback 
        WHERE feedback_type='down' AND ticket_created=0
        AND DATE(created_at) >= DATE('now', '-7 days')
    """)
    negative_feedback_count = c.fetchone()[0]
    
    conn.close()
    
    return {
        "total_tickets": total_tickets,
        "open_tickets": open_tickets,
        "escalated_tickets": escalated_tickets,
        "resolved_today": resolved_today,
        "by_priority": by_priority,
        "negative_feedback_unaddressed": negative_feedback_count
    }


# /internal/check_rag_ws moved to Login_system/routers/system.py (Phase 4 refactor);
# registered via app.include_router(build_system_router(...)) near the favicon route.


try:
    from scripts.service_log_viewer import mount_service_logs

    mount_service_logs(app, _REPO_ROOT / "logs", require_login())
except Exception:
    pass
