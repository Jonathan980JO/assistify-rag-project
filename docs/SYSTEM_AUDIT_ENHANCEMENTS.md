# Assistify System Audit — Enhancements Applied

This document records the engineering audit findings and the enhancements implemented from the prioritized roadmap (P0–P3).

## Architecture (unchanged core)

```
Browser → Login :7001 (auth, guest cookie, proxy) → RAG :7000 → Ollama :11434
                                              ↓
                                    Chroma (per-tenant collections)
```

## P0 — Correctness & friendly support tone

| Item | Change |
|------|--------|
| Friendly persona | Wired `CUSTOMER_SUPPORT_AGENT_SYSTEM_PROMPT` via `build_english_support_system_prompt()` and `build_english_stream_context_block()` in HTTP + WebSocket paths |
| Blunt sentinel | LLM prompts no longer instruct raw `Not found in the document.`; internal sentinel still mapped to warm copy via `_finalize_user_visible_answer` |
| Cross-tenant typo bug | `_build_dynamic_vocab()` now uses `_active_rag()` collection instead of default tenant |
| List tone | `_apply_customer_support_tone()` called in live `_apply_not_found_ux` path |
| Frontend UX | Connection banner, error bubble, message queue on disconnect, `{type:"conversation"}` handler, separate guest/auth tenant localStorage keys |

## P1 — Intelligence & robustness

| Item | Change |
|------|--------|
| No-match copy | Warmer `CS_NO_MATCH_RESPONSE_EN/AR` in `config_head.py` |
| Uncertainty disclaimer | Softer wording in `response_validator.py` |
| Arabic persona | Tenant-neutral support prompt (removed Amazon-specific copy) |
| Arabic validation | `validate_response` runs on Arabic streaming output |
| Dictionary typo fallback | `backend/spelling_fallback.py` + integration in `_lightweight_spelling_correction` |
| Tenant membership | `ENFORCE_CHAT_TENANT_MEMBERSHIP` in `config.py` (on in production by default); enforced in `tenant_access.py` |

## P2 — Speed (quality-safe tricks applied)

| Trick | Change | Quality risk |
|-------|--------|--------------|
| Shared embedder | `VectorStore` reuses `knowledge_base.get_shared_embedder()` | None |
| Larger caches | Rerank LRU 128→512; query-embedding LRU (256 entries) | None |
| Smaller rerank pool | Candidate ceiling 240→120 | Low (monitor eval) |
| Vocab scan cap | Typo vocab scan 5000→1500 docs | Low |
| Synthesis context cap | Up to 8 chunks when `top_k>8` or structure/chapter queries | Slight token/latency increase |
| Skip rerank | Single high-confidence hit (`similarity≥0.92`, `top_k≤3`) skips cross-encoder | Low |

Env knobs: `RERANK_CACHE_MAX`, `QUERY_EMBED_CACHE_MAX`, `ASSISTIFY_DOMAIN_BOOST`.

## P3 — Sustainability

| Item | Change |
|------|--------|
| Dead ingest path | `AdaptiveRAGPipeline.ingest_pdf` emits `DeprecationWarning` |
| `clear_knowledge_base` | Uses correct `tenant_collection_name(DEFAULT_TENANT_ID)` |
| Domain heuristics | Eval-specific token boosts gated behind `ASSISTIFY_DOMAIN_BOOST=1` |
| Employee KB reindex | Login proxy now uses `require_tenant_staff()` (aligned with RAG) |
| Frontend hardening | `typescript.ignoreBuildErrors: false`; AnalyserNode replaces deprecated ScriptProcessorNode; reconnect cap (12 attempts) |
| Voice overlay | Streaming cursor only during `transcribing` state |

## Configuration reference

```env
# Membership enforcement (auto-on in production)
ENFORCE_CHAT_TENANT_MEMBERSHIP=false

# Retrieval tuning
RERANK_CACHE_MAX=512
QUERY_EMBED_CACHE_MAX=256
ASSISTIFY_DOMAIN_BOOST=0
```

## Verification

```powershell
conda activate assistify_main
$env:PYTHONUTF8 = "1"
python tests\test_rag_query_prep.py
python tests\test_tenant_selector.py
python tests\test_rag_chunk_retrieval_fixes.py
```

Frontend typecheck:

```powershell
cd assistify-ui-design
npm run build
```
