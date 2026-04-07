from fastapi import FastAPI, Request, Form, Depends, status, HTTPException, WebSocket
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
import os
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

try:
    from backend.knowledge_base import add_document, chunk_and_add_document
except Exception:
    # If running in isolation, delay import errors until endpoint is used
    add_document = None
    chunk_and_add_document = None
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
    BCRYPT_ROUNDS
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

_UUID_FILENAME_PREFIX = re.compile(r"^[0-9a-f]{8}_(.+)$", re.IGNORECASE)
_PDF_TEXT_CACHE = {}
_PDF_TEXT_CACHE_MAX = 16


def _display_filename(stored_name: str) -> str:
    match = _UUID_FILENAME_PREFIX.match(stored_name or "")
    return match.group(1) if match else stored_name


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
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error. Please contact support."}
        )
    else:
        # Show details in development for debugging
        return JSONResponse(
            status_code=500,
            content={
                "error": str(exc),
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
                httponly=True,
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

# Session management constants
SESSION_ABSOLUTE_TIMEOUT = 86400  # 24 hours
SESSION_IDLE_TIMEOUT = 1800  # 30 minutes
MAX_CONCURRENT_SESSIONS = 3

# Session tracking (use Redis in production)
invalidated_sessions = set()  # Track invalidated session tokens
user_sessions = defaultdict(list)  # user_id -> list of (session_id, created_at, last_activity)
MAX_INVALIDATED_SESSIONS = 5000  # Prevent memory leak

# Account lockout tracking (use Redis in production)
failed_login_attempts = {}  # username -> count
account_lockouts = {}  # username -> lockout_until_timestamp
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_DURATION = 900  # 15 minutes

# Rate limiting storage (in-memory, use Redis in production)
# NOTE: This is reset on server restart and won't work properly with multiple workers
# For production, replace with Redis-backed rate limiting
rate_limit_store = defaultdict(lambda: {"count": 0, "reset_time": time.time()})
MAX_RATE_LIMIT_ENTRIES = 10000  # Prevent memory leak

def check_rate_limit(identifier: str, limit: int, window_seconds: int = 60) -> bool:
    """Check if request is within rate limit. Returns True if allowed."""
    now = time.time()
    key = identifier
    
    # Cleanup old entries to prevent memory leak
    if len(rate_limit_store) > MAX_RATE_LIMIT_ENTRIES:
        expired_keys = [
            k for k, v in rate_limit_store.items()
            if now > v["reset_time"]
        ]
        for k in expired_keys[:len(expired_keys)//2]:  # Remove half of expired
            del rate_limit_store[k]
    
    if now > rate_limit_store[key]["reset_time"]:
        # Reset window
        rate_limit_store[key] = {"count": 1, "reset_time": now + window_seconds}
        return True
    
    if rate_limit_store[key]["count"] >= limit:
        return False
    
    rate_limit_store[key]["count"] += 1
    return True

def check_account_lockout(username: str) -> tuple[bool, int]:
    """Check if account is locked out. Returns (is_locked, remaining_seconds)"""
    now = time.time()
    
    # Clean expired lockouts
    expired = [u for u, until in account_lockouts.items() if now >= until]
    for u in expired:
        del account_lockouts[u]
        if u in failed_login_attempts:
            del failed_login_attempts[u]
    
    if username in account_lockouts:
        remaining = int(account_lockouts[username] - now)
        return True, max(0, remaining)
    
    return False, 0

def record_failed_login(username: str, ip_address: str):
    """Record failed login attempt and lock account if threshold exceeded"""
    if username not in failed_login_attempts:
        failed_login_attempts[username] = 0
    
    failed_login_attempts[username] += 1
    
    log_security_event("login_failure", {
        "username": username,
        "ip_address": ip_address,
        "attempt_count": failed_login_attempts[username]
    }, severity="WARNING")
    
    if failed_login_attempts[username] >= MAX_FAILED_ATTEMPTS:
        account_lockouts[username] = time.time() + LOCKOUT_DURATION
        log_security_event("account_lockout", {
            "username": username,
            "ip_address": ip_address,
            "lockout_duration_seconds": LOCKOUT_DURATION
        }, severity="CRITICAL")

def clear_failed_attempts(username: str):
    """Clear failed login attempts after successful login"""
    if username in failed_login_attempts:
        del failed_login_attempts[username]

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
    
    # Get user ID for session tracking
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE username=?", (username,))
    row = c.fetchone()
    conn.close()
    
    if row:
        user_id = row[0]
        # Track session for concurrent session limits
        user_sessions[user_id].append({
            "session_id": session_id,
            "created_at": now,
            "last_activity": now
        })
        
        # Enforce concurrent session limit
        if len(user_sessions[user_id]) > MAX_CONCURRENT_SESSIONS:
            # Remove oldest session
            user_sessions[user_id].sort(key=lambda x: x["created_at"])
            oldest = user_sessions[user_id].pop(0)
            invalidated_sessions.add(oldest["session_id"])
            
            log_security_event("concurrent_session_limit", {
                "username": username,
                "user_id": user_id,
                "max_sessions": MAX_CONCURRENT_SESSIONS,
                "invalidated_session": oldest["session_id"]
            })
        
        # Prevent memory leak in invalidated sessions
        if len(invalidated_sessions) > MAX_INVALIDATED_SESSIONS:
            # Keep only recent half
            temp = list(invalidated_sessions)
            invalidated_sessions.clear()
            invalidated_sessions.update(temp[-MAX_INVALIDATED_SESSIONS//2:])
    
    return serializer.dumps(session_data)

def validate_session(session_data: dict) -> tuple[bool, str]:
    """Validate session hasn't expired or been invalidated. Returns (is_valid, error_message)"""
    # Check if session was explicitly invalidated
    session_id = session_data.get("session_id")
    if session_id and session_id in invalidated_sessions:
        return False, "Session invalidated"
    
    created_at = session_data.get("created_at", 0)
    last_activity = session_data.get("last_activity", created_at)
    now = time.time()
    
    # Check absolute timeout (24 hours)
    if now - created_at > SESSION_ABSOLUTE_TIMEOUT:
        return False, "Session expired (absolute timeout)"
    
    # Check idle timeout (30 minutes)
    if now - last_activity > SESSION_IDLE_TIMEOUT:
        return False, "Session expired (idle timeout)"
    
    # Update last activity (we'll need to refresh the token)
    session_data["last_activity"] = now
    
    return True, ""

def invalidate_session(session_id: str):
    """Mark a session as invalidated"""
    if session_id:
        invalidated_sessions.add(session_id)

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

def hash_otp(otp: str) -> str:
    """Hash OTP before storing in database"""
    return hashlib.sha256(otp.encode()).hexdigest()

def verify_otp_hash(otp: str, hashed: str) -> bool:
    """Verify OTP against hash"""
    return hash_otp(otp) == hashed

def validate_password(password: str) -> tuple[bool, str]:
    """Validate password strength and length.
    Returns (is_valid, error_message)
    """
    # Development: relax password rules for easier testing
    try:
        from config import IS_PRODUCTION
    except Exception:
        IS_PRODUCTION = True

    if not IS_PRODUCTION:
        # In development allow shorter/simple passwords (do basic length>0 check)
        if len(password) == 0:
            return False, "Password cannot be empty"
        return True, ""

    # Check length (8-128 characters)
    if not (8 <= len(password) <= 128):
        return False, "Password must be between 8 and 128 characters"
    
    # Basic complexity checks
    has_upper = any(c.isupper() for c in password)
    has_lower = any(c.islower() for c in password)
    has_digit = any(c.isdigit() for c in password)
    has_special = any(c in '!@#$%^&*()_+-=[]{}|;:,.<>?' for c in password)
    
    if not (has_upper or has_lower):
        return False, "Password must contain letters"
    
    if not (has_digit or has_special):
        return False, "Password must contain numbers or special characters"
    
    return True, ""

def validate_email(email: str) -> bool:
    """Validate email format."""
    import re
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email)) and len(email) <= 254

def validate_username(username: str) -> tuple[bool, str]:
    """Validate username format.
    Returns (is_valid, error_message)
    """
    if not (3 <= len(username) <= 50):
        return False, "Username must be between 3 and 50 characters"
    
    import re
    if not re.match(r'^[a-zA-Z0-9_-]+$', username):
        return False, "Username can only contain letters, numbers, underscores, and hyphens"
    
    return True, ""

def sanitize_input(text: str, max_length: int = 500) -> str:
    """Sanitize user input by stripping and truncating."""
    if not text:
        return ""
    return text.strip()[:max_length]

def verify_otp_hash_old(otp: str, hashed: str) -> bool:
    """Verify OTP against hash (kept for compatibility)"""
    return hashlib.sha256(otp.encode()).hexdigest() == hashed

# Resolve templates directory relative to this module file so uvicorn's CWD
# doesn't affect template resolution.
BASE_DIR = os.path.dirname(__file__)
TEMPLATES_DIR = os.path.abspath(os.path.join(BASE_DIR, "templates"))
STATIC_DIR = os.path.abspath(os.path.join(BASE_DIR, "static"))

# Mount static files
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# CSRF token function for Jinja2 templates
def csrf_token():
    """Generate CSRF token - returns a lambda that returns the token from cookie"""
    return lambda: secrets.token_urlsafe(32)

templates = Jinja2Templates(directory=TEMPLATES_DIR)
templates.env.globals['csrf_token'] = csrf_token()


def resolve_template(name: str) -> str:
    """Return an existing template filename from the templates directory.
    Tries the exact name, then a few common variants (capitalized/lower/title).
    """
    tpl_dir = TEMPLATES_DIR
    candidate = os.path.join(tpl_dir, name)
    if os.path.exists(candidate):
        return name
    # try a few common variants
    variants = [name.capitalize(), name.lower(), name.title()]
    for v in variants:
        if v == name:
            continue
        if os.path.exists(os.path.join(tpl_dir, v)):
            return v
    return name

DB_PATH = str((Path(__file__).resolve().parent / "users.db"))


def get_db():
    conn = sqlite3.connect(DB_PATH)
    return conn


def create_user(username, password, role, mfa_enabled=0, mfa_secret=None):
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        INSERT OR IGNORE INTO users (username, password_hash, role, mfa_enabled, mfa_secret)
        VALUES (?, ?, ?, ?, ?)
    """, (username, pwd_context.hash(password), role, int(mfa_enabled), mfa_secret))
    conn.commit()
    conn.close()



def verify_csrf(request: Request):
    """Simple CSRF verification: header X-CSRF-Token must match csrf_token cookie."""
    header = request.headers.get("x-csrf-token")
    cookie = request.cookies.get("csrf_token")
    if not cookie or header != cookie:
        raise HTTPException(status_code=403, detail="CSRF token missing or invalid")


def init_db():
    conn = get_db()
    c = conn.cursor()
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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        create_user("admin", "admin123", "admin")
        create_user("employee", "employee123", "employee")
        create_user("customer", "customer123", "customer")
        conn.commit()
    else:
        # Check if columns exist, add if not
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


@app.on_event("startup")
def on_startup():
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
        
        # Development fallback: if password_hash empty allow simple passwords
        try:
            from config import IS_PRODUCTION
        except Exception:
            IS_PRODUCTION = True
        if not IS_PRODUCTION and (not password_hash or password_hash.strip() == ""):
            if password == username or password == f"{username}123":
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
        except Exception as e:
            # Log failed verification but don't expose details
            # Development fallback: allow simple username==password logins when not in production
            if not IS_PRODUCTION:
                try:
                    if password == username:
                        return username, role
                except Exception:
                    pass
            pass
    return None, None


def get_current_user(request: Request):
    token = request.cookies.get(SESSION_COOKIE)
    try:
        if token:
            data = serializer.loads(token)
            return data
    except Exception:
        return None


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
    
    # Insert new Google user as customer
    c.execute("""
        INSERT INTO users (username, password_hash, role, google_id, email, profile_picture, auth_provider, active)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (username, "", "customer", google_id, email, picture, "google", 1))
    
    conn.commit()
    conn.close()
    
    return {"username": username, "role": "customer"}


def generate_otp(length=6):
    """Generate a random OTP code."""
    return ''.join(random.choices(string.digits, k=length))


def store_otp(email: str, otp_code: str, temp_user_data: str):
    """Store OTP in database with expiration."""
    conn = get_db()
    c = conn.cursor()
    
    # Delete old OTPs for this email
    c.execute("DELETE FROM otp_verification WHERE email=?", (email,))
    
    # Store new OTP (expires in 10 minutes)
    expires_at = datetime.now() + timedelta(minutes=10)
    # Hash OTP before storing
    otp_hash = hash_otp(otp_code)
    c.execute("""
        INSERT INTO otp_verification (email, otp_code, expires_at, temp_user_data, purpose)
        VALUES (?, ?, ?, ?, 'registration')
    """, (email, otp_hash, expires_at, temp_user_data))
    
    conn.commit()
    conn.close()


def send_otp_email(email: str, name: str, otp_code: str):
    """Send OTP email via EmailJS API (server-side)."""
    # Guard: warn early if any credential is missing / still placeholder
    missing = []
    for key, val in [
        ("EMAILJS_SERVICE_ID",  EMAILJS_SERVICE_ID),
        ("EMAILJS_TEMPLATE_ID", EMAILJS_TEMPLATE_ID),
        ("EMAILJS_PUBLIC_KEY",  EMAILJS_PUBLIC_KEY),
        ("EMAILJS_PRIVATE_KEY", EMAILJS_PRIVATE_KEY),
    ]:
        if not val or val.startswith("YOUR_"):
            missing.append(key)
    if missing:
        print(f"[EMAIL] SKIPPED – missing/placeholder credentials: {', '.join(missing)}")
        print(f"[EMAIL] Fill in the real values in your .env file and restart the server.")
        return False

    try:
        url = "https://api.emailjs.com/api/v1.0/email/send"
        
        payload = {
            "service_id": EMAILJS_SERVICE_ID,
            "template_id": EMAILJS_TEMPLATE_ID,
            "user_id": EMAILJS_PUBLIC_KEY,
            "accessToken": EMAILJS_PRIVATE_KEY,
            "template_params": {
                "to_email": email,
                "to_name": name,
                "otp_code": otp_code,
                "reply_to": email
            }
        }
        
        response = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=10)
        
        if response.status_code == 200:
            print(f"[EMAIL] OTP email sent successfully to {email}")
            return True
        else:
            # Log full response body so you can see the exact EmailJS error
            print(f"[EMAIL] Failed to send email - status: {response.status_code}")
            print(f"[EMAIL] EmailJS response body: {response.text}")
            return False
    except Exception as e:
        print(f"[EMAIL] Email service exception: {type(e).__name__}: {e}")
        return False


def verify_otp(email: str, otp_code: str):
    """Verify OTP code for registration and return temp user data if valid."""
    conn = get_db()
    c = conn.cursor()
    
    # Fetch all unverified OTPs for this email (to check hash)
    c.execute("""
        SELECT id, otp_code, temp_user_data, expires_at, purpose FROM otp_verification 
        WHERE email=? AND verified=0 AND purpose='registration'
        ORDER BY created_at DESC
    """, (email,))
    
    results = c.fetchall()
    
    if not results:
        conn.close()
        return None
    
    # Try to verify hash against each stored OTP
    for row_id, stored_hash, temp_user_data, expires_at, purpose in results:
        if verify_otp_hash(otp_code, stored_hash):
            # Check if OTP has expired
            if datetime.now() > datetime.fromisoformat(expires_at):
                conn.close()
                return None
            
            # Mark OTP as verified using row ID to avoid race conditions
            c.execute("""
                UPDATE otp_verification 
                SET verified=1 
                WHERE id=?
            """, (row_id,))
            
            conn.commit()
            conn.close()
            
            return temp_user_data
    
    conn.close()
    return None


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


def require_login(role=None):
    def wrapper(request: Request):
        user = get_current_user(request)
        if not user or (role and user.get("role") != role):
            raise HTTPException(
                status_code=status.HTTP_303_SEE_OTHER,
                detail="Not authenticated",
                headers={"Location": "/?error=login"},
            )
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
            raise HTTPException(
                status_code=status.HTTP_303_SEE_OTHER,
                detail="Not authenticated",
                headers={"Location": "/?error=login"},
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


@app.get("/register", response_class=HTMLResponse)
def register_form(request: Request):
    """Show registration form for new users."""
    error = request.query_params.get("error")
    return templates.TemplateResponse(resolve_template("register.html"), {"request": request, "error": error})


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
        url=f"/verify-otp?email={email}", 
        status_code=status.HTTP_303_SEE_OTHER
    )


@app.get("/verify-otp", response_class=HTMLResponse)
def verify_otp_form(request: Request):
    """Show OTP verification form."""
    email = request.query_params.get("email")
    error = request.query_params.get("error")
    return templates.TemplateResponse(resolve_template("verify_otp.html"), {
        "request": request, 
        "email": email,
        "error": error
    })


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
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        INSERT INTO users (username, password_hash, role, email, full_name, email_verified, auth_provider, active)
        VALUES (?, ?, ?, ?, ?, 1, 'local', 1)
    """, (
        user_data["username"],
        user_data["password_hash"],
        user_data["role"],
        user_data["email"],
        user_data["full_name"]
    ))
    conn.commit()
    conn.close()
    
    # Redirect to login with success message
    return RedirectResponse(url="/?success=registration_complete", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/change-username", response_class=HTMLResponse)
def change_username_form(request: Request):
    """Show username change form."""
    error = request.query_params.get("error")
    success = request.query_params.get("success")
    return templates.TemplateResponse(resolve_template("change_username.html"), {
        "request": request,
        "error": error,
        "success": success
    })


@app.post("/change-username")
async def change_username(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    new_username: str = Form(...)
):
    """Process username change request (one-time only)."""
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
        
        # Redirect to main page
        response = RedirectResponse(url="/main", status_code=status.HTTP_303_SEE_OTHER)
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
    """Redirect root to login page."""
    return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    """Show login form."""
    error = request.query_params.get("error")
    return templates.TemplateResponse(resolve_template("login.html"), {"request": request, "error": error})


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
        return templates.TemplateResponse(resolve_template("login.html"), {
            "request": request, 
            "error": "Too many login attempts. Please try again later."
        })
    
    # Check account lockout
    is_locked, remaining_seconds = check_account_lockout(username)
    if is_locked:
        minutes_remaining = (remaining_seconds + 59) // 60  # Round up
        log_security_event("lockout_attempt", {
            "username": username,
            "ip_address": client_ip,
            "remaining_seconds": remaining_seconds
        }, severity="WARNING")
        return templates.TemplateResponse(resolve_template("login.html"), {
            "request": request, 
            "error": f"Account locked. Try again in {minutes_remaining} minute(s)."
        })
    
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
                return templates.TemplateResponse(resolve_template("login.html"), {"request": request, "error": "MFA token required"})
            try:
                import pyotp
                totp = pyotp.TOTP(row[2])
                if not totp.verify(mfa_token):
                    record_failed_login(actual_username, client_ip)
                    return templates.TemplateResponse(resolve_template("login.html"), {"request": request, "error": "Invalid MFA token"})
            except Exception:
                return templates.TemplateResponse(resolve_template("login.html"), {"request": request, "error": "MFA verification failed (pyotp required)"})

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
        
        if role == "admin":
            redirect_url = "/admin"
        elif role == "employee":
            redirect_url = "/employee"
        else:
            redirect_url = "/main"
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
        return templates.TemplateResponse(resolve_template("login.html"), {"request": request, "error": "Invalid credentials"})


@app.get("/users")
def list_users(request: Request, user=Depends(require_login("admin"))):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id, username, role, mfa_enabled FROM users")
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
        allowed_roles = ['admin', 'employee', 'customer']
        if v not in allowed_roles:
            raise ValueError(f"Role must be one of: {', '.join(allowed_roles)}")
        return v



@app.post("/users")
def create_user_api(request: Request, data: UserCreate, admin=Depends(require_login("admin"))):
    verify_csrf(request)
    create_user(data.username, data.password, data.role)
    return {"status": "created", "username": data.username}



class UserUpdate(BaseModel):
    role: Optional[str] = None
    password: Optional[str] = None
    
    @validator('role')
    def validate_role(cls, v):
        """Validate role if provided"""
        if v is not None:
            allowed_roles = ['admin', 'employee', 'customer']
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
def update_user(request: Request, user_id: int, data: UserUpdate, admin=Depends(require_login("admin"))):
    verify_csrf(request)
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
def delete_user(request: Request, user_id: int, admin=Depends(require_login("admin"))):
    verify_csrf(request)
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM users WHERE id=?", (user_id,))
    conn.commit()
    conn.close()
    return {"status": "deleted"}



@app.post("/users/{user_id}/mfa-enable")
def enable_mfa(request: Request, user_id: int, admin=Depends(require_login("admin"))):
    verify_csrf(request)
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
def admin_dashboard(request: Request, user=Depends(require_login("admin"))):
    """Admin dashboard - returns HTML for browsers, JSON for API requests"""
    # Check if client wants JSON (API request)
    accept_header = request.headers.get("accept", "")
    if "application/json" in accept_header:
        return JSONResponse({"status": "ok", "role": "admin", "username": user.get("username")})
    # Return HTML for browser
    return templates.TemplateResponse("admin.html", {"request": request, "user": user})


@app.get("/employee")
def employee_dashboard(request: Request, user=Depends(require_login("employee"))):
    """Employee dashboard - returns HTML for browsers, JSON for API requests"""
    # Check if client wants JSON (API request)
    accept_header = request.headers.get("accept", "")
    if "application/json" in accept_header:
        return JSONResponse({"status": "ok", "role": "employee", "username": user.get("username")})
    # Return HTML for browser
    return templates.TemplateResponse("employee.html", {"request": request, "user": user})


@app.get("/customer")
def customer_dashboard(request: Request, user=Depends(require_login("customer"))):
    """Customer dashboard - returns HTML for browsers, JSON for API requests"""
    # Check if client wants JSON (API request)
    accept_header = request.headers.get("accept", "")
    if "application/json" in accept_header:
        return JSONResponse({"status": "ok", "role": "customer", "username": user.get("username")})
    # Return HTML for browser (redirect to main for customers)
    return RedirectResponse("/main", status_code=302)


@app.get("/admin/users", response_class=HTMLResponse)
def admin_users_page(request: Request, user=Depends(require_login("admin"))):
    return templates.TemplateResponse("admin_users.html", {"request": request, "user": user})


@app.get("/admin/knowledge", response_class=HTMLResponse)
def admin_knowledge_page(request: Request, user=Depends(require_login("admin"))):
    return templates.TemplateResponse("admin_knowledge.html", {"request": request, "user": user})


@app.get("/admin/analytics", response_class=HTMLResponse)
def admin_analytics_page(request: Request, user=Depends(require_login("admin"))):
    return templates.TemplateResponse("admin_analytics.html", {"request": request, "user": user})


@app.get("/admin/audit-logs", response_class=HTMLResponse)
def admin_audit_logs_page(request: Request, user=Depends(require_login("admin"))):
    """Display audit logs for admin review."""
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT id, user_id, username, action, old_value, new_value, timestamp, ip_address
        FROM audit_logs
        ORDER BY timestamp DESC
        LIMIT 100
    """)
    rows = c.fetchall()
    conn.close()
    
    logs = []
    for row in rows:
        logs.append({
            "id": row[0],
            "user_id": row[1],
            "username": row[2],
            "action": row[3],
            "old_value": row[4],
            "new_value": row[5],
            "timestamp": row[6],
            "ip_address": row[7]
        })
    
    return templates.TemplateResponse("admin_audit_logs.html", {
        "request": request,
        "user": user,
        "logs": logs
    })


@app.get("/api/users")
def list_users(request: Request, user=Depends(require_api_auth("admin"))):
    """Admin: Get all users (admin, employee, customer)"""
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id, username, role, active, email, full_name FROM users ORDER BY id")
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
def list_customers(request: Request, user=Depends(require_api_role("admin", "employee"))):
    """Employee: Get only customer accounts"""
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id, username, active, email, full_name, created_at FROM users WHERE role='customer' ORDER BY id")
    rows = c.fetchall()
    conn.close()
    customers = []
    for row in rows:
        customers.append({
            "id": row[0],
            "username": row[1],
            "active": bool(row[2]) if len(row) > 2 else True,
            "email": row[3] if len(row) > 3 else None,
            "full_name": row[4] if len(row) > 4 else None,
            "created_at": row[5] if len(row) > 5 else None
        })
    return customers


@app.post("/api/users/create")
async def create_new_user(request: Request, user=Depends(require_login("admin"))):
    verify_csrf(request)
    data = await request.json()
    username = data.get("username")
    password = data.get("password")
    role = data.get("role", "customer")
    
    if not username or not password:
        raise HTTPException(status_code=400, detail="Username and password required")
    
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    
    if role not in ["admin", "employee", "customer"]:
        raise HTTPException(status_code=400, detail="Invalid role")
    
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("""
            INSERT INTO users (username, password_hash, role, active)
            VALUES (?, ?, ?, 1)
        """, (username, pwd_context.hash(password), role))
        conn.commit()
        conn.close()
        return {"status": "created", "username": username}
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Username already exists")


@app.post("/api/users/{user_id}/deactivate")
async def deactivate_user_api(request: Request, user_id: int, user=Depends(require_login("admin"))):
    verify_csrf(request)
    conn = get_db()
    c = conn.cursor()
    
    # Get username for audit
    c.execute("SELECT username FROM users WHERE id=?", (user_id,))
    row = c.fetchone()
    if row:
        username = row[0]
        c.execute("UPDATE users SET active=0 WHERE id=?", (user_id,))
        
        # Audit log
        c.execute("""
            INSERT INTO audit_logs (user_id, username, action, old_value, new_value, ip_address, performed_by)
            VALUES (?, ?, 'ACCOUNT_DEACTIVATED', 'active', 'inactive', ?, ?)
        """, (user_id, username, request.client.host, user.get("username")))
        
    conn.commit()
    conn.close()
    return {"status": "deactivated"}


@app.post("/api/users/{user_id}/activate")
async def activate_user_api(request: Request, user_id: int, user=Depends(require_login("admin"))):
    verify_csrf(request)
    conn = get_db()
    c = conn.cursor()
    
    # Get username for audit
    c.execute("SELECT username FROM users WHERE id=?", (user_id,))
    row = c.fetchone()
    if row:
        username = row[0]
        c.execute("UPDATE users SET active=1 WHERE id=?", (user_id,))
        
        # Audit log
        c.execute("""
            INSERT INTO audit_logs (user_id, username, action, old_value, new_value, ip_address, performed_by)
            VALUES (?, ?, 'ACCOUNT_ACTIVATED', 'inactive', 'active', ?, ?)
        """, (user_id, username, request.client.host, user.get("username")))
        
    conn.commit()
    conn.close()
    return {"status": "activated"}


@app.delete("/api/users/{user_id}/delete")
def delete_user_api(request: Request, user_id: int, user=Depends(require_login("admin"))):
    verify_csrf(request)
    # Prevent deleting yourself
    if user.get("username"):
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT username FROM users WHERE id=?", (user_id,))
        row = c.fetchone()
        if row and row[0] == user.get("username"):
            conn.close()
            raise HTTPException(status_code=400, detail="Cannot delete your own account")
        c.execute("DELETE FROM users WHERE id=?", (user_id,))
        conn.commit()
        conn.close()
    return {"status": "deleted"}


# Employee-specific customer activation/deactivation
@app.post("/api/customers/{customer_id}/deactivate")
async def deactivate_customer_api(request: Request, customer_id: int, user=Depends(require_role("admin", "employee"))):
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
async def activate_customer_api(request: Request, customer_id: int, user=Depends(require_role("admin", "employee"))):
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
async def change_user_role(request: Request, user_id: int, user=Depends(require_login("admin"))):
    """Admin only: Change user role"""
    verify_csrf(request)
    data = await request.json()
    new_role = data.get("role")
    
    if new_role not in ["admin", "employee", "customer"]:
        raise HTTPException(status_code=400, detail="Invalid role")
    
    conn = get_db()
    c = conn.cursor()
    
    # Get old role for audit
    c.execute("SELECT username, role FROM users WHERE id=?", (user_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="User not found")
    
    username, old_role = row
    
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
async def update_user_profile(request: Request, user_id: int, user=Depends(require_role("admin", "employee"))):
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
async def trigger_customer_password_reset(request: Request, customer_id: int, user=Depends(require_role("admin", "employee"))):
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
def get_customer_notes(request: Request, customer_id: int, user=Depends(require_role("admin", "employee"))):
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
async def add_customer_note(request: Request, customer_id: int, user=Depends(require_role("admin", "employee"))):
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
async def delete_customer_note(request: Request, customer_id: int, note_id: int, user=Depends(require_role("admin", "employee"))):
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
def employee_analytics(request: Request, user=Depends(require_role("admin", "employee"))):
    """Employee: Get customer-focused analytics only"""
    conn = get_db()
    c = conn.cursor()
    
    # Total customers
    c.execute("SELECT COUNT(*) FROM users WHERE role='customer'")
    total_customers = c.fetchone()[0]
    
    # Active customers
    c.execute("SELECT COUNT(*) FROM users WHERE role='customer' AND active=1")
    active_customers = c.fetchone()[0]
    
    # Recent registrations (last 30 days)
    thirty_days_ago = (datetime.now() - timedelta(days=30)).isoformat()
    c.execute("SELECT COUNT(*) FROM users WHERE role='customer' AND created_at > ?", (thirty_days_ago,))
    recent_registrations = c.fetchone()[0]
    
    # Total support notes
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


# ========== CUSTOMER: SELF-SERVICE FEATURES ==========

@app.get("/api/my-profile")
def get_my_profile(request: Request, user=Depends(require_login())):
    """Customer: Get own profile data"""
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT username, email, full_name, role, created_at, active
        FROM users WHERE username=?
    """, (user.get("username"),))
    row = c.fetchone()
    conn.close()
    
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    
    return {
        "username": row[0],
        "email": row[1],
        "full_name": row[2],
        "role": row[3],
        "created_at": row[4],
        "active": bool(row[5])
    }


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
    response = RedirectResponse("/", status_code=302)
    response.delete_cookie(SESSION_COOKIE)
    return response


@app.get("/main", response_class=HTMLResponse)
def main_dashboard(request: Request, user=Depends(require_login())):
    return templates.TemplateResponse("main.html", {"request": request, "user": user})


@app.get("/employee/customers", response_class=HTMLResponse)
def employee_customers_page(request: Request, user=Depends(require_role("admin", "employee"))):
    """Employee customer management page"""
    return templates.TemplateResponse("employee_customers.html", {"request": request, "user": user})


@app.get("/notifications", response_class=HTMLResponse)
def notifications_page(request: Request, user=Depends(require_login())):
    """Notification center for all users"""
    return templates.TemplateResponse("notifications.html", {"request": request, "user": user})


@app.get("/my-tickets", response_class=HTMLResponse)
def my_tickets_page(request: Request, user=Depends(require_login("customer"))):
    """Customer support tickets page"""
    return templates.TemplateResponse("customer_tickets.html", {"request": request, "user": user})


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
    
    response = RedirectResponse("/", status_code=302)
    response.delete_cookie(SESSION_COOKIE)
    response.delete_cookie("csrf_token")
    return response




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
async def proxy_upload_rag(request: Request, file: UploadFile = File(...), user=Depends(require_login("admin"))):
    """Proxy upload endpoint on the auth server. Accepts a PDF/TXT, parses it,
    and indexes it into the knowledge base by calling backend.knowledge_base.chunk_and_add_document.
    This keeps uploads under the login server origin so cookies/CSRF work.
    """
    # Verify CSRF token (same as RAG server)
    verify_csrf(request)

    if chunk_and_add_document is None:
        # Try to import lazily
        try:
            from backend.knowledge_base import chunk_and_add_document as _cad
            globals()['chunk_and_add_document'] = _cad
        except Exception as e:
            log_security_event("upload_error", {
                "username": user.get("username"),
                "reason": "kb_import_failed",
                "error": str(e)
            }, severity="ERROR")
            raise HTTPException(status_code=500, detail=f"Knowledge base not available: {str(e)}")

    # Security: File upload validation
    MAX_UPLOAD_SIZE = 20 * 1024 * 1024  # 20MB (increased for large PDFs)
    ALLOWED_EXTENSIONS = {'.txt', '.pdf', '.md'}
    
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
        return {"message": f"Unsupported file type. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"}
    
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

    assets_dir = Path(__file__).resolve().parent.parent / 'backend' / 'assets'
    assets_dir.mkdir(parents=True, exist_ok=True)
    safe_filename = f"{uuid.uuid4().hex[:8]}_{filename}"
    save_path = assets_dir / safe_filename
    save_path.write_bytes(content)

    text = ""
    if file_ext == ".txt" or file_ext == ".md":
        try:
            text = content.decode("utf-8")
        except Exception:
            text = content.decode(errors="ignore")
        logger.info(f"Extracted text/markdown: {len(text)} chars")
    elif file_ext == ".pdf":
        # PDF EXTRACTION with better error handling
        try:
            from PyPDF2 import PdfReader
            logger.info(f"Extracting PDF: {filename}...")
            reader = PdfReader(save_path)
            pages = []
            num_pages = len(reader.pages)
            
            for page_num, p in enumerate(reader.pages):
                try:
                    page_text = p.extract_text() or ""
                    pages.append(page_text)
                except Exception as e:
                    logger.warning(f"Could not extract page {page_num}: {e}")
                    pages.append("")
            
            text = "\n\n".join(pages)
            logger.info(f"Extracted PDF: {len(text)} chars from {num_pages} pages")
        except ImportError:
            log_security_event("upload_error", {
                "username": user.get("username"),
                "filename": filename,
                "reason": "pypdf2_missing"
            }, severity="WARNING")
            return {"message": "PyPDF2 not installed. Install with: pip install PyPDF2"}
        except Exception as e:
            log_security_event("upload_error", {
                "username": user.get("username"),
                "filename": filename,
                "reason": "pdf_extraction_failed",
                "error": str(e)
            }, severity="ERROR")
            return {"message": f"Could not parse PDF: {str(e)}. File may be corrupted or encrypted."}

    doc_id = f"upload_{uuid.uuid4().hex[:8]}_{filename}"
    metadata = {"source": "upload_proxy", "filename": filename, "file_size_mb": file_size_mb}
    
    try:
        # Use chunk_and_add_document instead of add_document for proper handling of large files
        chunks_indexed = chunk_and_add_document(doc_id=doc_id, text=text, metadata=metadata)
        
        if chunks_indexed > 0:
            log_security_event("file_upload_success", {
                "username": user.get("username"),
                "filename": filename,
                "chunks_indexed": chunks_indexed,
                "file_size_mb": f"{file_size_mb:.1f}"
            })
            return {
                "message": f"✓ File {filename} uploaded and indexed as {chunks_indexed} chunk(s).",
                "filename": filename,
                "chunks_indexed": chunks_indexed,
                "file_size_mb": file_size_mb
            }
        else:
            log_security_event("file_upload_warning", {
                "username": user.get("username"),
                "filename": filename,
                "reason": "no_content_extracted"
            }, severity="WARNING")
            return {
                "message": f"⚠ File {filename} uploaded but no useful content found (may be blank or only images).",
                "filename": filename,
                "chunks_indexed": 0,
                "file_size_mb": file_size_mb
            }
    except Exception as e:
        log_security_event("upload_error", {
            "username": user.get("username"),
            "filename": filename,
            "reason": "indexing_failed",
            "error": str(e)
        }, severity="ERROR")
        raise HTTPException(status_code=500, detail=f"Failed to index uploaded document: {str(e)}")


@app.get("/api/knowledge/files")
def list_knowledge_files(request: Request, user=Depends(require_api_role("admin", "employee"))):
    """List all files in the knowledge base assets directory."""
    assets_dir = Path(__file__).resolve().parent.parent / 'backend' / 'assets'
    if not assets_dir.exists():
        return []
    
    files = []
    for file_path in assets_dir.iterdir():
        if file_path.is_file() and file_path.suffix.lower() in ['.txt', '.pdf', '.md']:
            stat = file_path.stat()
            stored_name = file_path.name
            files.append({
                "name": stored_name,
                "stored_name": stored_name,
                "display_name": _display_filename(stored_name),
                "size": stat.st_size,
                "modified": stat.st_mtime
            })
    
    return sorted(files, key=lambda x: x['modified'], reverse=True)


@app.get("/api/knowledge/files/{filename}")
def get_knowledge_file_content(request: Request, filename: str, user=Depends(require_role("admin", "employee"))):
    """Get the content of a knowledge base file."""
    assets_dir = Path(__file__).resolve().parent.parent / 'backend' / 'assets'
    file_path = assets_dir / filename
    
    # Security check: ensure the file is within assets directory
    try:
        file_path = file_path.resolve()
        if not str(file_path).startswith(str(assets_dir.resolve())):
            raise HTTPException(status_code=403, detail="Access denied")
    except Exception:
        raise HTTPException(status_code=404, detail="File not found")
    
    if not file_path.exists() or not file_path.is_file():
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
def download_knowledge_file(request: Request, filename: str, inline: bool = False, user=Depends(require_role("admin", "employee"))):
    """Download a knowledge base file."""
    assets_dir = Path(__file__).resolve().parent.parent / 'backend' / 'assets'
    file_path = assets_dir / filename
    
    # Security check
    try:
        file_path = file_path.resolve()
        if not str(file_path).startswith(str(assets_dir.resolve())):
            raise HTTPException(status_code=403, detail="Access denied")
    except Exception:
        raise HTTPException(status_code=404, detail="File not found")
    
    if not file_path.exists() or not file_path.is_file():
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
def preview_knowledge_pdf(request: Request, filename: str, user=Depends(require_role("admin", "employee"))):
    """Serve PDF as inline content for in-browser preview iframe."""
    assets_dir = Path(__file__).resolve().parent.parent / 'backend' / 'assets'
    file_path = assets_dir / filename

    try:
        file_path = file_path.resolve()
        if not str(file_path).startswith(str(assets_dir.resolve())):
            raise HTTPException(status_code=403, detail="Access denied")
    except Exception:
        raise HTTPException(status_code=404, detail="File not found")

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    if file_path.suffix.lower() != '.pdf':
        raise HTTPException(status_code=400, detail="Preview endpoint only supports PDF files")

    pdf_bytes = file_path.read_bytes()
    response = Response(content=pdf_bytes, media_type='application/pdf')
    response.headers["Content-Disposition"] = f'inline; filename="{_display_filename(filename)}"'
    response.headers["Cache-Control"] = "private, max-age=60"
    return response


@app.get("/api/knowledge/files/{filename}/pdf-data")
def get_knowledge_pdf_data(request: Request, filename: str, user=Depends(require_role("admin", "employee"))):
    """Return PDF bytes as base64 for reliable in-browser rendering."""
    assets_dir = Path(__file__).resolve().parent.parent / 'backend' / 'assets'
    file_path = assets_dir / filename

    try:
        file_path = file_path.resolve()
        if not str(file_path).startswith(str(assets_dir.resolve())):
            raise HTTPException(status_code=403, detail="Access denied")
    except Exception:
        raise HTTPException(status_code=404, detail="File not found")

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    if file_path.suffix.lower() != '.pdf':
        raise HTTPException(status_code=400, detail="PDF data endpoint only supports PDF files")

    pdf_bytes = file_path.read_bytes()
    return {
        "filename": filename,
        "display_name": _display_filename(filename),
        "bytes_b64": base64.b64encode(pdf_bytes).decode("ascii"),
    }


@app.put("/api/knowledge/files/{filename}")
async def update_knowledge_file(request: Request, filename: str, user=Depends(require_login("admin"))):
    """Update the content of a knowledge base file (text files only)."""
    verify_csrf(request)
    
    assets_dir = Path(__file__).resolve().parent.parent / 'backend' / 'assets'
    file_path = assets_dir / filename
    
    # Security check
    try:
        file_path = file_path.resolve()
        if not str(file_path).startswith(str(assets_dir.resolve())):
            raise HTTPException(status_code=403, detail="Access denied")
    except Exception:
        raise HTTPException(status_code=404, detail="File not found")
    
    if file_path.suffix.lower() != '.txt':
        raise HTTPException(status_code=400, detail="Can only edit text files")
    
    data = await request.json()
    content = data.get("content", "")
    
    try:
        file_path.write_text(content, encoding='utf-8')
        _PDF_TEXT_CACHE.pop(str(file_path), None)
        
        # Re-index the document in the knowledge base
        if add_document:
            doc_id = f"upload_{uuid.uuid4().hex[:8]}_{filename}"
            metadata = {"source": "edited", "filename": filename}
            add_document(doc_id=doc_id, text=content, metadata=metadata)
        
        return {"status": "updated", "filename": filename}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update file: {str(e)}")


@app.delete("/api/knowledge/files/{filename}")
async def delete_knowledge_file(request: Request, filename: str, user=Depends(require_login("admin"))):
    """Delete a knowledge base file: remove the physical file AND purge all
    ChromaDB chunks so the content is gone from the entire system immediately."""
    verify_csrf(request)

    assets_dir = Path(__file__).resolve().parent.parent / 'backend' / 'assets'
    file_path = assets_dir / filename

    # Security check
    try:
        file_path = file_path.resolve()
        if not str(file_path).startswith(str(assets_dir.resolve())):
            raise HTTPException(status_code=403, detail="Access denied")
    except Exception:
        raise HTTPException(status_code=404, detail="File not found")

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    # ---- 1. Delete the physical file ----
    try:
        file_path.unlink()
        _PDF_TEXT_CACHE.pop(str(file_path), None)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete file: {str(e)}")

    # ---- 2. Purge all ChromaDB chunks directly (no auth issues) ----
    chunks_deleted = 0
    try:
        import sys as _sys
        _sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from backend.knowledge_base import delete_documents_with_prefix, delete_documents_by_filename
        chunks_deleted += delete_documents_with_prefix(filename)
        chunks_deleted += delete_documents_by_filename(filename)
        # Also try with upload_ prefix variants
        chunks_deleted += delete_documents_with_prefix(f"upload_{filename}")
        chunks_deleted += delete_documents_by_filename(f"upload_{filename}")
    except Exception as e:
        import logging as _logging
        _logging.getLogger(__name__).warning(
            f"delete_knowledge_file: ChromaDB purge failed for '{filename}': {e}"
        )

    # ---- 3. Flush Ollama KV cache so stale answers are evicted ----
    try:
        import aiohttp as _aiohttp
        async with _aiohttp.ClientSession() as _sess:
            async with _sess.post(
                "http://127.0.0.1:11434/api/generate",
                json={"model": "qwen2.5:3b", "keep_alive": 0},
                timeout=_aiohttp.ClientTimeout(total=10)
            ) as _r:
                pass
    except Exception:
        pass  # Ollama may not be running; non-fatal

    return {"status": "deleted", "filename": filename, "chunks_deleted": chunks_deleted}


@app.post("/api/knowledge/clear-cache")
async def proxy_clear_cache(request: Request, user=Depends(require_login("admin"))):
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
                timeout=_aiohttp.ClientTimeout(total=15)
            ) as resp:
                data = await resp.json()
                return data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Cache clear failed: {str(e)}")


@app.get('/frontend/{path:path}')
def serve_frontend(path: str, request: Request, user=Depends(require_login())):
    """Serve files from the project's frontend directory but only to authenticated users.
    Protects the frontend when accessed via HTTP so anonymous visitors cannot load index.html.
    """
    # Compute frontend directory relative to repository root
    repo_root = Path(__file__).resolve().parent.parent
    frontend_dir = repo_root / 'frontend'
    # Default to index.html when path is empty or a directory
    if not path or path.endswith('/'):
        target = frontend_dir / 'index.html'
    else:
        target = frontend_dir / path


    try:
        target_resolved = target.resolve()
    except Exception:
        raise HTTPException(status_code=404, detail="Not Found")


    # Prevent directory traversal: ensure the resolved path is inside frontend_dir
    try:
        if frontend_dir.resolve() not in target_resolved.parents and frontend_dir.resolve() != target_resolved:
            raise HTTPException(status_code=404, detail="Not Found")
    except Exception:
        raise HTTPException(status_code=404, detail="Not Found")


    if not target_resolved.exists() or not target_resolved.is_file():
        raise HTTPException(status_code=404, detail="Not Found")

    # Add cache-busting headers to prevent browser from caching old versions
    return FileResponse(
        str(target_resolved),
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    )


# ========== FORGOT PASSWORD ROUTES ==========

@app.get("/forgot-password", response_class=HTMLResponse)
async def forgot_password_page(request: Request):
    """Show the forgot password page."""
    return templates.TemplateResponse("forgot_password.html", {
        "request": request
    })


@app.post("/forgot-password")
async def forgot_password_submit(request: Request, email: str = Form(...)):
    """Handle forgot password request - send OTP to email."""
    # Rate limiting - 3 attempts per minute per IP
    client_ip = request.client.host
    if not check_rate_limit(f"forgot_password:{client_ip}", RATE_LIMIT_OTP, 60):
        return templates.TemplateResponse("forgot_password.html", {
            "request": request,
            "error": "rate_limit"
        })
    
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
        return templates.TemplateResponse("forgot_password.html", {
            "request": request,
            "error": "rate_limit"
        })
    
    # Check if email exists
    c.execute("SELECT username FROM users WHERE email = ?", (email,))
    row = c.fetchone()
    
    if not row:
        conn.close()
        return templates.TemplateResponse("forgot_password.html", {
            "request": request,
            "error": "email_not_found"
        })
    
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
    return RedirectResponse(url=f"/reset-password?email={email}", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/reset-password", response_class=HTMLResponse)
async def reset_password_page(request: Request, email: str):
    """Show the reset password page."""
    return templates.TemplateResponse("reset_password.html", {
        "request": request,
        "email": email
    })


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
        return templates.TemplateResponse("reset_password.html", {
            "request": request,
            "email": email,
            "error": "password_mismatch"
        })
    
    # Check password strength
    if len(new_password) < 8:
        return templates.TemplateResponse("reset_password.html", {
            "request": request,
            "email": email,
            "error": "weak_password"
        })
    
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
        return templates.TemplateResponse("reset_password.html", {
            "request": request,
            "email": email,
            "error": "invalid_otp"
        })
    
    # Find matching OTP hash
    otp_id = None
    for row_id, stored_hash, expires_at_str, verified, purpose in rows:
        if verify_otp_hash(otp_code, stored_hash):
            # Check expiration
            expires_at = datetime.fromisoformat(expires_at_str)
            if datetime.now() > expires_at:
                conn.close()
                return templates.TemplateResponse("reset_password.html", {
                    "request": request,
                    "email": email,
                    "error": "invalid_otp"
                })
            otp_id = row_id
            break
    
    if not otp_id:
        conn.close()
        return templates.TemplateResponse("reset_password.html", {
            "request": request,
            "email": email,
            "error": "invalid_otp"
        })
    
    # Mark OTP as verified
    c.execute("UPDATE otp_verification SET verified = 1 WHERE id = ?", (otp_id,))
    
    # Update password
    password_hash = pwd_context.hash(new_password)
    c.execute("UPDATE users SET password_hash = ? WHERE email = ?", (password_hash, email))
    conn.commit()
    conn.close()
    
    # Redirect to login with success message
    return RedirectResponse(url="/login?password_reset=success", status_code=status.HTTP_303_SEE_OTHER)


# ========== PROFILE MANAGEMENT ROUTES ==========

@app.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request, user=Depends(require_login())):
    """Show the profile management page."""
    username = user['username']
    role = user['role']
    
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT username, email, role, full_name FROM users WHERE username = ?", (username,))
    row = c.fetchone()
    conn.close()
    
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Determine back URL based on role
    back_urls = {
        'admin': '/admin',
        'employee': '/employee',
        'customer': '/main'
    }
    back_url = back_urls.get(role, '/main')
    
    return templates.TemplateResponse("profile.html", {
        "request": request,
        "user": {
            "username": row[0],
            "email": row[1],
            "role": row[2],
            "full_name": row[3]
        },
        "back_url": back_url
    })


@app.post("/profile/change-email")
async def change_email_request(
    request: Request,
    new_email: str = Form(...),
    current_password: str = Form(...),
    user=Depends(require_login())
):
    """Request email change - verify password and send OTP to new email."""
    username = user['username']
    
    conn = get_db()
    c = conn.cursor()
    
    # Verify current password
    c.execute("SELECT password_hash, email FROM users WHERE username = ?", (username,))
    row = c.fetchone()
    
    if not row or not pwd_context.verify(current_password, row[0]):
        conn.close()
        role = user['role']
        back_urls = {'admin': '/admin', 'employee': '/employee', 'customer': '/main'}
        back_url = back_urls.get(role, '/main')
        
        c2 = get_db().cursor()
        c2.execute("SELECT username, email, role, full_name FROM users WHERE username = ?", (username,))
        user_row = c2.fetchone()
        
        return templates.TemplateResponse("profile.html", {
            "request": request,
            "user": {
                "username": user_row[0],
                "email": user_row[1],
                "role": user_row[2],
                "full_name": user_row[3]
            },
            "back_url": back_url,
            "error": "invalid_password"
        })
    
    current_email = row[1]
    
    # Check if new email is already taken
    c.execute("SELECT username FROM users WHERE email = ? AND username != ?", (new_email, username))
    if c.fetchone():
        conn.close()
        role = user['role']
        back_urls = {'admin': '/admin', 'employee': '/employee', 'customer': '/main'}
        back_url = back_urls.get(role, '/main')
        
        c2 = get_db().cursor()
        c2.execute("SELECT username, email, role, full_name FROM users WHERE username = ?", (username,))
        user_row = c2.fetchone()
        
        return templates.TemplateResponse("profile.html", {
            "request": request,
            "user": {
                "username": user_row[0],
                "email": user_row[1],
                "role": user_row[2],
                "full_name": user_row[3]
            },
            "back_url": back_url,
            "error": "email_taken"
        })
    
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
    return RedirectResponse(url=f"/profile/verify-email-change?new_email={new_email}", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/profile/verify-email-change", response_class=HTMLResponse)
async def verify_email_change_page(request: Request, new_email: str, user=Depends(require_login())):
    """Show the email change verification page."""
    return templates.TemplateResponse("verify_email_change.html", {
        "request": request,
        "new_email": new_email
    })


@app.post("/profile/verify-email-change")
async def verify_email_change_submit(
    request: Request,
    new_email: str = Form(...),
    otp_code: str = Form(...),
    user=Depends(require_login())
):
    """Verify OTP and update email."""
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
        return templates.TemplateResponse("verify_email_change.html", {
            "request": request,
            "new_email": new_email,
            "error": "invalid_otp"
        })
    
    # Find matching OTP hash
    otp_id = None
    for row_id, stored_hash, expires_at_str, verified, purpose in rows:
        if verify_otp_hash(otp_code, stored_hash):
            # Check expiration
            expires_at = datetime.fromisoformat(expires_at_str)
            if datetime.now() > expires_at:
                conn.close()
                return templates.TemplateResponse("verify_email_change.html", {
                    "request": request,
                    "new_email": new_email,
                    "error": "invalid_otp"
                })
            otp_id = row_id
            break
    
    if not otp_id:
        conn.close()
        return templates.TemplateResponse("verify_email_change.html", {
            "request": request,
            "new_email": new_email,
            "error": "invalid_otp"
        })
    
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
    return RedirectResponse(url="/profile?email_changed=success", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/profile/change-password")
async def change_password_request(
    request: Request,
    old_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    user=Depends(require_login())
):
    """Request password change - verify old password and send OTP."""
    username = user['username']
    
    # Check passwords match
    if new_password != confirm_password:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT username, email, role, full_name FROM users WHERE username = ?", (username,))
        user_row = c.fetchone()
        conn.close()
        
        role = user['role']
        back_urls = {'admin': '/admin', 'employee': '/employee', 'customer': '/main'}
        back_url = back_urls.get(role, '/main')
        
        return templates.TemplateResponse("profile.html", {
            "request": request,
            "user": {
                "username": user_row[0],
                "email": user_row[1],
                "role": user_row[2],
                "full_name": user_row[3]
            },
            "back_url": back_url,
            "error": "password_mismatch"
        })
    
    # Check password strength
    if len(new_password) < 8:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT username, email, role, full_name FROM users WHERE username = ?", (username,))
        user_row = c.fetchone()
        conn.close()
        
        role = user['role']
        back_urls = {'admin': '/admin', 'employee': '/employee', 'customer': '/main'}
        back_url = back_urls.get(role, '/main')
        
        return templates.TemplateResponse("profile.html", {
            "request": request,
            "user": {
                "username": user_row[0],
                "email": user_row[1],
                "role": user_row[2],
                "full_name": user_row[3]
            },
            "back_url": back_url,
            "error": "weak_password"
        })
    
    conn = get_db()
    c = conn.cursor()
    
    # Verify old password
    c.execute("SELECT password_hash, email FROM users WHERE username = ?", (username,))
    row = c.fetchone()
    
    if not row or not pwd_context.verify(old_password, row[0]):
        conn.close()
        
        c2 = get_db().cursor()
        c2.execute("SELECT username, email, role, full_name FROM users WHERE username = ?", (username,))
        user_row = c2.fetchone()
        
        role = user['role']
        back_urls = {'admin': '/admin', 'employee': '/employee', 'customer': '/main'}
        back_url = back_urls.get(role, '/main')
        
        return templates.TemplateResponse("profile.html", {
            "request": request,
            "user": {
                "username": user_row[0],
                "email": user_row[1],
                "role": user_row[2],
                "full_name": user_row[3]
            },
            "back_url": back_url,
            "error": "invalid_old_password"
        })
    
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
    return RedirectResponse(url="/profile/verify-password-change", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/profile/verify-password-change", response_class=HTMLResponse)
async def verify_password_change_page(request: Request, user=Depends(require_login())):
    """Show the password change verification page."""
    return templates.TemplateResponse("verify_password_change.html", {
        "request": request
    })


@app.post("/profile/verify-password-change")
async def verify_password_change_submit(
    request: Request,
    otp_code: str = Form(...),
    user=Depends(require_login())
):
    """Verify OTP and update password."""
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
        return templates.TemplateResponse("verify_password_change.html", {
            "request": request,
            "error": "invalid_otp"
        })
    
    # Find matching OTP hash
    otp_id = None
    new_password_hash = None
    for row_id, stored_hash, expires_at_str, verified, purpose, temp_pwd_hash in rows:
        if verify_otp_hash(otp_code, stored_hash):
            # Check expiration
            expires_at = datetime.fromisoformat(expires_at_str)
            if datetime.now() > expires_at:
                conn.close()
                return templates.TemplateResponse("verify_password_change.html", {
                    "request": request,
                    "error": "invalid_otp"
                })
            otp_id = row_id
            new_password_hash = temp_pwd_hash
            break
    
    if not otp_id:
        conn.close()
        return templates.TemplateResponse("verify_password_change.html", {
            "request": request,
            "error": "invalid_otp"
        })
    
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
    return RedirectResponse(url="/profile?password_changed=success", status_code=status.HTTP_303_SEE_OTHER)


@app.websocket("/ws")
async def websocket_proxy(websocket: WebSocket):
    """Proxy a websocket connection from the browser (same-origin on the login server)
    to the backend RAG server websocket. This allows the frontend served from the
    login server to open a single-origin websocket while the actual voice/LLM
    processing runs on the RAG server.
    """
    # Accept the incoming client websocket first
    await websocket.accept()

    # Simple session check: ensure the client has a valid session cookie
    token = websocket.cookies.get(SESSION_COOKIE)
    user = None
    if token:
        try:
            user = serializer.loads(token)
        except Exception:
            user = None

    if not user:
        # Reject unauthorized websocket clients
        log_security_event("websocket_unauthorized", {
            "client_ip": websocket.client.host if websocket.client else "unknown"
        }, severity="WARNING")
        await websocket.close(code=1008)
        return
    
    # Create rate limiter for this connection
    rate_limiter = WebSocketRateLimiter(max_messages=20, window_seconds=60)
    
    log_security_event("websocket_connected", {
        "username": user.get("username"),
        "role": user.get("role")
    })

    # Open a websocket client connection to the RAG server and bridge messages
    try:
        async with aiohttp.ClientSession() as session:
            # Try to connect to the RAG server with a few retries/backoff to tolerate
            # the backend booting slightly slower than the proxy.
            backend_ws = None
            max_attempts = 5
            for attempt in range(1, max_attempts + 1):
                try:
                    backend_ws = await session.ws_connect(RAG_WS_URL, timeout=3)
                    break
                except Exception as e:
                    # Log and retry with a small backoff
                    logger = globals().get('logger')
                    msg = f"Attempt {attempt}/{max_attempts} failed connecting to RAG ws: {e}"
                    if logger:
                        logger.warning(msg)
                    else:
                        print(msg)
                    if attempt < max_attempts:
                        await asyncio.sleep(0.6 * attempt)
                    else:
                        raise
            # Ensure we have a websocket to the backend
            if backend_ws is None:
                raise RuntimeError("Failed to establish backend websocket")
            # Use the connected websocket as an async context manager
            async with backend_ws:


                # Send an initial auth handshake to the backend (non-blocking)
                try:
                    await backend_ws.send_json({"type": "auth", "user": user})
                except Exception:
                    # backend may not expect JSON auth; ignore failures
                    pass


                # Proxy messages in both directions until one closes
                async def forward_client_to_backend():
                    try:
                        while True:
                            data = await websocket.receive()
                            
                            # Rate limiting check - only for text messages, not binary audio
                            if "text" in data:
                                if not rate_limiter.is_allowed():
                                    remaining = rate_limiter.get_remaining_time()
                                    log_security_event("websocket_rate_limit", {
                                        "username": user.get("username"),
                                        "remaining_seconds": remaining
                                    }, severity="WARNING")
                                    await websocket.send_json({
                                        "error": f"Rate limit exceeded. Please slow down. Try again in {remaining}s."
                                    })
                                    continue
                                await backend_ws.send_str(data["text"])
                            elif "bytes" in data:
                                # Binary audio data - no rate limiting to allow continuous voice recording
                                await backend_ws.send_bytes(data["bytes"])
                            elif data.get("type") == "websocket.disconnect":
                                await backend_ws.close()
                                break
                    except Exception:
                        try:
                            await backend_ws.close()
                        except Exception:
                            pass

                async def forward_backend_to_client():
                    try:
                        async for msg in backend_ws:
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                await websocket.send_text(msg.data)
                            elif msg.type == aiohttp.WSMsgType.BINARY:
                                await websocket.send_bytes(msg.data)
                            elif msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED):
                                await websocket.close(code=1000)
                                break
                    except Exception:
                        try:
                            await websocket.close(code=1000)
                        except Exception:
                            pass

                # Run both forwarding tasks concurrently
                await asyncio.gather(
                    forward_client_to_backend(),
                    forward_backend_to_client(),
                )
    except Exception as e:
        logger.error(f"Websocket proxy error: {e}")
        try:
            await websocket.close(code=1011)
        except Exception:
            pass
    return websocket


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
    
    # Generate ticket number
    ticket_number = generate_ticket_number()
    
    # Assign to employee by default (or leave unassigned)
    assigned_to_role = "employee"
    
    # Create ticket
    c.execute("""
        INSERT INTO support_tickets 
        (ticket_number, customer_id, customer_username, subject, description, status, priority, assigned_to_role)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (ticket_number, customer_id, user.get("username"), subject, description, "open", priority, assigned_to_role))
    
    ticket_id = c.lastrowid
    
    # Link feedback if provided
    if feedback_id:
        c.execute("UPDATE query_feedback SET ticket_created=1, ticket_id=? WHERE id=?", (ticket_id, feedback_id))
    
    # Add initial message
    c.execute("""
        INSERT INTO ticket_messages (ticket_id, sender_username, sender_role, message)
        VALUES (?, ?, ?, ?)
    """, (ticket_id, user.get("username"), user.get("role"), description))
    
    # Notify all employees
    c.execute("SELECT username FROM users WHERE role='employee' AND active=1")
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
        # Employees see tickets assigned to them or unassigned (not escalated to admin only)
        c.execute("""
            SELECT id, ticket_number, subject, description, status, priority,
                   customer_username, assigned_to, created_at, updated_at, escalated_to_admin
            FROM support_tickets
            WHERE (assigned_to_role='employee' OR assigned_to IS NULL OR assigned_to=?) 
              AND escalated_to_admin=0
            ORDER BY 
                CASE priority 
                    WHEN 'urgent' THEN 1
                    WHEN 'high' THEN 2
                    WHEN 'normal' THEN 3
                    WHEN 'low' THEN 4
                END,
                created_at DESC
        """, (user.get("username"),))
    elif user.get("role") == "admin":
        # Admins see all tickets
        c.execute("""
            SELECT id, ticket_number, subject, description, status, priority,
                   customer_username, assigned_to, assigned_to_role, created_at, updated_at, escalated_to_admin
            FROM support_tickets
            ORDER BY 
                CASE WHEN escalated_to_admin=1 THEN 0 ELSE 1 END,
                CASE priority 
                    WHEN 'urgent' THEN 1
                    WHEN 'high' THEN 2
                    WHEN 'normal' THEN 3
                    WHEN 'low' THEN 4
                END,
                created_at DESC
        """)
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
               resolved_at, escalated_to_admin, resolution_notes
        FROM support_tickets
        WHERE id=?
    """, (ticket_id,))
    
    ticket_row = c.fetchone()
    if not ticket_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Ticket not found")
    
    # Verify access
    if user.get("role") == "customer" and ticket_row[3] != user.get("username"):
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
    c.execute("SELECT customer_username, assigned_to, status FROM support_tickets WHERE id=?", (ticket_id,))
    ticket_row = c.fetchone()
    if not ticket_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Ticket not found")
    
    customer_username, assigned_to, status = ticket_row
    
    # Verify access
    if user.get("role") == "customer" and customer_username != user.get("username"):
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
async def assign_ticket(ticket_id: int, request: Request, user=Depends(require_role("admin", "employee"))):
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
async def resolve_ticket(ticket_id: int, request: Request, user=Depends(require_role("admin", "employee"))):
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
def get_admin_support_summary(request: Request, user=Depends(require_role("admin"))):
    """Get support ticket summary for admin dashboard"""
    conn = get_db()
    c = conn.cursor()
    
    # Total tickets
    c.execute("SELECT COUNT(*) FROM support_tickets")
    total_tickets = c.fetchone()[0]
    
    # Open tickets
    c.execute("SELECT COUNT(*) FROM support_tickets WHERE status='open'")
    open_tickets = c.fetchone()[0]
    
    # Escalated tickets
    c.execute("SELECT COUNT(*) FROM support_tickets WHERE escalated_to_admin=1 AND status!='resolved'")
    escalated_tickets = c.fetchone()[0]
    
    # Resolved today
    c.execute("SELECT COUNT(*) FROM support_tickets WHERE DATE(resolved_at)=DATE('now')")
    resolved_today = c.fetchone()[0]
    
    # Tickets by priority
    c.execute("""
        SELECT priority, COUNT(*) FROM support_tickets 
        WHERE status!='resolved'
        GROUP BY priority
    """)
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


# ========== EMPLOYEE ROUTES ==========

@app.get("/employee", response_class=HTMLResponse)
def employee_dashboard(request: Request, user=Depends(require_role("admin", "employee"))):
    """Employee dashboard"""
    return templates.TemplateResponse("employee.html", {"request": request, "user": user})


@app.get("/employee/tickets", response_class=HTMLResponse)
def employee_tickets_page(request: Request, user=Depends(require_role("admin", "employee"))):
    """Employee support tickets page"""
    return templates.TemplateResponse("employee_tickets.html", {"request": request, "user": user})


# ========== ADMIN ROUTES ==========

@app.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request, user=Depends(require_role("admin"))):
    """Admin dashboard page"""
    return templates.TemplateResponse("admin.html", {"request": request, "user": user})


@app.get("/admin/tickets", response_class=HTMLResponse)
def admin_tickets_page(request: Request, user=Depends(require_role("admin"))):
    """Admin support tickets management page"""
    return templates.TemplateResponse("admin_tickets.html", {"request": request, "user": user})




@app.get("/internal/check_rag_ws")
async def internal_check_rag_ws():
    """Lightweight endpoint to check whether the login server can connect to the
    RAG server websocket. Returns JSON with status and any exception text.
    """
    try:
        import aiohttp
        timeout = aiohttp.ClientTimeout(total=3)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.ws_connect(RAG_WS_URL) as ws:
                # send a ping and await pong/close
                await ws.send_json({"type": "ping"})
                try:
                    msg = await ws.receive(timeout=2)
                    return {"ok": True, "backend_msg_type": getattr(msg, 'type', str(type(msg)))}
                except Exception as e:
                    return {"ok": True, "note": "connected but no immediate response", "detail": str(e)}
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        return {"ok": False, "error": str(e), "trace": tb}
