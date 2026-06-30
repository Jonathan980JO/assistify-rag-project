"""
HTTP security middleware and helpers for the RAG server.

Extracted from assistify_rag_server.py as the first step toward modularizing
the monolith without changing runtime behavior.
"""
from __future__ import annotations

from typing import Iterable, List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware


def _normalize_origin(url: str) -> str:
    return (url or "").strip().rstrip("/")


def rag_allowed_origins(base_url: str, extra: Optional[Iterable[str]] = None) -> List[str]:
    """Origins permitted to call the RAG API from a browser (login server only)."""
    origins = {
        _normalize_origin(base_url),
        "http://127.0.0.1:7001",
        "http://localhost:7001",
    }
    if extra:
        for item in extra:
            normalized = _normalize_origin(item)
            if normalized:
                origins.add(normalized)
    return sorted(o for o in origins if o)


def configure_rag_http_security(
    app: FastAPI,
    *,
    session_secret: str,
    development: bool,
    base_url: str,
    allowed_hosts: Optional[List[str]] = None,
) -> None:
    """Apply CORS, session, and trusted-host middleware to the RAG app."""
    hosts = allowed_hosts or ["localhost", "127.0.0.1"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=rag_allowed_origins(base_url),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )
    app.add_middleware(
        SessionMiddleware,
        secret_key=session_secret,
        https_only=(not development),
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=hosts)


def verify_csrf(request: Request) -> None:
    csrf_header = request.headers.get("x-csrf-token")
    csrf_cookie = request.cookies.get("csrf_token")
    if not csrf_cookie or csrf_header != csrf_cookie:
        raise HTTPException(status_code=403, detail="CSRF token missing or invalid")
