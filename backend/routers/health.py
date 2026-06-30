"""Health/stats routes for the RAG backend.

Extracted from ``assistify_rag_server.py`` during the Phase 4 refactor.

These handlers read live server state (loaded models, ASSETS_DIR, the in-memory
conversation map, get_stats). To keep behavior byte-identical and avoid an
import cycle with the server module, the router is built by a factory that
receives the live server module and reads attributes from it at request time.
Paths, methods, and response bodies are unchanged.
"""
from fastapi import APIRouter, Depends


def build_health_router(server) -> APIRouter:
    """Build the /health and /stats router bound to the live server module."""
    router = APIRouter()

    def get_server():
        """Dependency provider for the live server module (Phase 5 DI)."""
        return server

    @router.get("/health")
    async def health(srv=Depends(get_server)):
        stats = srv.get_stats()
        return {
            "status": "healthy",
            "services": {
                "asr": srv.whisper_model is not None,
                "tts": srv.xtts_model is not None,
                "llm": "connected",
                "database": True,
                "knowledge_base": True,
                "assets": srv.ASSETS_DIR.exists()
            },
            "stats": stats
        }

    @router.get("/stats")
    async def statistics(srv=Depends(get_server)):
        stats = srv.get_stats()
        return {
            "database": stats,
            "active_connections": len(srv.conversation_history),
            "knowledge_base": "ChromaDB"
        }

    return router
