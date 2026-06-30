"""Analytics and admin-dashboard routes for the RAG backend.

Extracted from ``assistify_rag_server.py`` during the Phase 8F refactor.

The handlers read live server state (analytics DB path, tenant scoping, the
adaptive TTS manager) and the auth dependencies. To keep behavior
byte-identical and avoid an import cycle, the router is built by a factory that
receives the live server module and reads attributes from it at request time.
Paths, methods, and response bodies are unchanged.
"""
import sqlite3
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse

from backend.services.analytics_service import (
    get_comprehensive_analytics,
    log_satisfaction,
)


def build_analytics_router(server) -> APIRouter:
    """Build the analytics router bound to the live server module."""
    router = APIRouter()

    @router.get("/admin/analytics", response_class=HTMLResponse)
    def admin_analytics_page(request: Request, user=Depends(server.require_tenant_staff())):
        html_path = Path(server.__file__).parent / "templates" / "admin_analytics.html"
        if not html_path.exists():
            raise HTTPException(status_code=404, detail="Admin analytics template not found.")
        content = html_path.read_text(encoding="utf-8")
        return HTMLResponse(content=content)

    @router.get("/admin/errors", response_class=HTMLResponse)
    def admin_errors_page(request: Request, user=Depends(server.require_tenant_staff())):
        html_path = Path(server.__file__).parent / "templates" / "admin_errors.html"
        if not html_path.exists():
            raise HTTPException(status_code=404, detail="Admin errors template not found.")
        content = html_path.read_text(encoding="utf-8")
        return HTMLResponse(content=content)

    @router.get("/analytics/summary")
    def get_analytics_summary(tenant_id: int | None = None, user=Depends(server.require_tenant_staff())):
        """Legacy endpoint - returns basic summary (tenant-scoped)"""
        scope = server.analytics_scope_tenant(user, tenant_id)
        conn = sqlite3.connect(server.ANALYTICS_DB)
        c = conn.cursor()
        if scope is None:
            c.execute("SELECT user_role, COUNT(*) FROM usage_stats GROUP BY user_role")
        else:
            c.execute(
                "SELECT user_role, COUNT(*) FROM usage_stats WHERE tenant_id = ? GROUP BY user_role",
                (int(scope),),
            )
        data = c.fetchall()
        conn.close()
        return {"summary": data}

    @router.get("/analytics/comprehensive")
    def get_comprehensive_analytics_endpoint(days: int = 30, tenant_id: int | None = None, user=Depends(server.require_tenant_staff())):
        """New comprehensive analytics endpoint (tenant-scoped)"""
        scope = server.analytics_scope_tenant(user, tenant_id)
        return get_comprehensive_analytics(days, tenant_id=scope)

    @router.get("/analytics/tts-performance")
    def tts_performance_stats(user=Depends(server.require_tenant_staff())):
        """Real-time adaptive TTS chunk-size performance dashboard.

        Returns current tier, rolling-average first-chunk latency, recent
        per-query snapshots, and the recommended words-per-chunk / buffer.
        """
        return server.adaptive_manager.get_stats()

    @router.get("/analytics/errors")
    def get_recent_errors(tenant_id: int | None = None, user=Depends(server.require_tenant_staff())):
        scope = server.analytics_scope_tenant(user, tenant_id)
        conn = sqlite3.connect(server.ANALYTICS_DB)
        c = conn.cursor()
        if scope is None:
            c.execute("""
                SELECT timestamp, username, error_message, response_time_ms FROM usage_stats
                WHERE response_status != 'success' ORDER BY timestamp DESC LIMIT 50
            """)
        else:
            c.execute("""
                SELECT timestamp, username, error_message, response_time_ms FROM usage_stats
                WHERE response_status != 'success' AND tenant_id = ? ORDER BY timestamp DESC LIMIT 50
            """, (int(scope),))
        errors = c.fetchall()
        conn.close()
        return {"errors": [{"timestamp": e[0], "username": e[1], "error": e[2], "response_time": e[3]} for e in errors]}

    @router.post("/analytics/feedback")
    async def submit_feedback(request: Request, user=Depends(server.require_login())):
        """Allow users to submit satisfaction ratings"""
        data = await request.json()
        rating = data.get("rating")
        feedback_text = data.get("feedback")

        if not rating or rating < 1 or rating > 5:
            raise HTTPException(status_code=400, detail="Rating must be between 1 and 5")

        log_satisfaction(
            username=user.get("username"),
            user_role=user.get("role"),
            rating=rating,
            feedback_text=feedback_text,
            tenant_id=server.resolve_request_tenant(user),
        )
        return {"message": "Feedback submitted successfully"}

    return router
