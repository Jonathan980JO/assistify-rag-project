# Assistify v1.0 — Local setup and run guide (Windows)

Assistify is a help-desk stack with several services started by one launcher:

| Service | Port (default) | Role |
|---------|----------------|------|
| **Login** | `7001` | Auth, sessions, Web UI entry |
| **RAG** | `7000` | Retrieval, speech, chat WebSocket |
| **LLM API** | `8000` or `8010` | Thin API in front of **Ollama** (optional shim) |
| **Piper TTS** | `5002` | Voice output (CPU; optional if models missing) |
| **Ollama** | `11434` | LLM inference (**GPU**) |

**Inference** is handled by **[Ollama](https://ollama.com)** on `http://127.0.0.1:11434`, not by local GGUF files in `backend/Models`.

**GPU policy:** GPU is reserved for **Ollama (LLM)** and **RAG embeddings**. Voice STT (Whisper) and Piper TTS run on **CPU** so VRAM stays free for chat and retrieval.

```
Browser → Login (7001) → RAG (7000) → Ollama (11434, GPU)
                              ↓
                        Piper TTS (5002, CPU)
              ↑ optional LLM shim (8000/8010)
```

---

## Prerequisites

Install before you start:

- **Windows 10/11**
- **[Miniconda](https://docs.conda.io/en/latest/miniconda.html)** (or Anaconda)
- **[Node.js](https://nodejs.org/)** (LTS) — required to build the React UI (`assistify-ui-design/`)
- **[Git](https://git-scm.com/download/win)** (optional, for clones)
- **NVIDIA GPU + driver** (recommended; CPU-only is slower)
- **[Ollama for Windows](https://ollama.com)** — must be running while you use the app

**Hardware:** 16 GB RAM minimum; **6 GB VRAM** works if you use a small Ollama model (e.g. `qwen2.5:3b`).

---

## 1. One-time setup

Open **PowerShell** and go to the project root (adjust the path if yours differs):

```powershell
cd path\to\assistify-rag-project-main
```

### 1.1 Create the Conda environment

```powershell
conda env create -f environment_main.yml
```

This creates **`assistify_main`** with **Python 3.11** and most dependencies.

If the environment already exists:

```powershell
conda activate assistify_main
```

Verify:

```powershell
python --version
# Expected: Python 3.11.x
```

### 1.2 Extra Python packages (known gaps)

Still with `assistify_main` active:

```powershell
pip install itsdangerous authlib pdfplumber
pip install "setuptools<81"
```

`setuptools<81` avoids `pkg_resources` issues with **faster-whisper** / **ctranslate2** on some installs.

### 1.3 Environment file

```powershell
copy .env.example .env
```

Edit `.env` for local dev (recommended):

```env
ENVIRONMENT=development
OLLAMA_MODEL=qwen2.5:3b
KMP_DUPLICATE_LIB_OK=TRUE
```

For **6 GB VRAM**, prefer **`qwen2.5:3b`** over the default `qwen2.5:7b` in `config.py`.

If port **8000** is blocked on Windows, add:

```env
LLM_SERVER_PORT=8010
LLM_SERVER_URL=http://127.0.0.1:8010
```

### 1.4 Broken `graduation` virtualenv (if present)

If `graduation\pyvenv.cfg` points at another PC's paths, **delete the whole `graduation` folder**. The launcher will use your active Conda Python instead.

### 1.5 Ollama model

Start Ollama (tray app or `ollama serve`), then:

```powershell
ollama pull qwen2.5:3b
```

Use the same tag as **`OLLAMA_MODEL`** in `.env` / `config.py`.

### 1.6 Knowledge base (sample documents)

Loads **10 built-in support snippets** into Chroma (no PDF required):

```powershell
conda activate assistify_main
python -m backend.load_documents
```

### 1.7 Login database (bootstrap superadmin)

```powershell
python Login_system\init_users_db.py
```

Creates `Login_system\users.db` with a single bootstrap account:

| Username | Password | Role |
|----------|----------|------|
| `superadmin` | `superadmin` | superadmin |

All other roles (Master Admin, Admin, Employee, Customer) are created through the UI and APIs after login. Passwords are stored as bcrypt hashes (see `Login_system/init_users_db.py`).

---

## 2. Run the project (every session)

Use **one PowerShell window** for the launcher. Always run from the **project root** (see `docs/CANONICAL_PROJECT_PATH.md` if you moved the folder).

The launcher **builds the React UI** (`assistify-ui-design/out/`) and serves it as the **only** web UI at `/frontend/*` on port **7001**. Legacy Jinja/HTML pages have been removed.

### 2.1 Before you start (checklist)

1. **Conda env** — `conda activate assistify_main`
2. **Ollama** — tray app running, or let the launcher start it (default)
3. **Model pulled** — `ollama pull qwen2.5:3b` (must match `OLLAMA_MODEL` in `.env` / `config.py`)
4. **Knowledge base** — run section 1.6 once if you have not loaded sample docs
5. **Users DB** — run section 1.7 once if `Login_system\users.db` does not exist

Optional sanity check:

```powershell
python scripts\preflight_check.py
```

### 2.2 Start all servers (recommended)

**One command** from the project root (no `conda activate` needed — the launcher finds `assistify_main` automatically):

```powershell
python start_main_servers.py
```

**Default on Windows:** a **coordinator** window scans ports, prints a process inventory table, then opens **one terminal per service**:

| Window title | Service | Port |
|--------------|---------|------|
| Assistify Ollama | Ollama | 11434 |
| Assistify Piper | Piper TTS | 5002 |
| Assistify LLM | LLM shim | 8010 |
| Assistify | RAG server | 7000 |
| Assistify Login | Login UI | 7001 |

Services already listening are skipped. The coordinator waits until each reports **Ready**, then prints http://127.0.0.1:7001/login. **Close each `Assistify *` window** to stop that service; Ctrl+C in the coordinator only exits the coordinator.

**List running processes without starting anything:**

```powershell
python start_main_servers.py --status
```

**Previous single-window behavior** (merged `[RAG]` / `[LOGIN]` logs in one console — useful for CI or SSH):

```powershell
python start_main_servers.py --single-console
```

This sets `KMP_DUPLICATE_LIB_OK=TRUE` and frees occupied ports (`--kill-ports`) by default. First RAG start can take several minutes while faster-whisper loads.

Then open **http://127.0.0.1:7001/login** (`superadmin` / `superadmin`).

Per-service logs (single-console mode) are written under `logs\` (`piper.log`, `llm.log`, `rag.log`, `login.log`).

**Advanced / manual equivalent** (if you prefer explicit conda activation):

```powershell
cd path\to\assistify-rag-project-main
conda activate assistify_main
$env:KMP_DUPLICATE_LIB_OK = "TRUE"
python scripts\project_start_server.py --kill-ports --llm-port 8010
```

| Flag | When to use |
|------|-------------|
| **`--status`** | Print port/PID inventory only; do not start services |
| **`--single-console`** | One window with merged logs (old launcher) |
| **`--kill-ports`** | Frees `5002`, `7000`, `7001`, `8010` if a previous run left listeners behind |
| **`--llm-port 8010`** | Use when port **8000** fails with "permission denied" on Windows; set `LLM_SERVER_URL=http://127.0.0.1:8010` in `.env` to match |

Pass extra flags through the one-liner, e.g. `python start_main_servers.py --no-piper`.

### 2.3 Open the app

| URL | Purpose |
|-----|---------|
| http://127.0.0.1:7001/login | **Staff / admin UI** (redirects to React `/frontend/login/`) |
| http://127.0.0.1:7001/frontend/guest/ | **Customer chat (no login)** — tenant selector + RAG |
| http://127.0.0.1:7001/frontend/ | Authenticated chat UI (after login) |
| http://127.0.0.1:7000/health | RAG health check |
| http://127.0.0.1:5002/health | Piper TTS health (optional) |
| http://127.0.0.1:8010/internal/gpu-status | LLM shim status (if using port 8010) |

Log in with **`superadmin` / `superadmin`** (bootstrap account). After code or frontend changes, hard refresh the browser (**Ctrl+F5**). For a clean chat history, use **+ New Chat** in the sidebar.

### 2.4 Alternative launcher options

Flags can be passed via `python start_main_servers.py <flags>` or directly to `project_start_server.py`.

**Ollama + RAG only** (skip the FastAPI LLM shim; RAG talks to Ollama directly):

```powershell
python start_main_servers.py --no-llm
```

**No voice output** (skip Piper on 5002; chat still works, browser TTS may be used):

```powershell
python start_main_servers.py --no-piper
```

**Ollama already running** (do not start a second Ollama process):

```powershell
python start_main_servers.py --no-ollama
```

**Development** (auto-reload on code changes):

```powershell
python start_main_servers.py --reload
```

Do **not** run `start_xtts_service.bat.disabled` unless you explicitly want the legacy XTTS GPU service instead of Piper.

---

## 3. PDF and knowledge-base testing

**Default KB:** `python -m backend.load_documents` does **not** ingest PDFs; it loads text from code.

**PDF support** exists via the RAG server / admin upload flow and `backend/pdf_ingestion_rag.py`.

**Sample PDFs in the repo:**

- `tmp_test_pdfs\management_test.pdf`
- `tmp_test_pdfs\psychology_test.pdf`

Upload them through the **admin knowledge** UI (when logged in as admin), or place assets per your deployment docs and reindex.

**Good manual test questions** (after sample KB load):

- "How many days do I have to return a product?" → **30 days**
- "How do I reset my password?" → forgot-password / email steps
- "When is shipping free?" → **orders over $50**

---

## 4. Run tests (optional)

From project root with `assistify_main` active:

```powershell
$env:PYTHONUTF8 = "1"
python tests\test_system_integrity.py
python tests\test_edge_cases.py
python tests\test_toon.py
python tests\test_toon_integration.py
```

Skip **`tests\test_arabic_tts.py`** unless a TTS service is running on **port 5002** (Piper/XTTS).

Run most tests (excluding Arabic TTS):

```powershell
Get-ChildItem tests\test_*.py | Where-Object { $_.Name -ne "test_arabic_tts.py" } | ForEach-Object { python $_.FullName }
```

---

## 5. Troubleshooting

| Symptom | What to try |
|---------|-------------|
| `can't open file ... scripts\project_start_server.py` | `cd` into the **project root** where `start_main_servers.py` lives (see [CANONICAL_PROJECT_PATH.md](CANONICAL_PROJECT_PATH.md)). |
| Launcher exits immediately / "All servers stopped" | Check `logs\rag.log` and `logs\piper.log`; ensure Ollama is running and the model is pulled. |
| RAG stuck starting / long first boot | Normal on first run while faster-whisper downloads; wait up to ~10 minutes or check `logs\rag.log`. |
| `$env:KMP_DUPLICATE_LIB_OK` error in **cmd** | Use PowerShell, or `set KMP_DUPLICATE_LIB_OK=TRUE` in cmd. |
| No module named 'backend' in tests | Run tests from repo root; use updated test files that set `sys.path` to parent of `tests/`. |
| LLM empty / connection errors | Start **Ollama**; run `ollama pull qwen2.5:3b`; check `OLLAMA_MODEL` matches. |
| Ollama warmup 404 for model | Run `ollama pull` for the exact tag in `config.py` / `.env`. |
| Port **8000** permission denied | Use `--llm-port 8010` and set `LLM_SERVER_URL=http://127.0.0.1:8010` in `.env`. |
| OpenMP / crash with whisper + torch | `$env:KMP_DUPLICATE_LIB_OK = "TRUE"` (also in `.env`). |
| `passlib` / `bcrypt` version warning | Harmless if login works; optional: `pip install "bcrypt<4.1"`. |
| Piper / TTS warnings on **5002** | Optional; chat works without server TTS (browser fallback). Use `--no-piper` to skip. |
| Voice stuck on "Thinking…" / "Speaking…" | Hard refresh (**Ctrl+F5**); restart launcher; check browser mic/speech permissions. |
| Old blunt replies in chat | Start **+ New Chat**; older threads may have cached answers from before router fixes. |
| Greeting + question gets no KB answer (e.g. `hello what is X`) | Mixed messages are auto-normalized before RAG (`backend/rag_query_prep.py`). Restart the RAG server after updates. Set `RAG_QUERY_LLM_PREP=true` in `.env` for messy multi-clause messages. |
| Typo in question returns "don't have that specific detail…" | Typos are corrected against uploaded KB terms (e.g. `gazoline` → `gasoline`). Use **+ New Chat** if an old thread cached a miss. |
| `graduation` venv broken | Delete `graduation\`; use Conda only. |
| Moved project or large folders to another drive | See `docs/CANONICAL_PROJECT_PATH.md`; run `python scripts/preflight_check.py`. |

---

## 6. Project layout (short)

```
assistify-rag-project-main/
├── assistify-ui-design/     # React/Next.js UI (static export → out/)
├── backend/                 # RAG server, routers, services, voice_audio/
├── Login_system/            # Login server, users.db (API + serves React /frontend/)
├── tts_service/             # Piper TTS microservice (port 5002)
├── scripts/
│   ├── project_start_server.py   # Multi-server launcher (used by start_main_servers.py)
│   ├── react_ui_build.py         # npm install + build for React UI
│   └── preflight_check.py        # Pre-start sanity check
├── start_main_servers.py         # Recommended one-command project start
├── logs/                    # Per-service logs (created at runtime)
├── environment_main.yml     # Conda env definition
├── config.py                # Shared configuration (GPU policy, Ollama, Whisper)
├── .env.example             # Copy to .env
└── docs/                    # Additional documentation
```

---

## 7. Quick reference (daily use)

```powershell
cd path\to\assistify-rag-project-main
python start_main_servers.py
```

Wait for all services **Ready**, then open **http://127.0.0.1:7001/login** (`superadmin` / `superadmin`).

For more detail, see `docs/PROJECT_BRIEFING.md` and `docs/CANONICAL_PROJECT_PATH.md` (this project uses **Ollama** for the LLM).
