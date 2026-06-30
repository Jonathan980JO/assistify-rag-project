# Environment Validation Report — Phase 13A

- **Branch:** `refactor/architecture-v2`
- **Date:** 2026-06-27
- **Mode:** Validation-only (no changes to environment, schema, Chroma, or code)
- **Repo root:** project root (`assistify-rag-project-main`)
- **Result:** PASS

All evidence below was reproduced live against the running interpreter and services.

---

## 1. Python Environment — PASS

| Item | Value |
|---|---|
| Python version | 3.11.14 (Anaconda, MSC v.1929 64-bit) |
| Interpreter | `python` (with `assistify_main` conda env active) |
| Conda env | `assistify_main` (active) |
| Prefix | conda env prefix for `assistify_main` |

The active interpreter matches the env the canonical launcher resolves (`conda:assistify_main`, confirmed in Part 1).

---

## 2. Required Packages — PASS

Imported live; version + resolved file recorded.

| Package | Status | Version | Source |
|---|---|---|---|
| fastapi | OK | 0.115.12 | site-packages |
| uvicorn | OK | 0.34.2 | site-packages |
| starlette | OK | 0.46.2 | site-packages |
| pydantic | OK | 2.10.6 | site-packages |
| requests | OK | 2.32.5 | user site-packages |
| httpx | OK | 0.28.1 | site-packages |
| chromadb | OK | 0.5.23 | site-packages |
| sentence_transformers | OK | 3.4.1 | site-packages |
| torch | OK | 2.6.0+cu124 | site-packages (CUDA 12.4) |
| transformers | OK | 4.49.0 | site-packages |
| pyotp | OK | 2.9.0 (real) | site-packages |
| bcrypt | OK | 4.0.1 | site-packages |
| itsdangerous | OK | 2.2.0 | site-packages |
| jinja2 | OK | 3.1.6 | site-packages |
| python_multipart | OK | 0.0.20 | site-packages |
| faster_whisper | OK | 1.1.1 | site-packages |
| numpy | OK | 2.4.4 | site-packages |
| python-dotenv | OK | installed | site-packages |
| websockets | OK | 15.0.1 | site-packages |

### PDF ingestion dependencies (used by `backend/pdf_ingestion_rag.py`) — PASS

| Package | Status | Version |
|---|---|---|
| PyPDF2 | OK | 3.0.1 |
| pdfplumber | OK | 0.11.9 |
| pytesseract (OCR fallback) | OK | present |
| pdf2image (OCR fallback) | OK | present |

Note: `pypdf` and `fitz` (PyMuPDF) are **not installed**, but they are **not imported anywhere in the codebase** — the ingestion pipeline uses `PyPDF2` + `pdfplumber` (+ optional OCR). This is therefore not a gap. Verified via source scan of `backend/`.

---

## 3. Ollama Connectivity — PASS

- `GET http://127.0.0.1:11434/api/tags` -> HTTP 200
- LLM shim `GET http://127.0.0.1:8010/internal/gpu-status` -> HTTP 200, `ollama_reachable: true`
- Installed models: `lexi:latest`, `qwen2.5vl:7b`, `qwen2.5:7b`, `qwen2.5:3b`
- Active model: `qwen2.5:7b` (matches `config.OLLAMA_MODEL` default)

---

## 4. Piper TTS Connectivity — PASS

- `GET http://127.0.0.1:5002/health` -> HTTP 200
- `status: ok`, `engine: piper`, `ready: true`
- Voices loaded: `en`, `ar` (onnx); output sample rate 24000; model load time ~2.05s

---

## 5. Chroma Connectivity — PASS

- Path: `backend/chroma_db_v3` (matches `config.CHROMA_DB_PATH`) — exists
- Contents: `chroma.sqlite3` + 7 collection segment directories (UUID-named)
- RAG `/health` reports `knowledge_base: true` (KB readable by the live server)

---

## 6. SQLite Connectivity — PASS

`PRAGMA quick_check` = `ok` for all three databases.

| Database | Journal mode | quick_check | Tables |
|---|---|---|---|
| `Login_system/users.db` | WAL | ok | 16 |
| `backend/conversations.db` | delete | ok | 7 |
| `backend/analytics.db` | delete | ok | 6 |

---

## 7. Frontend Dependencies — PASS

| Item | Status |
|---|---|
| `assistify-ui-design/` | present |
| `package.json` | present |
| `node_modules/` | present |
| Built `out/index.html` | present |
| Built `out/_next/static/` | present |

The React UI is already built and ready to be served at `/frontend/`.

---

## Genericity & Evidence Assessment

- **Genericity:** All checks are package/service/file probes with no dependency on any specific document, company, or value. Would work for any future dataset.
- **Evidence origin:** Every row above was produced by a live import or HTTP/SQLite probe, not from constants.
- **Future-document compatibility:** Yes — environment validation is content-agnostic.

## Verdict: PASS — environment is ready for live validation.
