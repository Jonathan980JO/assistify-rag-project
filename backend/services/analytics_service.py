"""Thin analytics service for the RAG backend.

Extracted during the Phase 8F refactor. Provides a single import surface that
wraps :mod:`backend.analytics` for the analytics routes, so the router does not
reach into the analytics module directly. Behavior is unchanged — these are the
same functions the monolith called inline.

This module never imports ``assistify_rag_server`` (avoids an import cycle).
"""
from backend.analytics import (
    get_comprehensive_analytics,
    log_satisfaction,
)

__all__ = ["get_comprehensive_analytics", "log_satisfaction"]
