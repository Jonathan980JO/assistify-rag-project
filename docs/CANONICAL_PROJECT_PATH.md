# Canonical project location

Use **one** working copy of Assistify per machine.

## Active project (code + data)

Clone or extract the repository to a path of your choice, then run all commands from that folder:

```powershell
cd path\to\assistify-rag-project-main
```

## Data directories

Keep runtime data under the project root (or override via `.env`):

| Path | Purpose |
|------|---------|
| `Login_system/users.db` | Auth database (created on first run) |
| `backend/chroma_db_v3/` | Vector store (created on first index) |
| `backend/assets/` | Uploaded knowledge-base files |
| `models/` | Downloaded AI models (Whisper, Piper, etc.) |
| `logs/` | Service logs |

Set `WHISPER_MODEL_PATH`, `CHROMA_DB_PATH`, and `ASSETS_DIR` in `.env` if you use a non-default layout.

## Before starting servers

1. Copy `.env.example` to `.env` and set `SESSION_SECRET`.
2. Run `python scripts/preflight_check.py`.
3. See [SETUP_WINDOWS.md](SETUP_WINDOWS.md) for the full install guide.
