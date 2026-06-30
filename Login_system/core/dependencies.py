"""Dependency providers (composition root) for the login system.

Phase 5 of the architectural refactor introduces a single place to resolve the
extracted repositories/services so routers can consume them via FastAPI's
``Depends``. Providers here import only the standalone layer modules (never the
server module), so wiring them into routes never creates an import cycle.

Behavior is unchanged: providers return the same connection factory / service
singletons the monolith already used.
"""
from Login_system.repositories.db import get_db as _get_db
from Login_system.services import otp_service as _otp_service


def get_db_connection():
    """Yield a users-DB connection and guarantee it is closed afterwards.

    Suitable for use as a FastAPI ``Depends`` provider. Existing handlers that
    open/close their own connection are unaffected; this is opt-in.
    """
    conn = _get_db()
    try:
        yield conn
    finally:
        conn.close()


def get_otp_service():
    """Provide the OTP persistence/email service."""
    return _otp_service
