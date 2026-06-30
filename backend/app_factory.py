"""Application factory for the Assistify RAG voice server.

Phase 8L: ``create_app()`` builds the FastAPI instance with the exact middleware
stack and static-assets mount that ``assistify_rag_server`` previously configured
inline. The server module calls this once and then registers its routes, event
handlers, and routers against the returned app.

Centralizing construction here gives the server a single, testable entry point
without changing any runtime behavior: the middleware classes, their order, and
their parameters are identical to the pre-refactor monolith, and the static
``/assets`` mount is unchanged.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from config import BASE_URL
from backend.config_head import ASSETS_DIR, SESSION_SECRET, DEVELOPMENT
from backend.rag_middleware import rag_allowed_origins


def create_app() -> FastAPI:
    """Construct the FastAPI app with the production middleware stack and mount.

    Middleware is added in the same order as the original monolith (CORS,
    session, trusted-host); Starlette applies middleware in reverse order of
    addition, so preserving this order preserves request-handling behavior.
    """
    app = FastAPI(title="Assistify RAG Voice Engine")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=rag_allowed_origins(BASE_URL),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )
    app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET, https_only=(not DEVELOPMENT))
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1"]
    )
    Path(ASSETS_DIR).mkdir(parents=True, exist_ok=True)
    app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")
    return app
