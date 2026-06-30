# RAG Retrieval — Authoritative Path

## Production retrieval flow

```
User query
  → assistify_rag_server.call_llm_with_rag()
  → get_tenant_rag(tenant_id).search()
  → LiveRAGManager.search()
  → pdf_ingestion_rag.VectorStore.search()
```

This is the **only** path used for live chat answers. It applies:

- **Embeddings:** `intfloat/multilingual-e5-base` with E5 `query:` / `passage:` prefixes
- **Reranker:** `cross-encoder/ms-marco-MiniLM-L-6-v2` (unless `ASSISTIFY_DISABLE_RERANKER` or safe mode)
- **Distance threshold:** `RAG_STRICT_DISTANCE_THRESHOLD` (default **1.0**) from `backend/config_head.py`
- **Tenant isolation:** per-tenant Chroma collections (`t{N}_support_docs_v3_latest`)

## Legacy / auxiliary path

`knowledge_base.search_documents()` uses a looser default threshold (**1.2**) and no reranker. It is used by some admin/debug tooling and ingestion helpers — **not** for production voice/text chat.

## ChromaDB location

Single source of truth: `config.CHROMA_DB_PATH` (default `backend/chroma_db_v3`). All ingestion and retrieval modules read this value.

## TTS naming note

Environment variable `XTTS_SERVICE_URL` points at the Piper microservice (`tts_service/piper_server.py` on port 5002). The "XTTS" name is historical; health checks expect `engine=piper`. Use `PIPER_SERVICE_URL` mentally when debugging TTS issues.
