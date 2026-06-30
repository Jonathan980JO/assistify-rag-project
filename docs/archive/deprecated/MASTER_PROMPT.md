# ASSISTIFY — FULL PROJECT MASTER PROMPT

Use this prompt when implementing, extending, auditing, or documenting the **Assistify RAG Enterprise AI Help-Desk Platform**. Treat every requirement below as mandatory unless explicitly marked optional.

**Related docs:** [README.md](../README.md) · [SYSTEM_ARCHITECTURE.md](SYSTEM_ARCHITECTURE.md) · [SETUP_WINDOWS.md](SETUP_WINDOWS.md) · [DIAGRAMS.md](DIAGRAMS.md) · [TENANT_SELECTOR_ARCHITECTURE.md](TENANT_SELECTOR_ARCHITECTURE.md)

---

## 1. MISSION & PRODUCT DEFINITION

**Assistify** is a **multi-tenant, RAG-powered customer support platform** that answers questions **grounded in each tenant's uploaded knowledge base**, using **local LLM inference** (Ollama), **text + voice** interaction (English + Arabic), **role-based access control**, and **auditable** support workflows.

**It is NOT:**

- A generic open-domain chatbot
- A cloud-API-dependent SaaS (primary path is local inference)
- A single-tenant demo app

**It IS:**

- Document-agnostic RAG (must work for unknown future PDFs/industries)
- Multi-tenant SaaS-shaped (tenants = businesses; customers request access)
- Gateway-pattern architecture (all user traffic through Login :7001 → RAG :7000)

**Business goals:**

| Goal | Requirement |
|------|-------------|
| Accurate grounded answers | Retrieve tenant-scoped chunks before LLM; no hallucination when no evidence |
| Low cost | Local Ollama + CPU voice; TOON context format saves 40–60% tokens |
| Trust & compliance | Sessions, RBAC, tenant isolation, PII/profanity validation, security logs |
| Admin control | KB upload/reindex, analytics, audit logs, user/tenant management |
| Multimodal UX | REST text chat + WebSocket voice (STT → RAG → LLM → TTS) |

---

## 2. NON-NEGOTIABLE ENGINEERING RULES (GENERICITY)

From `.cursorrules` — **every implementation must pass the Future Document Test:**

> "Would this still work if tomorrow the system receives a completely new document from a domain that has never existed before?"

### FORBIDDEN (never implement)

- Hardcoded company names, product names, PDF names, section names
- Hardcoded metrics, percentages, dollar amounts, dates, known answers
- `if "CompanyX" in query`, `if filename == "..."`, `return "$250,000"`, etc.
- Domain-specific extractors that return canned answers without chunk evidence
- Prompt instructions that name specific corpora (e.g. "cite IBM HR report")

### REQUIRED (always implement)

- Answers derived from **retrieved chunk evidence** only
- Generic mechanisms: table parsing, column mapping, entity extraction from query, semantic retrieval, reranking, evidence validation
- Numeric answers: extract from matching sentence/row in retrieved text (verbatim or formatted from evidence)
- Before completing any RAG task, provide: **Genericity Assessment**, **Evidence-Origin Assessment**, **Future-Document Compatibility Assessment**

---

## 3. RUNTIME ARCHITECTURE

### Service topology (default ports)

| Service | Port | Role |
|---------|------|------|
| **Login Server** | `7001` | Auth, sessions, RBAC, static React UI, REST/WS **proxy** to RAG |
| **RAG Server** | `7000` | Chat orchestration, retrieval, LLM calls, voice, conversations, analytics |
| **Ollama** | `11434` | LLM inference (GPU) — default model `qwen2.5:3b` |
| **Piper TTS** | `5002` | Voice output (CPU ONNX) |
| **LLM Shim** (optional) | `8010` / `8000` | OpenAI-compatible proxy to Ollama |

```
Browser → Login (7001) → RAG (7000) → Ollama (11434, GPU)
                              ↓
                        Piper TTS (5002, CPU)
              ↑ optional LLM shim (8010)
```

**Critical rule:** All user-facing traffic enters **Login :7001** only. Login validates session, enforces RBAC, proxies to RAG.

### GPU/CPU policy

| Component | Device |
|-----------|--------|
| Ollama LLM | GPU |
| Embeddings + reranker | GPU if `RAG_USE_GPU=1` |
| faster-whisper STT | **CPU only** (preserve VRAM) |
| Piper TTS | **CPU only** |

---

## 4. REPOSITORY LAYOUT

```
assistify-rag-project-final-rag-system/
├── assistify-ui-design/     # Canonical React/Next.js UI → static export to out/
├── backend/                 # RAG server, KB, voice, chat_store, analytics
│   ├── assistify_rag_server.py   # Main orchestrator (~40k+ lines)
│   ├── knowledge_base.py           # Chunking, embedding, Chroma
│   ├── pdf_ingestion_rag.py        # VectorStore, retrieval, rerank
│   ├── rag_query_prep.py           # Query normalization
│   ├── rag_chunk_heuristics.py     # Chunk shape heuristics
│   ├── response_validator.py       # PII/profanity validation
│   ├── chat_store.py               # Normalized conversations
│   ├── tenant_access.py            # Tenant membership enforcement
│   ├── toon.py                     # TOON context encoding
│   └── voice_audio/                # STT/TTS WebSocket handler
├── Login_system/            # login_server.py, users.db, RBAC, sessions
├── tts_service/             # Piper microservice
├── scripts/                 # Launchers, migrations, eval
├── tests/                   # Unit/integration tests
├── docs/                    # Architecture, setup, DIAGRAMS.md
├── config.py                # Shared configuration
├── start_main_servers.py    # One-command launcher
└── environment_main.yml     # Conda env (assistify_main, Python 3.11)
```

**Use only `assistify-ui-design`** — folders `(1)` and `(2)` are stale duplicates.

---

## 5. TECHNOLOGY STACK

| Layer | Technology |
|-------|------------|
| Frontend | Next.js 16, React 19, TypeScript, Tailwind CSS 4 (static export) |
| API Gateway | FastAPI — `Login_system/login_server.py` |
| Orchestration | FastAPI — `backend/assistify_rag_server.py` |
| LLM | Ollama (`qwen2.5:3b` default) |
| Embeddings | `intfloat/multilingual-e5-base` (Sentence Transformers) |
| Reranker | `cross-encoder/ms-marco-MiniLM-L-6-v2` |
| Vector DB | ChromaDB persistent, cosine HNSW — `backend/chroma_db_v3` |
| Relational DB | SQLite — `users.db`, `conversations.db`, `analytics.db` |
| STT | faster-whisper (CPU int8) |
| TTS | Piper ONNX (CPU) |
| Auth | Signed session cookies, OTP (EmailJS), Google OAuth, MFA (TOTP) |

---

## 6. MULTI-TENANCY & RBAC

### Tenant model

- `tenants` table = business/company (no separate companies table)
- Columns: `id`, `name`, `slug`, `active`, `plan`, `allow_multiple_admins`
- Default tenant id=1 cannot be permanently deleted

### Role hierarchy (low → high)

`customer` < `employee` < `admin` < `master_admin` < `superadmin`

| Role | Tenant binding |
|------|----------------|
| `admin`, `master_admin`, `employee` | `users.tenant_id` = home tenant |
| `superadmin` | Platform-wide; bypasses tenant SQL filters |
| `customer` | Global user; business access via `tenant_memberships` |

### Membership flow

1. Customer `POST /api/access-requests {tenant_id}` → status `pending`
2. Admin approves → `approved`
3. Customer `POST /api/session/active-tenant` → session cookie gets `active_tenant_id`
4. Chat uses tenant-scoped RAG collection

Statuses: `pending` → `approved` | `rejected` | `revoked`

### Isolation layers

| Layer | Mechanism |
|-------|-----------|
| Vector KB | Per-tenant Chroma: `support_docs_v3_latest` (tenant 1) or `t{N}_support_docs_v3_latest` |
| File assets | `backend/assets/tenant_{id}/` |
| Conversations | `tenant_id` on `chat_messages` |
| Analytics | `tenant_id` on usage tables |
| Chat access | `tenant_access.assert_chat_tenant_allowed()` |
| Staff queries | `_tenant_scope_sql()` filters by caller tenant |

### Per-conversation tenant selector

- User picks **active tenant per conversation** (header dropdown)
- Switching tenant mid-thread does **not** create new conversation
- APIs: `GET /api/chat-tenants`, `PATCH /conversations/{id}/active-tenant`, WS `set_active_tenant`
- Storage: `chat_conversations`, `chat_conversation_state`, `chat_messages` in `chat_store.py`

### Guest chat (configurable)

- `ALLOW_PUBLIC_GUEST_CHAT` — default on in dev, off in prod
- Guest cookie `guest_id` + header `X-Guest-Owner`
- Routes: `/frontend/guest/`, `/api/guest/*`, `/ws/guest`

### Tenant lifecycle (superadmin)

- Create, activate, deactivate, permanent delete (inactive + slug confirmation)
- `tenant_lifecycle.delete_tenant_permanently()` purges KB, chat, analytics, staff users

---

## 7. END-TO-END REQUEST FLOW (TEXT CHAT)

1. React UI → `POST /query` (session cookie, tenant context)
2. Login Server → validate session + RBAC → proxy to RAG
3. RAG → bind `tenant_id`, `conversation_id`, `connection_id`
4. `prepare_query_for_rag()` — strip greetings, optional LLM normalize, spelling
5. `classify_query_route()` — smalltalk/meta bypass RAG; `document_question` uses full pipeline
6. Retrieval — `get_tenant_rag(tenant_id).search()` — embed, Chroma, rerank, hybrid gate
7. Answer path — deterministic evidence extraction OR LLM with TOON context
8. `validate_response()` — PII, profanity, grounding
9. Persist to `chat_store` + analytics
10. Return JSON to UI

### Query routes (`classify_query_route`)

| Route | Behavior |
|-------|----------|
| `conversational_ack` | Canned — no RAG |
| `assistant_meta` | Capability — no RAG |
| `smalltalk` | Smalltalk — no RAG |
| `unsupported_unclear` | Clarification — no RAG |
| `document_question` | Full RAG + LLM |

### Fact/list/generation routing

- Fact queries → evidence-driven extraction (`_extract_evidence_value_sentence`) from retrieved chunks
- List queries → list extraction or LLM with list rules
- Multi-source synthesis → `multi_source_synthesis` doc router mode when comparison/bridge/explicit multi-doc

---

## 8. RAG PIPELINE (IMPLEMENTATION DETAILS)

### Document upload

1. `POST /upload_rag` (or `/proxy/upload_rag`) — PDF/TXT, rate limit 10/min
2. Save to `assets/tenant_N/{uuid}_{filename}`
3. Background: `extract_pdf_asset_text()` → `chunk_and_add_document()` → embed → Chroma upsert
4. Sync live collection pointer; WS events on `/ws/kb-events`

### PDF extraction

- Primary: pdfplumber
- OCR fallback: pytesseract + pdf2image (page text < 100 chars)
- Secondary: PyPDF2
- Post-process: hyphenation repair, repeated heading strip, table blocks `[TABLE DATA]`

### Chunking (`knowledge_base.chunk_and_add_document`)

| Parameter | Long docs | Short (≤8000 words) |
|-----------|-----------|---------------------|
| TARGET_WORDS | 300 | 120 |
| TARGET_MIN/MAX | 220–360 | 80–160 |
| OVERLAP_WORDS | 50 | 25 |

- Structure-aware: chapter/section boundaries, prose vs table split, numbered heading repair
- Chunk IDs: `{doc_id}_chunk_{index}`
- Metadata: `section`, `title`, `chunk_role`, `page`, `source`, `tenant_id`

### Embeddings

- Model: `intfloat/multilingual-e5-base`
- Index: `passage: {text}` | Query: `query: {text}`
- Shared singleton: `get_shared_embedder()`

### Retrieval (`VectorStore.search`)

- top_k: 5–8 default, cap 120, FACT_MAX_TOP_K=20
- Distance threshold: dynamic 0.85–1.35
- Quality filter: heading-dominated, TOC, OCR garbage, number-heavy (unless structured table)
- Rerank: CrossEncoder, blend 0.7 semantic + 0.3 density
- Hybrid gate: semantic ≥ 0.18 OR keyword overlap
- Doc router: single vs multi-source synthesis based on query coverage across sources

### TOON context (`toon.py`)

- doc[0] full text; later docs truncated to 500 chars
- 40–60% token reduction vs JSON
- Joined with `\n---\n`

### Generic fact extraction (required pattern)

- `_extract_evidence_value_sentence(query, chunk)` — concept token overlap + numeric shape detection
- `_extract_minbalance_from_pipe_line` — column-mapped table read (Account / Min balance headers)
- `_table_fact_product_phrases` — from query (`for X`, Title-Case noun phrases), **no hardcoded product list**
- `_extract_metric_fact_answer` — evidence sentence from corpus, no hardcoded metrics
- Pipe-table fallback: `_collection_pipe_table_chunks()` when retrieval out-ranks table chunk

### Caching

- Rerank LRU 512, query embed LRU 256, simple RAG answers TTL 120s
- Cleared on collection hot-swap / `POST /rag/clear-cache`

### Fallbacks

| Scenario | Behavior |
|----------|----------|
| No relevant docs | Friendly not-found — **no LLM** |
| MPC11 fast-fail | Skip LLM if doc_count < 1 or max_sim < 0.25 |
| LLM timeout | User-friendly error |
| Query prep LLM down | Skip normalization silently |
| TTS down | Browser SpeechSynthesis |

---

## 9. VOICE ARCHITECTURE

```
Browser Mic (PCM16 16kHz) → WS /ws → VAD (~600ms silence)
  → faster-whisper STT (CPU) → RAG+LLM → Piper TTS (:5002)
  → WS binary PCM16 24kHz → Browser speaker
```

- WS control messages: `set_language`, `set_conversation_id`, `set_active_tenant`, `interrupt`
- Rate limit: 20 msg/min WebSocket
- Arabic: separate Whisper + Piper voices
- Memory guard: block voice after 3 consecutive suspected leaks

---

## 10. SECURITY ARCHITECTURE

| Control | Implementation |
|---------|----------------|
| Session | Signed cookie (`itsdangerous`), 24h absolute / 2h idle timeout, max 3 concurrent |
| CSRF | Cookie + `X-CSRF-Token` on mutating requests |
| Rate limiting | Per-IP SQLite buckets (login, register, OTP, guest, WS) |
| Account lockout | 5 failures → 15 min |
| Security logging | Rotating `logs/security.log` |
| HTTP headers | CSP, HSTS, X-Frame-Options, nosniff |
| Tenant enforcement | `ENFORCE_CHAT_TENANT_MEMBERSHIP` (on in prod by default) |
| Response validation | PII (SSN, credit card, non-company email/phone), profanity blocklist |
| TrustedHost | Config-driven `ALLOWED_HOSTS` |

### Production secrets (required in `.env`)

`SESSION_SECRET` (64+ bytes), `GOOGLE_CLIENT_*`, `EMAILJS_*`, `ENFORCE_HTTPS=true`

---

## 11. DATABASE DESIGN

### users.db (Login_system)

Key tables: `tenants`, `users`, `tenant_memberships`, `otp_verification`, `user_sessions`, `invalidated_sessions`, `rate_limit_buckets`, `failed_login_attempts`, `account_lockouts`, `audit_logs`, `customer_notes`, `support_tickets`, `ticket_messages`, `notifications`, `query_feedback`

### conversations.db (backend)

`chat_conversations`, `chat_conversation_state`, `chat_messages` (+ legacy tables)

### analytics.db

`usage_stats`, `satisfaction_ratings`, `model_performance`, `session_analytics`, `kb_document_versions`

### ChromaDB

`backend/chroma_db_v3` — per-tenant collections, cosine distance

---

## 12. API SURFACE (SUMMARY)

**Auth legend:** public | session | API auth | tenant staff | superadmin | CSRF | guest

### Core groups (Login :7001 unless proxied)

- **Auth:** `/login`, `/register`, `/verify-otp`, Google OAuth, password reset
- **Profile:** `/api/my-profile`, email/password change with OTP
- **Users:** CRUD, roles, MFA — `/api/users/*`
- **Tenants:** `/api/tenants/*`, memberships, access requests, active-tenant
- **Chat:** `/conversations/*`, `POST /query`, `WS /ws`, guest variants
- **Knowledge:** upload, list, delete, reindex, `kb_status`, `WS /ws/kb-events`
- **Analytics:** `/api/analytics/*`, feedback thumbs
- **Tickets:** `/api/support/ticket/*`
- **Superadmin:** tenant lifecycle, cross-tenant visibility

RAG direct endpoints on :7000 mirror some KB/chat routes for internal/proxy use.

See [README.md §12](../README.md#12-api-documentation) for the full endpoint table.

---

## 13. FRONTEND (`assistify-ui-design`)

- **Framework:** Next.js App Router, static export → served at `/frontend/` from Login
- **Key hooks:** `useChatWebSocket`, `useConversations`, `useKnowledge`, `useTenants`, `useActiveTenant`, `useGuestChat`, `useVoiceMode`, `useRoleNav`
- **Feature modules:** Knowledge admin, Analytics, Superadmin, Guest chat, Tenant selector
- **Build:** `npm run build` → `out/` copied/served by Login

Role-gated routes:

- Customer: `/frontend/`
- Guest: `/frontend/guest/`
- Employee: `/frontend/employee/*`
- Admin: `/frontend/admin/*`
- Master admin: `/frontend/master_admin/*`
- Superadmin: `/frontend/superadmin`

---

## 14. CONFIGURATION (`config.py` + `.env`)

Key variables:

```env
ENVIRONMENT=development|production
SESSION_SECRET=...
OLLAMA_MODEL=qwen2.5:3b
OLLAMA_HOST=127.0.0.1
RAG_USE_GPU=1
LLM_SERVER_URL=http://127.0.0.1:8010
RAG_SERVER_URL=http://127.0.0.1:7000
BASE_URL=http://127.0.0.1:7001
ALLOW_PUBLIC_GUEST_CHAT=true
ENFORCE_CHAT_TENANT_MEMBERSHIP=false  # true in prod
RAG_DOC_MODE=single|multi
RAG_QUERY_LLM_PREP=true
KMP_DUPLICATE_LIB_OK=TRUE
WHISPER_BEAM_SIZE=1
BCRYPT_ROUNDS=12
RATE_LIMIT_LOGIN=5
```

---

## 15. DEPLOYMENT (WINDOWS DEV)

1. `conda env create -f environment_main.yml` → `conda activate assistify_main`
2. `pip install itsdangerous authlib pdfplumber "setuptools<81"`
3. `copy .env.example .env` — configure secrets and model
4. `ollama pull qwen2.5:3b`
5. Build UI: `cd assistify-ui-design && npm install && npm run build`
6. Seed KB (optional): project scripts for sample snippets
7. Launch: `python start_main_servers.py` (or `--public` for Cloudflare tunnel)

Services started by launcher: Login, RAG, Ollama check, Piper, optional LLM shim.

See [SETUP_WINDOWS.md](SETUP_WINDOWS.md) for the full guide.

---

## 16. FEATURE MATRIX (MUST IMPLEMENT / PRESERVE)

### Customer

- Text + voice RAG chat, tenant selector, access requests, tickets, notifications, profile, guest chat

### Employee

- Customer CRM, ticket management, analytics

### Admin (tenant)

- User CRUD, KB upload/reindex/delete, analytics, audit logs, access approval, MFA enable

### Master admin

- Tenant admin management, full tenant-scoped admin

### Superadmin

- Tenant CRUD, platform visibility, permanent delete with cleanup

### KB & RAG

- PDF/TXT upload, adaptive chunking, per-tenant Chroma, hybrid retrieval, TOON, query prep, response validation, pipeline monitoring

### Voice

- STT/TTS pipeline, VAD, barge-in, EN+AR, browser TTS fallback

---

## 17. KEY BACKEND MODULES (RESPONSIBILITIES)

| Module | Responsibility |
|--------|----------------|
| `assistify_rag_server.py` | Orchestration, routing, LLM calls, WS handler entry |
| `knowledge_base.py` | Ingestion, chunking, embed, search, tenant purge |
| `pdf_ingestion_rag.py` | VectorStore, rerank, quality filters, query profile |
| `rag_query_prep.py` | Greeting strip, LLM normalize, spelling |
| `rag_chunk_heuristics.py` | Table/heading chunk detection |
| `response_validator.py` | PII/profanity/uncertainty |
| `chat_store.py` | Normalized conversation persistence |
| `tenant_access.py` | Membership validation cache |
| `login_server.py` | Auth gateway, proxy, static UI |
| `tenant_lifecycle.py` | Tenant delete cascade |

---

## 18. TESTING & QUALITY

- Unit tests: `tests/test_rag_*`, `tests/test_tenant_*`, `tests/test_zero_hardcode_generalization.py`
- Eval scripts: `scripts/*_eval.py`, `scripts/verify_kb_rag_fixes.py` (diagnostic only, not production logic)
- Before merge: AST parse, no hardcoded domain literals in `backend/assistify_rag_server.py`
- Adversarial genericity: extractor must return evidence from synthetic chunks across banking/food/healthcare/HR/SaaS domains

---

## 19. KNOWN CONSTRAINTS & INCONSISTENCIES (DO NOT REINTRODUCE)

- Monolithic `assistify_rag_server.py` — refactor carefully, preserve behavior
- `retrieval_filter.py` unused — filtering inline in VectorStore
- LLM port: prefer `8010` via launcher
- Stale UI duplicate folders — ignore
- Ticket REST partially in login_server only
- Answers from extractors are **verbatim evidence sentences** — evals may need re-baseline

---

## 20. IMPLEMENTATION ACCEPTANCE CRITERIA

When implementing any feature, verify:

1. **Tenant isolation** — no cross-tenant data leak in retrieval, files, or SQL
2. **RBAC** — correct `require_login` / `require_tenant_staff` / superadmin gates
3. **Evidence grounding** — no answer value without retrievable chunk provenance
4. **Genericity** — passes Future Document Test; no domain hardcoding
5. **Security** — CSRF on mutations, rate limits, session validation, PII filter
6. **Performance** — GPU for LLM/embeddings only; voice on CPU
7. **Observability** — log route decisions, retrieval metrics, validation results
8. **UI parity** — React hooks updated if API contract changes
9. **Backward compatibility** — existing conversations and KB collections remain readable
10. **Documentation** — update `README.md` / `docs/SYSTEM_ARCHITECTURE.md` if architecture changes

---

## 21. DIAGRAMS REFERENCE

Consolidated index: [DIAGRAMS.md](DIAGRAMS.md) (35 mermaid diagrams from README, SYSTEM_ARCHITECTURE, diagrams/, etc.)

Required diagram types for documentation:

- Use case (actors × features)
- Sequence (login → proxy → RAG → Chroma → Ollama)
- Activity (query routing decision tree)
- Class (backend module relationships)
- Block (subsystems + data stores)
- Architecture (layered deployment)
- WBS (project work breakdown)

---

## 22. YOUR TASK (WHEN USING THIS PROMPT)

When asked to implement, fix, or extend Assistify:

1. Read relevant modules before editing (match existing conventions)
2. Never add domain-specific hardcoding
3. Prefer evidence-driven extraction over template answers
4. Minimize diff scope — one concern per change
5. Run tests relevant to touched area
6. Deliver Genericity + Evidence-Origin + Future-Document assessments for RAG changes
7. Do not break Login→RAG proxy, tenant scoping, or session auth
8. Preserve multi-tenant collection naming and asset paths
9. Keep CPU/GPU policy intact
10. Update docs only when behavior changes materially

---

*End of master prompt.*
