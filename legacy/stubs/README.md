# Deactivated Import-Collection Stubs

These files were previously located at the repository root, where their filenames
collided with installed/optional third-party distributions. Because several
entrypoints place the repo root on `sys.path[0]` (via `-m uvicorn`, `PYTHONPATH`,
or the pytest `conftest.py`), the root stubs would *shadow* the real packages and
silently replace them with non-functional placeholders.

They are preserved here (not deleted) for historical reference. Living under
`legacy/stubs/` keeps them off `sys.path`, so they can no longer shadow real
packages during any startup or test run.

| File | Original role | Why deactivated |
|---|---|---|
| `pyotp.py` | Fake TOTP placeholder | Shadowed real `pyotp`, breaking production MFA. Real `pyotp` is now installed; see `Phase11B_Deployment_Hardening_Report.md`. |
| `playwright.py` | Import placeholder | Dead code; only importer is a standalone script run outside the repo root. |
| `pyttsx3.py` | Import placeholder | Dead code; only importer is a one-off tool script run outside the repo root. |
| `reportlab.py` | Import placeholder | Test-only; importers guard with `try/except ImportError` and fall back. |
| `TTS/` | Fake Coqui-TTS placeholder (`api.TTS` returns empty bytes) | Shadowed real `TTS` package used by `xtts_service`; broke GPU voice synthesis when repo root was on `sys.path`. |

Do not re-add any of these names as modules or packages at the repository root.
