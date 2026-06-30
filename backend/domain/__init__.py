"""Domain models / dataclasses for the RAG backend.

Layer: domain (the "models" layer in the target architecture).

NOTE: This layer is named ``domain`` rather than ``models`` on purpose. A
pre-existing ``backend/Models`` directory holds multi-gigabyte ML model
weights (faster-whisper, Qwen, etc.) and is git-ignored. On case-insensitive
filesystems (Windows) a ``backend/models`` Python package cannot coexist with
that directory, so the domain-model layer uses ``backend/domain`` instead.

Populated during the architectural refactor; empty in Phase 0.
"""
