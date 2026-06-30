# Assistify System Evaluation Report

**Date:** June 21, 2026  
**Scope:** Full-stack component review — security, correctness, performance, architecture, reliability  
**Status:** Findings documented; enhancements tracked in implementation backlog below

---

## Executive Summary

Assistify is a multi-process local stack: **Login (7001)**, **RAG + voice (7000)**, **Ollama (11434)**, **Piper TTS (5002)**, optional **LLM shim (8010)**. The system is functionally rich (multi-tenant RBAC, dual-corpus RAG, voice EN/AR, tickets, analytics) but carries **production blockers** in session persistence, RAG CORS policy, and several config/integration drifts.

| Area | Grade | Top risk |
|------|-------|----------|
| Security | C+ | RAG CORS `*` + credentials; dev login fallback |
| Correctness | B- | Chroma path drift; tenant analytics leak |
| Performance | B | Single-GPU voice/LLM queue without user feedback |
| Architecture | C | 43k-line RAG monolith; duplicate routes |
| Reliability | B- | SQLite-backed session invalidation/rate-limits; single-GPU inference queue |

---

## System Topology

```
Browser (:7001)
    → Login_server (auth, RBAC, proxy)
        → RAG_server (:7000) → Ollama, Piper, ChromaDB
```

**Trust contract:** Login signs session cookies (`SESSION_SECRET`); RAG validates the same cookie. Tenant scope travels in cookie payload (`tenant_id`, `active_tenant_id`).

---

## Component Evaluations

### 1. Login Server (`Login_system/login_server.py`)

**Verdict:** Feature-complete gateway; operationally fragile.

| Dimension | Finding | Severity |
|-----------|---------|----------|
| Security | bcrypt_sha256, CSRF, rate limits, lockout, CSP headers, RBAC hierarchy | Strength |
| Security | `password == username` dev fallback when `IS_PRODUCTION=false` | P1 |
| Security | Session id rotation on login exists (invalidates prior cookie) | Partial fix |
| Reliability | Sessions, invalidation, rate limits, lockouts in RAM | **P0** |
| Correctness | `/api/employee/analytics` counts all customers globally | P2 |
| Architecture | Duplicate `/admin`, `/employee` route blocks (~2003 vs ~5783) | P2 |

**Key symbols:** `create_session_token`, `validate_session`, `auth_user`, `_tenant_scope_sql`, `init_db`

---

### 2. RAG + Voice Server (`backend/assistify_rag_server.py`)

**Verdict:** Powerful engine trapped in a monolith.

| Dimension | Finding | Severity |
|-----------|---------|----------|
| Security | `allow_origins=["*"]` + `allow_credentials=True` (line ~8217) | **P0** |
| Security | CSRF only on `/upload_rag`, `/rag/update` — missing on delete/reindex | P1 |
| Correctness | `CryptContext` uses `pbkdf2_sha256`; Login uses `bcrypt_sha256` | P1 |
| Architecture | ~43,000 lines mixing RAG, routes, Arabic, lifecycle | P2 |
| Config | Hardcoded `chroma_db_v3` vs `config.CHROMA_DB_PATH` default `chroma_db` | P2 |

**Key symbols:** `LiveRAGManager`, `call_llm_with_rag`, `require_login`, `verify_csrf`

---

### 3. Knowledge Base (`backend/knowledge_base.py`, `backend/pdf_ingestion_rag.py`)

**Verdict:** Strongest subsystem.

| Dimension | Finding | Severity |
|-----------|---------|----------|
| Performance | E5 embeddings + cross-encoder rerank + structural boosting | Strength |
| Reliability | Chroma SQLite lock on concurrent uploads; no queue | P2 |
| Correctness | Two search paths: `search_documents` (threshold 1.2) vs `VectorStore.search` (1.0) | P3 |

**Authoritative path:** `LiveRAGManager.search()` → `VectorStore.search()` with `RAG_STRICT_DISTANCE_THRESHOLD` (default 1.0).

---

### 4. Voice Subsystem (`backend/voice_audio/`)

**Verdict:** Best-factored module.

| Dimension | Finding | Severity |
|-----------|---------|----------|
| Architecture | Clean stt/tts/ws split, DI via `VoiceWebSocketDeps` | Strength |
| Performance | `voice_semaphore(1)` — no queued user feedback | P1 |
| Reliability | Long utterances can overflow buffer (>30s freeze) | P2 |
| Naming | Code says "XTTS"; health check expects `engine=piper` | P3 |

---

### 5. Frontend (`frontend/index.html`)

**Verdict:** Capable SPA; XSS mostly safe.

| Dimension | Finding | Severity |
|-----------|---------|----------|
| Security | `appendMsg` uses `textContent` (safe) | Strength |
| Security | `innerHTML` only for clearing containers | Low risk |
| Maintainability | ~4,700 lines inline HTML/CSS/JS | P3 |

---

### 6. Config & Launchers (`config.py`, `scripts/`)

**Verdict:** Good ops tooling; port drift.

| Dimension | Finding | Severity |
|-----------|---------|----------|
| Ops | `preflight_check`, `verify_stack`, `verify_rbac`, split launcher | Strength |
| Config | LLM port 8000 vs 8010 across files | P2 |
| Security | Production already requires `SESSION_SECRET` ≥64 bytes | Partial |

---

## Cross-Cutting Integration Risks

1. **Cookie trust** breaks if RAG is browser-reachable cross-origin (CORS P0).
2. **Tenant isolation** enforced in most SQL but leaked in employee analytics.
3. **Chroma path drift** can cause reindex scripts to target wrong database.

---

## Enhancement Backlog (Implemented)

| ID | Priority | Enhancement | Status |
|----|----------|-------------|--------|
| report | — | This document | Done |
| p0-cors | P0 | Lock RAG CORS to login origin | Implemented |
| p0-sessions | P0 | SQLite-backed session/rate/lockout state | Implemented |
| p1-csrf-rag | P1 | CSRF on all RAG mutations | Implemented |
| p1-devfallback | P1 | Gate dev login behind `ALLOW_DEV_LOGIN_FALLBACK` | Implemented |
| p1-hashing | P1 | Unify CryptContext to bcrypt_sha256 | Implemented |
| p1-concurrency | P1 | Voice queue busy signal | Implemented |
| p2-chroma-path | P2 | Single `CHROMA_DB_PATH` source | Implemented |
| p2-tenant-analytics | P2 | Tenant-scoped employee analytics | Implemented |
| p2-dup-routes | P2 | Remove duplicate route registrations | Implemented |
| p2-llm-port | P2 | Canonical port 8010 | Implemented |
| p2-session-rotation | P2 | Session invalidation on login + audio buffer cap | Implemented |
| p2-secret-failclosed | P2 | Startup validation for production secrets | Implemented |
| p3-retrieval-docs | P3 | `docs/RAG_RETRIEVAL.md` + Piper naming note | Implemented |
| p3-monolith | P3 | Extract `backend/rag_middleware.py` | Implemented |
| p3-xss | P3 | `escapeHtml` helper + safe conversation titles | Implemented |

---

## Verification Commands

```powershell
python scripts/preflight_check.py
python scripts/verify_stack.py
python scripts/verify_rbac.py
python -m pytest tests/test_system_integrity.py -q
```

---

*End of evaluation report.*
