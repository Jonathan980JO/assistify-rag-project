# Repository Classification Report

**Phase:** 9A – Repository Classification Audit
**Repository:** `assistify-rag-project-main`
**Date:** 2026-06-27
**Mode:** Read-only audit. No files were moved, deleted, or renamed.

---

## 1. Category Definitions

| Category | Meaning |
|---|---|
| **ACTIVE** | Source code, config, or assets the running system directly depends on. |
| **DEPLOYMENT** | Artifacts used to install/launch/run the system (env specs, launchers, model assets). |
| **DOCUMENTATION** | Human-readable docs, specs, and historical reports. |
| **GENERATED** | Auto-produced output: build caches, logs, DB indexes, eval dumps, virtualenvs, downloaded models. |
| **ARCHIVE** | Intentional snapshots/backups kept for reference. |
| **EXPERIMENTAL** | Scratch/dev probes, one-off scripts, draft UIs. Not part of the runtime. |
| **LEGACY** | Superseded or explicitly non-functional code kept around but no longer used. |
| **UNKNOWN** | Purpose or safety could not be confirmed; needs human review. |

> Classification is based on: directory contents, `.gitignore` rules (what is treated as disposable), git tracking status, and references from launcher/build scripts (`scripts/project_start_server.py`, `scripts/react_ui_build.py`, `scripts/verify_stack.py`).

---

## 2. Special-Focus Items (explicitly requested)

| Folder | Purpose | Category | Risk if Removed | Recommended Destination |
|---|---|---|---|---|
| **assistify-ui-design** | The live Next.js frontend. Referenced by all build/launch scripts; its `out/` static export is served by the Login server. | **ACTIVE** | **HIGH** — frontend stops building/serving. | Keep at root (canonical UI). |
| **assistify-ui-design (1)** | Duplicate UI draft. `package.json` name is `my-project` (generator default). Not referenced anywhere; uses pnpm + shadcn variant. | **LEGACY** (duplicate/superseded design draft) | **LOW** — not wired into build or runtime. | Move to an `archive/ui-drafts/` area after confirming nothing imports it. |
| **assistify-ui-design (2)** | Second duplicate UI draft (same `my-project` identity, adds `PROJECT_SUMMARY.md`). Not referenced. | **LEGACY** (duplicate/superseded design draft) | **LOW** — not wired into build or runtime. | Move to `archive/ui-drafts/`. |
| **graduation** | Python virtual environment (`Lib/site-packages`, `Scripts`, `share`) holding all runtime dependencies (~27k files). | **GENERATED** (virtualenv) | **MEDIUM** — runtime breaks until recreated, but fully reproducible from `environment_*.yml`. | Keep locally; should be git-ignored (currently untracked). Recreate via env files, do not archive. |
| **Qwen2.5-7B-GGUF** | Downloaded LLM weights repo (has own `.git`, `.gitattributes`, README, nested venv `graduation/`). Explicitly listed in `.gitignore`. | **GENERATED** (downloaded model asset) | **MEDIUM** — LLM inference breaks; re-downloadable from source. | Keep as local runtime asset (DEPLOYMENT dependency); never commit. |
| **archived_pdfs** | Archived source PDFs under `docs/`. Git-ignored. | **ARCHIVE** | **LOW** — reference corpus snapshot only. | Keep under a dedicated `archive/` location. |
| **Backup** | Two large full-project backup `.zip` files (~15 GB + ~7 GB) plus `project_config_backup/`. Git-ignored. | **ARCHIVE** | **LOW** (for repo function) / **HIGH** (as recovery point) — not used at runtime. | Move off-repo to external/cold storage. |
| **scratch** | Ad-hoc baseline/probe scripts and server stdout/stderr logs. Git-ignored. | **GENERATED / EXPERIMENTAL** | **LOW** — disposable scratch work. | Safe to clear; relocate keepers to `tools/testing`. |
| **tmp** | ~200 temp files: eval logs, diffs, debug scripts, before/after dumps. Git-ignored (`tmp/`, `tmp_*`). | **GENERATED** (disposable) | **NONE** — pure scratch output. | Safe to delete/clear. |
| **tools** | Developer test/diagnostic tooling (`tools/testing/*` probes, WS regression scripts). Not part of runtime serving path. | **EXPERIMENTAL** (dev/test tooling) | **LOW–MEDIUM** — losing regression probes hurts QA, not runtime. | Keep as `tools/` but treat as dev-only. |
| **non_functional** | Explicitly parked non-working code: `old_python/` (git-ignored), `TMP_Codes/`, `media_logs/`. | **LEGACY** | **NONE** — already marked non-functional. | Move to `archive/legacy/` or delete after review. |
| **Notepad_Test_Results** | ~49 captured test/validation/log output files. | **GENERATED** | **NONE** — historical console captures. | Safe to clear; archive any needed evidence. |
| **assistify_refactor_audit** | Audit snapshot: huge concatenated source dumps (`assistify_rag_server.py` 2 MB, tree, route/import/TODO listings) + a `.rar`. Mirrors the root `assistify_refactor_audit.zip`. | **ARCHIVE** (audit snapshot) | **LOW** — point-in-time audit artifact, not runtime. | Move to `archive/audits/`. |

---

## 3. All Top-Level Directories

| Folder | Purpose | Category | Risk if Removed | Recommended Destination |
|---|---|---|---|---|
| `backend/` | Core RAG server, routers, retrieval, services, schemas, DB access. The heart of the system. | **ACTIVE** | **CRITICAL** | Keep at root. |
| `assistify-ui-design/` | Live Next.js frontend (see §2). | **ACTIVE** | **HIGH** | Keep at root. |
| `Login_system/` | Authentication / login server (28 tracked files). | **ACTIVE** | **HIGH** | Keep at root. |
| `tts_service/` | Piper TTS service (`piper_server.py`). | **ACTIVE** | **HIGH** (voice features) | Keep at root. |
| `xtts_service/` | XTTS voice service (`xtts_server.py`, stress test). | **ACTIVE** | **MEDIUM–HIGH** (voice) | Keep at root. |
| `TTS/` | Small local package (`api.py`, `__init__.py`) — likely a shim/adapter. | **ACTIVE** (verify) | **MEDIUM** | Keep; confirm it is imported (see §6). |
| `scripts/` | Operational + dev scripts: launchers, migrations, reindexing, verification (103 tracked). Mixed with one-off `_*`/`tmp_*` probes. | **ACTIVE** (with EXPERIMENTAL subset) | **HIGH** for launchers/migrations | Keep; consider splitting one-off probes into `tools/`. |
| `scripts/launch_windows/` | Windows launch helpers. | **DEPLOYMENT** | **MEDIUM** | Keep under `scripts/`. |
| `tests/` | Pytest suite (multitenant, OWASP, RAG, TTS, generalization). | **ACTIVE** | **MEDIUM** (CI/quality) | Keep at root. |
| `tools/` | Dev/test diagnostic tooling. | **EXPERIMENTAL** | **LOW–MEDIUM** | Keep (dev-only). |
| `docs/` | Project documentation, architecture, setup, security, diagrams. | **DOCUMENTATION** | **LOW** (for runtime) | Keep at root. |
| `models/` | `piper/` voice model files. Git-ignored (`models/`). | **GENERATED** (runtime model asset / **DEPLOYMENT**) | **MEDIUM** (voice) — re-downloadable | Keep locally; never commit. |
| `TTS_local_backup/` | Backup of TTS assets. Git-ignored. | **ARCHIVE** | **LOW** | Move to external/cold storage. |
| `chroma_db/` | Chroma vector index (`chroma.sqlite3` + segment dir). Git-ignored. | **GENERATED** (rebuildable index) | **MEDIUM** — rebuildable via reindex scripts | Keep locally; never commit. |
| `chroma_db_production/` | Production Chroma index. Git-ignored (`*.sqlite3`). | **GENERATED** (rebuildable index) | **MEDIUM–HIGH** — rebuildable but costly | Keep locally; back up separately. |
| `logs/` | Runtime/server/validation logs. Git-ignored (`logs/`, `*.log`). | **GENERATED** | **NONE** | Safe to clear/rotate. |
| `LOGSS/` | Two live log files (login + rag). Git-ignored. | **GENERATED** | **NONE** | Safe to clear; folder name looks accidental. |
| `Json/` | ~112 query-result JSON outputs (`run_queries_results_*`, `ws_*`). Git-ignored. | **GENERATED** (eval output) | **NONE** | Safe to clear; archive needed evidence. |
| `graduation/` | Python virtualenv (see §2). | **GENERATED** | **MEDIUM** (reproducible) | Local only; git-ignore. |
| `Qwen2.5-7B-GGUF/` | Downloaded LLM weights (see §2). | **GENERATED** | **MEDIUM** | Local only; never commit. |
| `archived_pdfs/` | Archived source PDFs (see §2). | **ARCHIVE** | **LOW** | `archive/`. |
| `Backup/` | Multi-GB project backups (see §2). | **ARCHIVE** | **LOW** (runtime) | External/cold storage. |
| `scratch/` | Scratch probes + server logs (see §2). | **GENERATED / EXPERIMENTAL** | **LOW** | Clear / relocate keepers. |
| `tmp/` | Disposable temp/debug artifacts (see §2). | **GENERATED** | **NONE** | Safe to delete. |
| `non_functional/` | Parked non-working code (see §2). | **LEGACY** | **NONE** | `archive/legacy/`. |
| `Notepad_Test_Results/` | Captured test output (see §2). | **GENERATED** | **NONE** | Clear. |
| `assistify_refactor_audit/` | Audit source dumps (see §2). | **ARCHIVE** | **LOW** | `archive/audits/`. |
| `phase9_repo_audit/` | Audit CSV inventories (`all_files.csv`, `all_folders.csv`, etc.) generated for this audit cycle. | **GENERATED** | **NONE** | Keep alongside this report or in `archive/audits/`. |
| `assistify-rag-project-main/` | Nested folder containing only `backend/` — a leftover partial copy of the project inside itself. | **LEGACY** (accidental nested copy) | **LOW** — appears unused | Review and remove after confirming nothing references it. |
| `.planning/` | GSD/workflow planning state (`debug/`). | **DOCUMENTATION** (tooling state) | **LOW** | Keep. |
| `.claude/`, `.remember/` | Assistant/agent tooling state. | **GENERATED** (tooling) | **NONE** | Keep/ignore. |
| `.vscode/` | Editor settings. Git-ignored. | **ACTIVE** (dev config) | **NONE** | Keep. |
| `.pytest_cache/` | Pytest cache. Git-ignored. | **GENERATED** | **NONE** | Safe to delete. |
| `__pycache__/` | Python bytecode cache. Git-ignored. | **GENERATED** | **NONE** | Safe to delete. |
| `.git/` | Git repository metadata. | **ACTIVE** (VCS) | **CRITICAL** | Keep. |

---

## 4. Notable Top-Level Files

| File(s) | Purpose | Category | Risk if Removed | Recommended Destination |
|---|---|---|---|---|
| `config.py` | Central application configuration. | **ACTIVE** | **CRITICAL** | Keep. |
| `conftest.py` | Pytest fixtures/config. | **ACTIVE** | **MEDIUM** | Keep. |
| `start_main_servers.py`, `start_piper_service.bat` | Service launchers. | **DEPLOYMENT** | **HIGH** | Keep. |
| `environment_main.yml`, `environment_main_locked.yml`, `environment_xtts.yml`, `environment_xtts_locked.yml` | Conda environment specs (dependency definitions). | **DEPLOYMENT** | **HIGH** — needed to recreate `graduation/` | Keep. |
| `.env.example` | Env-var template. | **DOCUMENTATION / DEPLOYMENT** | **LOW** | Keep. |
| `.env` | Live secrets/config. Git-ignored. | **ACTIVE** (sensitive) | **HIGH** | Keep local; never commit. |
| `.gitignore`, `.cursorrules` | Repo/agent config. | **ACTIVE** | **LOW–MEDIUM** | Keep. |
| `README.md`, `LAUNCHER_README.md` | Primary docs. | **DOCUMENTATION** | **LOW** | Keep. |
| `AGENT_TASK_PROMPT.md`, `AI_AGENT_RULES.md` | Agent guidance docs. | **DOCUMENTATION** | **LOW** | Keep. |
| `BUGFIX_LIST_QUERIES_SUMMARY.md`, `EVIDENCE_REPORT.md`, `RAW_EVIDENCE_FINAL.md`, `PATCHES_APPLIED.md`, `PHASE_AR0_ANALYSIS_REPORT.md`, `PHASE_AR1B_FINAL_REPORT.md`, `UPSTREAM_PATCH_BUNDLES.md` | Historical phase/analysis reports. | **DOCUMENTATION** (historical) | **NONE** | Move to `docs/reports/` or `archive/`. |
| `cleanup_repo.py`, `collect_evidence.py`, `hotswap_validation.py`, `phase2_validation.py`, `phase3_validation.py`, `verify_rag_standalone.py`, `run_all.py`, `run_all_queries.py` | Maintenance/validation scripts kept at root. | **ACTIVE** (utility) | **LOW–MEDIUM** | Consider moving into `scripts/`. |
| `check_chunk8.py`, `check_page2.py`, `dump_chunks_sql_v3.py`, `find_6ms.py`, `find_chunk_by_text.py`, `find_rank1.py`, `get_ans.py`, `get_chunk6.py`, `get_chunks.py`, `get_chunks_8_9_10.py`, `inspect_chunks.py`, `query_final.py`, `query_test.py`, `query_ws.py`, `scan_pdf.py`, `search_all_chunks.py`, `test_list_patch.py`, `test_search.py`, `trace_ext.py`, `trace_ws_route.py`, `validate_ws.py` | One-off debugging/inspection scripts scattered at repo root. | **EXPERIMENTAL** | **LOW** | Consolidate into `tools/` or remove. |
| `playwright.py`, `pyotp.py`, `pyttsx3.py`, `reportlab.py` | Root files whose names **shadow installed PyPI packages** (`playwright`, `pyotp`, `pyttsx3`, `reportlab`). High risk of import-shadowing bugs. | **UNKNOWN** (needs review) | **MEDIUM** — may silently break real imports | Review; rename or remove. |
| `repo_tree.txt`, `output.txt`, `phase2_validation_output.txt`, `temp_phase15c_pre_out.txt` | Generated text dumps/logs. Git-ignored (`*.txt`). | **GENERATED** | **NONE** | Safe to delete. |
| `assistify_refactor_audit.zip` | Zipped audit snapshot (~2 MB). Git-ignored (`*.zip`). | **ARCHIVE** | **LOW** | `archive/audits/`. |
| `._assistify_session_secret` | Hidden session secret file. Git-ignored (`._*`). | **UNKNOWN** (sensitive) | **MEDIUM** — possible secret | Verify; ensure never committed. |
| `start_piper_service.bat` | Piper launcher. | **DEPLOYMENT** | **MEDIUM** | Keep. |

---

## 5. Summary by Category

- **ACTIVE:** `backend/`, `assistify-ui-design/`, `Login_system/`, `tts_service/`, `xtts_service/`, `TTS/`, `scripts/` (core), `tests/`, `config.py`, `conftest.py`, `.env`, `.gitignore`, `.cursorrules`, `.vscode/`, `.git/`.
- **DEPLOYMENT:** `environment_*.yml` (×4), `start_main_servers.py`, `start_piper_service.bat`, `scripts/launch_windows/`, `.env.example`. Runtime model assets (`models/`, `Qwen2.5-7B-GGUF/`) straddle DEPLOYMENT/GENERATED.
- **DOCUMENTATION:** `docs/`, `README.md`, `LAUNCHER_README.md`, agent/phase report `.md` files, `.planning/`.
- **GENERATED:** `graduation/`, `Qwen2.5-7B-GGUF/`, `models/`, `chroma_db/`, `chroma_db_production/`, `logs/`, `LOGSS/`, `Json/`, `tmp/`, `scratch/`, `Notepad_Test_Results/`, `phase9_repo_audit/`, `.pytest_cache/`, `__pycache__/`, root `*.txt` dumps.
- **ARCHIVE:** `Backup/`, `archived_pdfs/`, `TTS_local_backup/`, `assistify_refactor_audit/` (+ `.zip`).
- **EXPERIMENTAL:** `tools/`, `scratch/`, root one-off debug scripts.
- **LEGACY:** `assistify-ui-design (1)`, `assistify-ui-design (2)`, `non_functional/`, nested `assistify-rag-project-main/`.
- **UNKNOWN:** `playwright.py`, `pyotp.py`, `pyttsx3.py`, `reportlab.py`, `._assistify_session_secret`.

---

## 6. Items Requiring Human Review

1. **`TTS/`** — small local package; confirm it is actually imported by the runtime vs. shadowing the PyPI `TTS` (Coqui) package.
2. **`playwright.py` / `pyotp.py` / `pyttsx3.py` / `reportlab.py`** — root modules that shadow real third-party libraries; likely accidental and potentially breaking imports.
3. **`assistify-rag-project-main/`** — nested partial copy of the project; confirm unused before any cleanup.
4. **`assistify-ui-design (1)` and `(2)`** — confirm neither is the intended canonical UI before archiving (canonical is `assistify-ui-design/`).
5. **`._assistify_session_secret`** — verify it contains no committed secret material.
6. **`chroma_db_production/`** — confirm whether it can be regenerated or must be treated as protected state before any relocation.

---

## 7. Genericity & Compliance Assessment

Per the core engineering rule, this audit was evaluated for document-agnostic compliance:

1. **Genericity Assessment:** PASS. Classification is derived purely from repository structure, file types, `.gitignore` rules, git tracking status, and build-script references. No rule keys on any specific document, company, product, dataset, or hardcoded value.
2. **Evidence-Origin Assessment:** PASS. Every classification cites observable evidence — directory listings, `package.json` identity/name fields, `.gitignore` entries, and explicit references inside `scripts/react_ui_build.py`, `scripts/verify_stack.py`, and `scripts/project_start_server.py`.
3. **Future-Document Compatibility Assessment:** PASS. The categories and reasoning apply to any future repository content. A new document/domain added tomorrow would still be classified by the same structural signals, with no code path depending on known content.

**No files were moved, deleted, or renamed. This report is the sole output.**
