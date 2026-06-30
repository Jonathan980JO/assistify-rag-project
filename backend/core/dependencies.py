"""Dependency providers (composition root) for the RAG backend.

Phase 5 of the architectural refactor introduces a single place to resolve the
extracted repositories/services so routers can consume them via FastAPI's
``Depends``. Providers here import only the standalone layer modules (never the
server module), so wiring them into routes never creates an import cycle.

Behavior is unchanged: providers return the same module-level singletons the
monolith already used.
"""
from backend.repositories import conversation_repository as _conversation_repository
from backend.services import language_service as _language_service


def get_conversation_repository():
    """Provide the conversation persistence repository."""
    return _conversation_repository


def get_language_service():
    """Provide the language-resolution service."""
    return _language_service
