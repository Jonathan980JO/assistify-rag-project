# Cleanup Plan

**Phase:** 9B – Cleanup Plan Generation
**Repository:** `assistify-rag-project-main`
**Date:** 2026-06-27
**Mode:** ANALYSIS ONLY. No files were moved, deleted, renamed, or modified. This document is the sole output.

**Inputs:** Phase 8 monolith decomposition (`assistify_rag_server.py`: ~44,818 → ~4,996 lines) and Phase 9A Repository Classification Audit (`Repository_Classification_Report.md`).

> **Method note (genericity):** Every classification and recommendation below is derived from observable, content-agnostic signals only — directory structure, file types, git tracking status (`git ls-files`), `.gitignore` rules, on-disk byte sizes, `package.json` identity fields, and explicit references inside launcher/build scripts (`scripts/project_start_server.py`, `scripts/react_ui_build.py`, `scripts/verify_stack.py`, `scripts/verify_react_routes.py`). No recommendation depends on any specific document, company, product, dataset, metric, or hardcoded value.

---

## Executive Summary

| Metric | Value (measured) |
|---|---|
| Top-level directories | 36 (incl. dot-dirs) |
| Top-level files | ~60 |
| Total on-disk size | ~49 GB |
| Largest single item | `Backup/` (~21.5 GB) |
| Disposable / non-runtime on disk | ~27 GB (Backup, Qwen weights, venv, tmp, dup UI, audits, logs) |
| Git-tracked clutter at root | 4 shadow stubs, ~25 one-off debug scripts, 2 duplicate UIs, 7 historical reports |

**Top risks found (detail in Part 2):**

1. **`pyotp.py` import-shadowing in production auth.** `Login_system/login_server.py` does `import pyotp` for MFA. A git-tracked root stub `pyotp.py` shadows the real installed `pyotp` package when the process runs with the repo root on `sys.path`. The stub returns a **constant `"000000"`** TOTP and lacks `provisioning_uri`. This is both a functional break and a security hazard. **Requires human review / fix in a later phase (not this phase).**
2. **A nested `assistify-rag-project-main/` directory** containing only a stray 168 KB `chroma.sqlite3`. Untracked, unreferenced by runtime code.
3. **Two duplicate frontend copies** (`assistify-ui-design (1)` / `(2)`, both `name: "my-project"`) committed to git but referenced by nothing.
4. **~27 GB of generated/archive content living inside the repo** (backups, model weights, virtualenv).

---

# PART 1 — REPOSITORY ANALYSIS

Classification legend: **ACTIVE · DEPLOYMENT · DOCUMENTATION · GENERATED · ARCHIVE · EXPERIMENTAL · LEGACY · UNKNOWN**

### 1.1 Application code (ACTIVE)

| Item | Category | Purpose | Current usage | Referenced by | Risk if removed | Recommended destination |
|---|---|---|---|---|---|---|
| `backend/` | ACTIVE | Core RAG server: routers, retrieval, services, schemas, DB access. ~10.6 GB on disk (includes local model/asset/index subfolders). | Runtime heart of the system. | Launchers, all services. | **CRITICAL** | `backend/` (keep; relocate heavy data subdirs to `data/`) |
| `Login_system/` | ACTIVE | Auth/login server; serves the React static export at `/frontend/`. 52 tracked files. | Runtime auth + UI host. | `project_start_server.py`. | **HIGH** | `Login_system/` (keep) |
| `assistify-ui-design/` | ACTIVE | Canonical Next.js frontend (`name: "assistify-ui-design"`, has `out/` + `node_modules/`). 117 tracked files, 435 MB on disk. | Built to `out/`, served by Login server. | `react_ui_build.py`, `verify_stack.py`, `verify_react_routes.py`, `project_start_server.py`. | **HIGH** | `frontend/` |
| `tts_service/` | ACTIVE | Piper TTS service (`piper_server.py`). | Voice synthesis. | `start_piper_service.bat`. | **HIGH** (voice) | `backend/` peer service (keep at root or under services) |
| `xtts_service/` | ACTIVE | XTTS voice service + stress test. | Voice synthesis. | Launch scripts. | **MEDIUM–HIGH** (voice) | keep (root/services) |
| `TTS/` | ACTIVE *(verify)* | 2-file local package (`api.py`, `__init__.py`); shadows the PyPI `TTS` (Coqui) name. | Possibly an adapter shim. | Confirm importer. | **MEDIUM** | keep after confirming it is the intended import target; otherwise `legacy/` |
| `config.py` | ACTIVE | Central app configuration. | Imported app-wide. | Backend/services. | **CRITICAL** | keep at root |
| `conftest.py` | ACTIVE | Pytest fixtures/config. | Test collection. | `tests/`. | **MEDIUM** | keep at root |
| `.env` | ACTIVE (sensitive) | Live secrets. Git-ignored. | Runtime config. | App. | **HIGH** | keep local; never commit |
| `.gitignore`, `.cursorrules` | ACTIVE | Repo/agent config. | Tooling. | — | LOW–MED | keep at root |
| `.vscode/` | ACTIVE (dev cfg) | Editor settings. Git-ignored. | Dev. | — | NONE | keep |
| `.git/` | ACTIVE (VCS) | Version control metadata. | Always. | — | **CRITICAL** | keep |

### 1.2 Deployment artifacts (DEPLOYMENT)

| Item | Category | Purpose | Current usage | Referenced by | Risk if removed | Recommended destination |
|---|---|---|---|---|---|---|
| `environment_main.yml`, `environment_main_locked.yml`, `environment_xtts.yml`, `environment_xtts_locked.yml` | DEPLOYMENT | Conda env specs; reproduce the `graduation/` venv. | Environment recreation. | Setup docs. | **HIGH** | `deployment/` (or keep at root) |
| `start_main_servers.py` | DEPLOYMENT | Multi-service launcher. | Boot. | Operators. | **HIGH** | `scripts/deployment/` |
| `start_piper_service.bat` | DEPLOYMENT | Piper launcher (Windows). | Boot voice. | Operators. | **MEDIUM** | `scripts/deployment/` |
| `scripts/launch_windows/` | DEPLOYMENT | Windows launch helpers. | Boot. | Operators. | **MEDIUM** | `scripts/deployment/` |
| `.env.example` | DEPLOYMENT/DOC | Env-var template. | Onboarding. | Docs. | LOW | keep at root |
| `models/` | DEPLOYMENT/GENERATED | `piper/` voice model files (120 MB). Git-ignored. | Runtime voice. | TTS services. | **MEDIUM** (re-downloadable) | `data/` model assets (local only) |
| `Qwen2.5-7B-GGUF/` | DEPLOYMENT/GENERATED | Downloaded LLM weights (5.0 GB, own `.git`). Git-ignored. | LLM inference. | Backend LLM. | **MEDIUM** (re-downloadable) | local runtime asset (never commit) |

### 1.3 Documentation (DOCUMENTATION)

| Item | Category | Purpose | Referenced by | Risk if removed | Recommended destination |
|---|---|---|---|---|---|
| `docs/` | DOCUMENTATION | Architecture, setup, security, diagrams (43 files). | Humans. | LOW (runtime) | `docs/` (sub-organize) |
| `README.md` (76 KB), `LAUNCHER_README.md` | DOCUMENTATION | Primary docs. | Humans. | LOW | keep `README.md` at root; `LAUNCHER_README.md` → `docs/deployment/` |
| `AGENT_TASK_PROMPT.md`, `AI_AGENT_RULES.md` | DOCUMENTATION | Agent guidance. | Tooling/humans. | LOW | `docs/` |
| `Repository_Classification_Report.md`, `Cleanup_Plan.md` (this) | DOCUMENTATION | Phase 9 audit/plan. | Humans. | LOW | `docs/architecture/` or `docs/archive/` |
| `BUGFIX_LIST_QUERIES_SUMMARY.md`, `EVIDENCE_REPORT.md`, `RAW_EVIDENCE_FINAL.md`, `PATCHES_APPLIED.md`, `PHASE_AR0_ANALYSIS_REPORT.md`, `PHASE_AR1B_FINAL_REPORT.md`, `UPSTREAM_PATCH_BUNDLES.md` | DOCUMENTATION (historical) | Past phase/analysis reports. | Humans. | NONE | `docs/archive/` |
| `.planning/` | DOCUMENTATION (tooling state) | GSD/workflow state. | Tooling. | LOW | keep |

### 1.4 Generated / rebuildable (GENERATED)

| Item | Category | Purpose | Git status | Risk if removed | Recommended destination |
|---|---|---|---|---|---|
| `graduation/` | GENERATED (virtualenv) | Python venv, 21,214 files / 407 MB. | Untracked (see Part 2.4) | **MEDIUM** (reproducible from env files) | local only; git-ignore explicitly |
| `chroma_db/` | GENERATED (vector index) | Chroma index. Git-ignored. | ignored | **MEDIUM** (rebuildable) | `data/chroma/` |
| `chroma_db_production/` | GENERATED (vector index) | Production Chroma index. Git-ignored. | ignored | **MEDIUM–HIGH** (rebuildable, costly) | `data/chroma/` (back up separately) |
| `logs/` (46 files, 7 MB) | GENERATED | Runtime logs. Git-ignored. | ignored | NONE | `data/cache/` or rotate; gitignore |
| `LOGSS/` (2 files) | GENERATED | Stray live log dir (name looks accidental). Git-ignored. | ignored | NONE | clear; fold into `logs/` |
| `Json/` (112 files) | GENERATED | Query-result JSON eval outputs. Git-ignored. | ignored | NONE | clear; archive evidence if needed |
| `tmp/` (200 files, 80 MB) | GENERATED | Disposable eval/debug dumps. Git-ignored. | ignored | NONE | delete |
| `scratch/` (8 files) | GENERATED/EXPERIMENTAL | Ad-hoc probes + stdout. Git-ignored. | ignored | LOW | clear; relocate keepers to `tools/` |
| `Notepad_Test_Results/` (49 files) | GENERATED | Captured console output. | mixed | NONE | clear; archive evidence if needed |
| `phase9_repo_audit/` | GENERATED | Audit CSV inventories. | untracked | NONE | `docs/archive/` or `tools/diagnostics/` |
| `.pytest_cache/`, `__pycache__/` | GENERATED | Caches. Git-ignored. | ignored | NONE | delete |
| `.claude/`, `.remember/` | GENERATED (tooling) | Assistant/agent state. | ignored | NONE | keep/ignore |
| `repo_tree.txt` (6.2 MB), `output.txt`, `phase2_validation_output.txt`, `temp_phase15c_pre_out.txt`, `phase2_validation_output.txt` | GENERATED | Text dumps/logs. Git-ignored (`*.txt`). | ignored | NONE | delete |

### 1.5 Archive (ARCHIVE)

| Item | Category | Purpose | Size | Risk if removed | Recommended destination |
|---|---|---|---|---|---|
| `Backup/` | ARCHIVE | Multi-GB project backups + `project_config_backup/`. Git-ignored. | ~21.5 GB | LOW (runtime) / HIGH (recovery) | **off-repo cold storage** |
| `Qwen2.5-7B-GGUF/` | ARCHIVE/GENERATED | (also DEPLOYMENT) downloaded weights. | 5.0 GB | MEDIUM | local asset; never commit |
| `assistify_refactor_audit/` (+ `assistify_refactor_audit.zip` 2.2 MB) | ARCHIVE | Point-in-time audit source dumps. Git-ignored zip. | 13 MB | LOW | `archive/audits/` |
| `archived_pdfs/` (28 files) | ARCHIVE | Archived source PDFs. Git-ignored. | 3 MB | LOW | `archive/` |
| `TTS_local_backup/` (6 files) | ARCHIVE | Backup of TTS assets. Git-ignored. | <1 MB | LOW | off-repo / `archive/` |

### 1.6 Experimental (EXPERIMENTAL)

| Item | Category | Purpose | Risk if removed | Recommended destination |
|---|---|---|---|---|
| `tools/` (36 files) | EXPERIMENTAL | Dev/test diagnostics & WS regression probes. Not on runtime path. | LOW–MEDIUM (QA) | `tools/diagnostics/` + `tools/experiments/` |
| Root one-off debug scripts (see Part 3C) | EXPERIMENTAL | `check_*`, `find_*`, `get_*`, `query_*`, `trace_*`, `inspect_*`, `scan_pdf.py`, `search_all_chunks.py`, `dump_chunks_sql_v3.py`, etc. | LOW | `tools/experiments/` |
| `scripts/` one-off `_*` / `tmp_*` probes | EXPERIMENTAL | Mixed into operational scripts. | LOW | `tools/experiments/` |

### 1.7 Legacy (LEGACY)

| Item | Category | Purpose | Git status | Risk if removed | Recommended destination |
|---|---|---|---|---|---|
| `assistify-ui-design (1)` | LEGACY (dup UI draft) | Superseded UI copy, `name: "my-project"`, no `out/`/`node_modules/`. 35 tracked. | tracked | LOW | `legacy/ui-drafts/` |
| `assistify-ui-design (2)` | LEGACY (dup UI draft) | Second UI copy, `name: "my-project"`, adds `PROJECT_SUMMARY.md`. 40 tracked. | tracked | LOW | `legacy/ui-drafts/` |
| `non_functional/` (74 files) | LEGACY | Parked non-working code (`old_python/` git-ignored, `TMP_Codes/`, `media_logs/`). | mixed | NONE | `legacy/` |
| `assistify-rag-project-main/` (nested) | LEGACY (accidental copy) | Only `backend/chroma_db_reindex/chroma.sqlite3` (168 KB). | untracked | LOW | delete after review (Part 2.1) |

### 1.8 Unknown / needs human decision (UNKNOWN)

| Item | Category | Issue | Risk | Recommended destination |
|---|---|---|---|---|
| `playwright.py`, `pyotp.py`, `pyttsx3.py`, `reportlab.py` | UNKNOWN | Git-tracked root stubs that **shadow installed PyPI packages** (see Part 2.2). | **MEDIUM–HIGH** | human review; isolate to `tools/diagnostics/stubs/` or remove |
| `._assistify_session_secret` (96 B, hidden) | UNKNOWN (sensitive) | Possible secret material. Git-ignored (`._*`). | MEDIUM | verify contents; ensure never committed |

---

# PART 2 — SPECIAL INVESTIGATIONS

## 2.1 Nested repository — `assistify-rag-project-main/` inside `assistify-rag-project-main/`

**Evidence (measured):**
- Full recursive contents: a single file — `assistify-rag-project-main/backend/chroma_db_reindex/chroma.sqlite3` (167,936 bytes). No source code, no `.git`, no `package.json`.
- Git: `git ls-files -- "assistify-rag-project-main/*"` → **0 tracked files** (entire nested tree is untracked).
- References: the string `assistify-rag-project-main/` appears only in audit/report artifacts (`Repository_Classification_Report.md`, the `phase9_repo_audit/*.csv` files, this plan) and in unrelated path strings inside scripts (`backend/inspect_chroma.py`, `dump_chunks_sql_v3.py`, etc. that reference the *outer* repo path or `chroma_db_reindex`). **No runtime code targets the nested folder.**

**Conclusions:**
- **Why it exists:** Accidental artifact — almost certainly a reindex/test run executed with a mis-rooted output path, which created `<repo>/assistify-rag-project-main/backend/chroma_db_reindex/`. The folder name matches the repo name, confirming an unintended self-nesting.
- **Referenced?** No (0 git-tracked, no runtime reference).
- **Duplicate content?** No — it is *not* a copy of the project; it is a single stray Chroma SQLite index (`chroma_db_reindex/` is git-ignored, so it was never committed).
- **Cleanup recommendation:** **Safe to delete** after a one-line human confirmation that the `.sqlite3` is not an irreplaceable index. Risk: LOW. (Executed in Phase 10, not now.)

## 2.2 Package-shadowing risk — `playwright.py`, `pyotp.py`, `pyttsx3.py`, `reportlab.py`

**Evidence (measured):**
- All four files exist at repo root and are **git-tracked** (`git ls-files` returns all four).
- Contents are deliberate **stubs**:
  - `playwright.py` → `Dummy` class + `sync_playwright()` context manager.
  - `pyotp.py` → `TOTP` class whose `.now()` **returns the constant `"000000"`**, plus `random_base32()` returning a constant string. **No `pyotp.totp` submodule and no `provisioning_uri`.**
  - `pyttsx3.py` → `EngineStub` + `init()`.
  - `reportlab.py` → comment `"Minimal stub ... used only for static analysis"` + empty `class canvas`.
- Installed real packages in `graduation/Lib/site-packages/`: `playwright` ✅, `pyotp` ✅, `pyttsx3` ✅, `reportlab` ❌ (not installed).
- Real usages found:
  - `Login_system/login_server.py` (**production auth**): `import pyotp`, `pyotp.TOTP(secret)`, `pyotp.random_base32()`, `pyotp.totp.TOTP(secret).provisioning_uri(...)`.
  - `scripts/playwright_test.py`: `from playwright.async_api import async_playwright`.
  - `scripts/full_regression_test.py`, `scripts/test_pdf_fixes.py`: `from reportlab... import ...`.

**Will Python resolve to these root files?** **Yes — whenever the interpreter runs with the repo root as the first entry on `sys.path`.** Python prefers a top-level module (`pyotp.py` at CWD/script dir) over a site-packages package of the same name. So a process started from the repo root (`python Login_system/login_server.py`, `python -m ...` from root, or any script whose directory is the root) can import the **stub** instead of the real library.

**Are they dangerous?** **Yes — confirmed hazardous:**
- **`pyotp.py` is the worst case.** It shadows MFA logic in `login_server.py`. The stub (a) makes `pyotp.totp.TOTP(...).provisioning_uri(...)` raise `AttributeError` (no `totp` submodule), breaking enrollment, and (b) where it *does* resolve, returns a **hardcoded `"000000"`** TOTP — a silent authentication-bypass / security defect if it ever shadows the real library at runtime.
- **`reportlab.py`** shadows a library that **isn't even installed**; the stub only defines `class canvas`, so `from reportlab.pdfgen import canvas` / `from reportlab.lib...` will fail — but it masks the real "package missing" signal.
- **`playwright.py` / `pyttsx3.py`** would silently no-op real browser automation / TTS if shadowed.

**Recommended action (human review; executed later, not this phase):**
1. Do **not** leave these at the import root. Either (a) delete them if nothing legitimately needs stubs, or (b) relocate to a clearly non-importable folder (e.g. `tools/diagnostics/stubs/`) used only via explicit, isolated paths.
2. Re-verify each importer runs against the real installed package (especially `login_server.py` MFA).
3. Add a CI guard / lint check that fails if a root-level module name collides with an installed third-party distribution.

> This is the single highest-priority finding. It is **flagged for Phase 11 (Deployment Hardening)** — Phase 9B performs no modification.

## 2.3 Frontend duplicates — `assistify-ui-design`, `assistify-ui-design (1)`, `assistify-ui-design (2)`

**Evidence (measured):**

| Dir | `package.json` name | `out/` | `node_modules/` | Tracked files | On disk |
|---|---|---|---|---|---|
| `assistify-ui-design` | `assistify-ui-design` | ✅ yes | ✅ yes | 117 | 435 MB |
| `assistify-ui-design (1)` | `my-project` | ❌ no | ❌ no | 35 | 0.2 MB |
| `assistify-ui-design (2)` | `my-project` | ❌ no | ❌ no | 40 | 0.3 MB |

- All build/serve scripts reference **only** `assistify-ui-design`: `react_ui_build.py`, `verify_stack.py`, `verify_react_routes.py`, `project_start_server.py`. The `(1)`/`(2)` variants are referenced by **nothing**.

**Conclusions:**
- **Active frontend:** `assistify-ui-design` (canonical name, has built `out/` export, wired into every launcher). It is the only one that ships.
- **Duplicate copies:** `(1)` and `(2)` are superseded design drafts (generator-default identity `my-project`); `(2)` adds a `PROJECT_SUMMARY.md`. Both are committed to git but dead.
- **Safe cleanup actions:** Move `(1)` and `(2)` to `legacy/ui-drafts/` (preserve git history) and remove from the build root. Risk: LOW (no references). Confirm with a human that no design asset still needed lives only in a draft before archiving.

## 2.4 Virtual environment — `graduation/`

**Evidence (measured):**
- Contents: `Lib/site-packages/`, `Scripts/`, `share/` — 21,214 files, 406.8 MB. This is the standard layout of a **Python virtual environment** (Conda/venv) holding all runtime dependencies (confirmed `pyotp`, `playwright`, `pyttsx3`, etc. present).
- Git: `git ls-files -- "graduation/*"` → **0 tracked files** (untracked).
- Reproducibility: four lockfiles exist at root — `environment_main.yml`, `environment_main_locked.yml`, `environment_xtts.yml`, `environment_xtts_locked.yml` — sufficient to recreate it.

**Conclusions:**
- **Is it a virtualenv?** Yes.
- **Reproducible?** Yes, from the `environment_*_locked.yml` specs.
- **Should it remain inside the repo?** **No.** It should stay **local-only and never committed.** It is untracked today, but `.gitignore` does **not** list `graduation/` explicitly (it relies on generic `lib/` / `venv/` patterns, which do not robustly match a venv named `graduation/` on every platform). **Recommendation:** add an explicit `graduation/` entry to `.gitignore` (Phase 11) to guarantee it can never be accidentally committed. Do not archive — recreate from env files.

---

# PART 3 — DEPLOYMENT INVENTORY

## A) DEPLOYMENT-CRITICAL — required to run in production

| Item | Why critical |
|---|---|
| `backend/` (application code; excluding heavy local data subdirs) | Core RAG server. |
| `Login_system/` | Auth + serves frontend. |
| `assistify-ui-design/` (source + built `out/`) | The shipped UI. |
| `tts_service/`, `xtts_service/` | Voice services. |
| `TTS/` (if confirmed an active import) | Adapter shim. |
| `config.py` | App configuration. |
| `.env` (local, secret) | Runtime secrets. |
| `environment_main*.yml`, `environment_xtts*.yml` | Recreate runtime env. |
| `start_main_servers.py`, `start_piper_service.bat`, `scripts/launch_windows/` | Launchers. |
| Operational `scripts/` (launch, migrate, reindex, verify) | Deploy/ops. |
| `models/` (piper voices) | Voice runtime asset (local). |
| `Qwen2.5-7B-GGUF/` (LLM weights) | LLM inference asset (local, never committed). |
| `chroma_db_production/` | Production vector index (rebuildable but protect). |

## B) DEVELOPMENT-ONLY — needed for dev, not deployment

| Item | Why |
|---|---|
| `graduation/` | Local dev venv (recreate from env files in prod). |
| `.vscode/` | Editor config. |
| `conftest.py` | Test harness config. |
| `tools/` | Dev diagnostics/probes. |
| `docs/` | Developer/maintainer docs. |
| `.env.example` | Onboarding template. |
| `.claude/`, `.remember/`, `.planning/`, `.cursorrules`, `AGENT_TASK_PROMPT.md`, `AI_AGENT_RULES.md` | Agent/dev tooling state & guidance. |
| `environment_*_locked.yml` | Dev pinning (also deployment-relevant). |

## C) TESTING-ONLY — tests, validation, debugging, audits, experiments

| Item | Why |
|---|---|
| `tests/` | Pytest suite. |
| Root validation scripts: `hotswap_validation.py`, `phase2_validation.py`, `phase3_validation.py`, `verify_rag_standalone.py`, `validate_ws.py`, `collect_evidence.py`, `run_all.py`, `run_all_queries.py` | Validation/eval drivers. |
| Root one-off debug scripts: `check_chunk8.py`, `check_page2.py`, `dump_chunks_sql_v3.py`, `find_6ms.py`, `find_chunk_by_text.py`, `find_rank1.py`, `get_ans.py`, `get_chunk6.py`, `get_chunks.py`, `get_chunks_8_9_10.py`, `inspect_chunks.py`, `query_final.py`, `query_test.py`, `query_ws.py`, `scan_pdf.py`, `search_all_chunks.py`, `test_list_patch.py`, `test_search.py`, `trace_ext.py`, `trace_ws_route.py` | Ad-hoc inspection probes. |
| `playwright.py`, `pyotp.py`, `pyttsx3.py`, `reportlab.py` | Stub/"static analysis" helpers (HAZARDOUS at root — see 2.2). |
| `assistify_refactor_audit/` (+ `.zip`), `phase9_repo_audit/` | Audit snapshots. |
| `Json/`, `Notepad_Test_Results/`, `scratch/`, `tmp/`, `LOGSS/`, `logs/` | Test/eval output & logs. |
| `non_functional/` | Parked experimental code. |

## D) ARCHIVAL — should be archived, not in root

| Item | Why |
|---|---|
| `Backup/` (~21.5 GB) | Cold-storage recovery point; off-repo. |
| `TTS_local_backup/` | Backup assets. |
| `archived_pdfs/` | Source-PDF snapshot. |
| `assistify_refactor_audit/`, `assistify_refactor_audit.zip` | Audit dumps. |
| `assistify-ui-design (1)`, `assistify-ui-design (2)` | Superseded UI drafts. |
| Historical reports: `BUGFIX_LIST_QUERIES_SUMMARY.md`, `EVIDENCE_REPORT.md`, `RAW_EVIDENCE_FINAL.md`, `PATCHES_APPLIED.md`, `PHASE_AR0_ANALYSIS_REPORT.md`, `PHASE_AR1B_FINAL_REPORT.md`, `UPSTREAM_PATCH_BUNDLES.md`, `Repository_Classification_Report.md` | Point-in-time documents. |
| `repo_tree.txt`, `output.txt`, `phase2_validation_output.txt`, `temp_phase15c_pre_out.txt` | Generated dumps (delete, not even archive). |

---

# PART 4 — FINAL TARGET STRUCTURE

```
assistify/
├── backend/                 # application code only (heavy data moved to data/)
├── Login_system/
├── frontend/                # = current assistify-ui-design
├── data/
│   ├── chroma/              # chroma_db/, chroma_db_production/
│   ├── uploads/             # backend upload/asset dirs
│   ├── archives/            # archived_pdfs/ (active reference copy)
│   └── cache/               # logs/, LOGSS/, transient caches
│
├── docs/
│   ├── architecture/        # Repository_Classification_Report.md, Cleanup_Plan.md, DIAGRAMS.md
│   ├── deployment/          # LAUNCHER_README.md, env/setup docs
│   ├── api/                 # API reference docs
│   └── archive/             # historical phase reports, AGENT_*/AI_AGENT_RULES
│
├── scripts/
│   ├── dev/                 # dev-only helper scripts
│   ├── deployment/          # start_main_servers.py, start_piper_service.bat, launch_windows/
│   └── maintenance/         # migrations, reindex, verify_*
│
├── tools/
│   ├── experiments/         # root one-off debug/query/trace scripts, scripts/_* probes
│   └── diagnostics/         # tools/testing/*, phase9_repo_audit/, stub modules (isolated)
│
├── tests/                   # pytest suite + conftest.py
├── deployment/              # environment_*.yml, docker-compose.yml (new), deploy manifests
├── legacy/                  # non_functional/, assistify-ui-design (1)&(2), nested-repo remnants
├── archive/                 # assistify_refactor_audit/ (+zip), TTS_local_backup/
│
├── README.md
├── .env.example
└── docker-compose.yml       # NEW (Phase 11)
```

**Mapping — every current top-level item → future location:**

| Current item | Future location | Action |
|---|---|---|
| `backend/` | `backend/` | keep; split out data subdirs → `data/` |
| `Login_system/` | `Login_system/` | keep |
| `assistify-ui-design/` | `frontend/` | rename/move |
| `assistify-ui-design (1)` | `legacy/ui-drafts/` | archive |
| `assistify-ui-design (2)` | `legacy/ui-drafts/` | archive |
| `tts_service/` | `backend/` peer (or `services/`) | keep |
| `xtts_service/` | `backend/` peer (or `services/`) | keep |
| `TTS/` | keep (verify) / `legacy/` | review |
| `config.py` | root (or `backend/`) | keep |
| `conftest.py` | `tests/` (or root) | keep |
| `tests/` | `tests/` | keep |
| `tools/` | `tools/diagnostics/` + `tools/experiments/` | reorganize |
| `scripts/` | `scripts/{dev,deployment,maintenance}/` | reorganize |
| `scripts/launch_windows/` | `scripts/deployment/launch_windows/` | move |
| `docs/` | `docs/{architecture,deployment,api,archive}/` | reorganize |
| `chroma_db/` | `data/chroma/` | move (local) |
| `chroma_db_production/` | `data/chroma/` | move (local, protect) |
| `models/` | `data/` model assets | move (local) |
| `Qwen2.5-7B-GGUF/` | local asset (out of tree ideally) | keep local, never commit |
| `graduation/` | local venv (gitignore explicitly) | keep local |
| `logs/`, `LOGSS/` | `data/cache/` | move + rotate |
| `Json/` | `data/cache/` or delete | clear |
| `tmp/` | — | delete |
| `scratch/` | `tools/experiments/` (keepers) | clear |
| `Notepad_Test_Results/` | `archive/` (if needed) | clear |
| `archived_pdfs/` | `data/archives/` (+ `archive/`) | move |
| `Backup/` | off-repo cold storage | move out |
| `TTS_local_backup/` | `archive/` / off-repo | move |
| `assistify_refactor_audit/` (+ `.zip`) | `archive/audits/` | move |
| `phase9_repo_audit/` | `tools/diagnostics/` or `docs/archive/` | move |
| `non_functional/` | `legacy/` | move |
| `assistify-rag-project-main/` (nested) | — | delete (after review) |
| `playwright.py`, `pyotp.py`, `pyttsx3.py`, `reportlab.py` | `tools/diagnostics/stubs/` or delete | review (HIGH priority) |
| `environment_*.yml` (×4) | `deployment/` | move |
| `start_main_servers.py`, `start_piper_service.bat` | `scripts/deployment/` | move |
| Root validation scripts | `tests/` or `scripts/maintenance/` | move |
| Root one-off debug scripts | `tools/experiments/` | move |
| `cleanup_repo.py`, `collect_evidence.py` | `scripts/maintenance/` | move |
| Historical `*.md` reports | `docs/archive/` | move |
| `README.md`, `.env.example` | root | keep |
| `.env`, `._assistify_session_secret` | local, never commit | keep local |
| `*.txt` dumps (`repo_tree.txt`, etc.) | — | delete |
| `.git/`, `.gitignore`, `.cursorrules`, `.vscode/`, `.planning/`, `.claude/`, `.remember/` | root | keep |

---

# PART 5 — CLEANUP ACTIONS

> All actions below are **proposals for later phases**. Nothing is executed in Phase 9B.

## A) Safe-To-Move (git mv / relocate; reversible)

| Item | Destination | Risk | Reason | Expected impact |
|---|---|---|---|---|
| `assistify-ui-design/` → `frontend/` | `frontend/` | MEDIUM | Standardize structure. | **Must update path refs** in `react_ui_build.py`, `verify_stack.py`, `verify_react_routes.py`, `project_start_server.py`. |
| `environment_*.yml` (×4) | `deployment/` | LOW | Group deploy specs. | Update setup docs. |
| `start_main_servers.py`, `start_piper_service.bat` | `scripts/deployment/` | LOW–MED | Group launchers. | Update launch docs/shortcuts. |
| Root validation scripts (`*_validation.py`, `verify_rag_standalone.py`, `validate_ws.py`, `run_all*.py`, `collect_evidence.py`) | `tests/` or `scripts/maintenance/` | LOW | De-clutter root. | Update any direct invocations. |
| Root one-off debug scripts (`check_*`, `find_*`, `get_*`, `query_*`, `trace_*`, `inspect_*`, `scan_pdf.py`, `search_all_chunks.py`, `dump_chunks_sql_v3.py`) | `tools/experiments/` | LOW | They are probes. | None on runtime. |
| `cleanup_repo.py` | `scripts/maintenance/` | LOW | Maintenance utility. | Update its own ignore-path assumptions. |
| Historical `*.md` reports | `docs/archive/` | LOW | Archive docs. | None. |
| `chroma_db/`, `chroma_db_production/`, `models/`, `archived_pdfs/`, `logs/`, `LOGSS/` | `data/...` | MEDIUM | Centralize data. | **Update path config** in backend/launchers (these are referenced at runtime). |
| `non_functional/` | `legacy/` | NONE | Already parked. | None. |
| `assistify_refactor_audit/`, `phase9_repo_audit/` | `archive/audits/` | LOW | Audit snapshots. | None. |

## B) Safe-To-Archive (move out of root / to cold storage)

| Item | Destination | Risk | Reason | Expected impact |
|---|---|---|---|---|
| `Backup/` (~21.5 GB) | off-repo cold storage | LOW (runtime) | Huge recovery snapshot; doesn't belong in repo. | ~21.5 GB freed; keep an external copy. |
| `TTS_local_backup/` | `archive/` / off-repo | LOW | Backup assets. | Minor. |
| `assistify-ui-design (1)`, `(2)` | `legacy/ui-drafts/` | LOW | Dead UI drafts. | None (unreferenced). |
| `Qwen2.5-7B-GGUF/` | local asset store (out of tree) | MEDIUM | Re-downloadable weights. | LLM path config update if relocated. |
| `assistify_refactor_audit.zip` | `archive/audits/` | LOW | Zipped snapshot. | None. |

## C) Safe-To-Delete (disposable / regenerable; git-ignored)

| Item | Risk | Reason | Expected impact |
|---|---|---|---|
| `tmp/` (200 files, 80 MB) | NONE | Pure scratch. | 80 MB freed. |
| `repo_tree.txt` (6.2 MB), `output.txt`, `phase2_validation_output.txt`, `temp_phase15c_pre_out.txt` | NONE | Generated dumps. | ~7 MB freed. |
| `.pytest_cache/`, `__pycache__/` | NONE | Regenerated caches. | Minor. |
| `Json/` (112 files) | NONE | Eval outputs; archive any needed evidence first. | <1 MB. |
| `Notepad_Test_Results/`, `scratch/` (non-keepers) | NONE–LOW | Console captures / probes. | Minor. |
| `LOGSS/`, `logs/` contents | NONE | Rotatable logs. | ~7 MB. |
| `assistify-rag-project-main/` (nested stray sqlite) | LOW | Accidental artifact (Part 2.1); confirm sqlite not needed. | ~0.2 MB; removes confusing self-nesting. |

## D) Requires-Human-Review (do NOT auto-act)

| Item | Risk | Reason | Expected impact if mishandled |
|---|---|---|---|
| `playwright.py`, `pyotp.py`, `pyttsx3.py`, `reportlab.py` | **HIGH** | Import-shadowing of real libs incl. **MFA in `login_server.py`**; `pyotp` stub returns constant `"000000"`. | Wrong removal/keep could break auth or hide a security defect. |
| `pyotp` MFA call path in `Login_system/login_server.py` | **HIGH** | Verify it binds to the real `pyotp` (`pyotp.totp.TOTP(...).provisioning_uri`) and not the stub. | Auth enrollment failure / TOTP bypass. |
| `TTS/` (local package) | MEDIUM | Confirm it is the intended import vs shadowing Coqui `TTS`. | Voice import breakage. |
| `chroma_db_production/` | MEDIUM–HIGH | Confirm regenerable vs protected production state before any move. | Loss of production index. |
| `._assistify_session_secret` | MEDIUM | Possible secret. | Secret leak if committed. |
| `.env` | HIGH | Live secrets. | Secret leak. |
| `Qwen2.5-7B-GGUF/` relocation | MEDIUM | 5 GB asset with its own `.git`. | LLM inference path break. |
| `config.py` / `conftest.py` relocation | MEDIUM | Import roots; many references. | Broad import breakage. |

---

# PART 6 — REPOSITORY SIZE REDUCTION

**Baseline (measured): ~49 GB on disk, 36 top-level dirs, ~60 top-level files.**

### Files removed from root (relocated or deleted)
- **~45–50 top-level files** leave root: 4 shadow stubs, ~21 one-off debug scripts, ~8 validation scripts, ~7 historical `.md` reports, 4 env `.yml`, 2 launchers, 4 `.txt` dumps, plus `cleanup_repo.py`/`collect_evidence.py`/audit zip.
- Root retains roughly: `README.md`, `.env.example`, `.env`, `.gitignore`, `.cursorrules`, `config.py`, `docker-compose.yml` (new), and dot-dirs.

### Folders removed from root
- **~22 of 36 top-level directories** leave root (moved to `data/`, `docs/`, `scripts/`, `tools/`, `tests/`, `deployment/`, `legacy/`, `archive/`, or off-repo): `assistify-ui-design (1)`, `(2)`, `assistify_refactor_audit`, `phase9_repo_audit`, `Backup`, `TTS_local_backup`, `archived_pdfs`, `Json`, `tmp`, `scratch`, `Notepad_Test_Results`, `LOGSS`, `logs`, `chroma_db`, `chroma_db_production`, `models`, `non_functional`, nested `assistify-rag-project-main`, `environment` group, etc.

### Estimated size reduction
| Bucket | Approx size | Effect |
|---|---|---|
| Archive out-of-repo (`Backup/`) | ~21.5 GB | repo footprint −21.5 GB |
| Relocate model/weights local (`Qwen2.5-7B-GGUF/`) | ~5.0 GB | tree −5.0 GB (kept local) |
| Delete disposable (`tmp/`, `*.txt`, caches, `Json/`, logs) | ~95 MB | permanent −~95 MB |
| Archive dup UIs + audits | ~13 MB | root −13 MB |
| **Root working tree after cleanup** | **~22–23 GB** (backend + frontend + venv + models + chroma) | from ~49 GB |
| **Git-tracked repo** (excl. ignored venv/models/backup) | shrinks notably by dropping 2 dup UIs (75 tracked files) + ~50 root scripts/reports | cleaner clone |

> Net: **~26–27 GB removable from the repo tree** (mostly `Backup/` + weights moved to external/local-only storage), and a far cleaner git-tracked surface.

### Estimated deployment simplification
- A production checkout no longer carries: 2 dead UIs, ~50 root debug/validation scripts, 4 dangerous import stubs, multi-GB backups, audit dumps, and scattered logs/eval JSON.
- Deploy artifact = `backend/` + `Login_system/` + `frontend/out/` + services + `deployment/` (`environment_*.yml`, `docker-compose.yml`) + local data/model mounts. Estimated **>90% reduction in deploy-irrelevant files** and elimination of the import-shadowing class of bugs.

---

# PART 7 — EXECUTION ROADMAP

> Each phase is gated by validation and is reversible (git history + off-repo backups). Phase 9B remains report-only.

## Phase 10 — Repository Cleanup

**Objectives:** Remove disposable clutter and establish the target folder skeleton without touching runtime behavior.

**Expected changes:**
- Delete safe-to-delete items (`tmp/`, `*.txt` dumps, caches, nested stray sqlite after confirmation).
- Move historical `.md` reports → `docs/archive/`; audit snapshots → `archive/audits/`.
- Move dup UIs (`(1)`,`(2)`) → `legacy/ui-drafts/`; `non_functional/` → `legacy/`.
- Consolidate root one-off scripts → `tools/experiments/`, validation scripts → `tests/`/`scripts/maintenance/`.
- Add explicit `.gitignore` entries (`graduation/`, `assistify-rag-project-main/`, etc.).

**Risks:** Accidentally moving a referenced script; deleting an index still needed. **Mitigation:** grep references before each move; confirm `chroma_db*`/sqlite with a human.

**Validation requirements:**
- `git status` clean & intentional; nothing deployment-critical relocated yet.
- Full pytest suite passes; launchers still start (`project_start_server.py`).
- UI still builds/serves (unchanged paths in Phase 10).

## Phase 11 — Deployment Hardening

**Objectives:** Eliminate runtime hazards and externalize heavy/secret assets.

**Expected changes:**
- **Resolve package shadowing (Part 2.2):** remove/relocate `playwright.py`, `pyotp.py`, `pyttsx3.py`, `reportlab.py`; verify `login_server.py` MFA binds to the real `pyotp`; add a CI guard against root-module/PyPI name collisions.
- Move `Backup/` to off-repo cold storage; relocate `Qwen2.5-7B-GGUF/` and `models/` to local-only asset mounts; ensure `graduation/` is git-ignored.
- Introduce `deployment/` (`environment_*.yml`, `docker-compose.yml`) and a minimal production env contract from `.env.example`.
- Verify `._assistify_session_secret`/`.env` are never tracked.

**Risks:** Auth regression if the real `pyotp` path is wrong; LLM/voice path breakage when assets move; production index loss.
**Validation requirements:** MFA enrollment + TOTP verify works against real `pyotp`; LLM + TTS/XTTS smoke tests; security scan confirms no secrets tracked; `chroma_db_production/` reachable from new path.

## Phase 12 — Production Structure Finalization

**Objectives:** Land the Part 4 target layout and make the canonical structure authoritative.

**Expected changes:**
- Rename `assistify-ui-design/` → `frontend/`; relocate data dirs → `data/{chroma,uploads,archives,cache}`; finalize `scripts/{dev,deployment,maintenance}` and `tools/{experiments,diagnostics}`.
- Update **all** path references (build/verify/launch scripts, backend config) to the new layout in one coordinated change.
- Refresh `README.md` + `docs/{architecture,deployment,api}` to match.

**Risks:** Broad path-reference breakage (frontend `out/`, data dirs, config import roots).
**Validation requirements:** End-to-end run from a fresh clone + `environment_*_locked.yml`: env builds, UI builds & serves at `/frontend/`, RAG query path works, voice works, full test suite green, deploy via `docker-compose` (or documented equivalent) succeeds.

---

## Compliance Assessment (per core engineering rule)

1. **Genericity Assessment — PASS.** All classifications use content-agnostic signals (structure, file type, git tracking, `.gitignore`, byte sizes, `package.json` identity, script references). No rule keys on any company, product, document, dataset, metric, or hardcoded value.
2. **Evidence-Origin Assessment — PASS.** Every finding cites observable evidence: `git ls-files` counts, recursive directory listings, measured sizes, stub file contents, and grep'd import references in `login_server.py` and `scripts/`.
3. **Future-Document Compatibility Assessment — PASS.** The structure, categories, and roadmap apply to any future content; a brand-new document/domain added tomorrow would be classified by the same structural signals with no code path depending on known content.

**This phase made no modifications. `Cleanup_Plan.md` is the sole output.**
