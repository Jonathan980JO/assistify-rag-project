"""Chroma collection mutation lock for the RAG backend.

Extracted from ``assistify_rag_server.py`` during the Phase 8G refactor. Owns
the single asyncio lock that serializes all ChromaDB mutations so concurrent
uploads/deletes/reindexes can never corrupt a collection mid-write.

The ``_collection_mutation`` async context manager stays in the server module
because it also drives the KB pipeline watchdog; it acquires the lock returned
by ``_get_collection_mutation_lock`` defined here.

This module never imports ``assistify_rag_server`` (avoids an import cycle).
"""
import asyncio
import logging

logger = logging.getLogger("Assistify")

_collection_mutation_lock_holder: dict[str, asyncio.Lock] = {"lock": asyncio.Lock()}


def _get_collection_mutation_lock() -> asyncio.Lock:
    return _collection_mutation_lock_holder["lock"]


def _reset_collection_mutation_lock() -> None:
    _collection_mutation_lock_holder["lock"] = asyncio.Lock()
    logger.warning("[KB LOCK] collection mutation lock reset")
