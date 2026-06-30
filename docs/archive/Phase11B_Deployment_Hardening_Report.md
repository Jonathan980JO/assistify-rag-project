# Phase 11B - Deployment Hardening Execution Report

- **Branch:** `refactor/architecture-v2`
- **Mode:** EXECUTION (changes applied + committed)
- **Date:** 2026-06-27
- **Input:** `Phase11A_Shadow_Module_Report.md`
- **Scope:** De-shadow the four root-level package-shadowing stubs (`pyotp.py`, `playwright.py`, `pyttsx3.py`, `reportlab.py`) by relocating them into `legacy/stubs/`, and remediate the broken production MFA path by installing/activating the real `pyotp` package. No backend business logic and no RAG behavior were modified. The nested `chroma.sqlite3` stray artifact was deliberately left untouched (out of scope).

---

## 0. Executive Summary

| Hazard (from 11A) | Action taken | Outcome |
|---|---|---|
| `pyotp.py` shadows real `pyotp`, breaking MFA | Installed real `pyotp==2.9.0`, added to env specs, moved stub to `legacy/stubs/`, reset stale MFA rows | MFA enrollment + OTP verification now functional; `pyotp` resolves to site-packages |
| `playwright.py` (dead code) | `git mv` to `legacy/stubs/` | No longer on `sys.path`; cannot shadow |
| `pyttsx3.py` (dead code) | `git mv` to `legacy/stubs/` | No longer on `sys.path`; cannot shadow |
| `reportlab.py` (test-only, fail-safe) | `git mv` to `legacy/stubs/` | No longer on `sys.path`; importers already fall back via `try/except` |

All four root-level `<pkgname>.py` shadowing files have been removed from the repository root. The repo root can no longer pre-empt installed distributions of these names during any `-m uvicorn` startup or pytest collection.

---

## 1. Actions Performed (chronological)

1. Confirmed branch `refactor/architecture-v2`, clean working tree (only the untracked `Phase11A_Shadow_Module_Report.md` present), and that all four stubs were git-tracked.
2. Created `legacy/stubs/` with a `README.md` documenting why these stubs are preserved-but-deactivated.
3. Re-verified, repo-wide, that no runtime module imports `playwright` / `pyttsx3` / `reportlab` (only non-runtime scripts/tools, with the `reportlab` importers guarded by `try/except ImportError`).
4. `git mv` of `playwright.py`, `pyttsx3.py`, `reportlab.py` into `legacy/stubs/`; `py_compile` each (exit 0).
5. Confirmed active interpreter is the `assistify_main` conda env; installed real `pyotp==2.9.0`.
6. Added `pyotp==2.9.0` to `environment_main.yml` (Authentication/security block) and `environment_main_locked.yml` (alphabetical position).
7. Inspected `Login_system/users.db`, derived the stub's bogus secret from the stub file itself, and reset any stale MFA rows matching it.
8. `git mv pyotp.py legacy/stubs/pyotp.py` to remove the shadow so the real package resolves.
9. Verified resolution + MFA enroll/verify paths; `py_compile Login_system/login_server.py` (exit 0).
10. Ran validation suite: import sanity, login + backend startup imports, route parity, py_compile.

---

## 2. Files Moved

| Original path | New path | Classification (11A) |
|---|---|---|
| `pyotp.py` | `legacy/stubs/pyotp.py` | ACTIVE (security-critical) -> deactivated, real package now used |
| `playwright.py` | `legacy/stubs/playwright.py` | DEAD CODE |
| `pyttsx3.py` | `legacy/stubs/pyttsx3.py` | DEAD CODE |
| `reportlab.py` | `legacy/stubs/reportlab.py` | TEST-ONLY (fail-safe) |

New file added: `legacy/stubs/README.md` (rationale + "do not re-add at root" note).

No importer scripts were modified: `scripts/playwright_test.py`, `tools/testing/pad_wav.py`, `scripts/full_regression_test.py`, and `scripts/test_pdf_fixes.py` run with their own script directory as `sys.path[0]`, so they never resolved to the root stub. The two `reportlab` importers additionally guard with `try/except ImportError` and fall back.

---

## 3. MFA Assessment

### 3.1 Pre-change state (confirmed broken)
The root `pyotp.py` stub was the module actually imported during production login startup (real `pyotp` was absent from `assistify_main`). The stub:
- `TOTP` had **no `verify`** -> `pyotp.TOTP(secret).verify(...)` raised `AttributeError`, caught at `login_server.py` L1709-1710 -> every MFA-enabled user was **locked out (fail-closed)**.
- `random_base32()` returned a **constant** (`"BASE32SECRET"`) -> all enrollments would share one hardcoded secret.
- Had **no `pyotp.totp` submodule** -> `enable_mfa` (L1894) raised `AttributeError` -> HTTP 500 (after the DB row had already been committed at L1888).

Decision: per the Phase 11B requirement, because MFA was provably broken, the real package was installed and the stub deactivated (full remediation).

### 3.2 Remediation
- `pyotp==2.9.0` installed into `assistify_main` and pinned in both environment specs.
- `pyotp.py` stub relocated to `legacy/stubs/` so the real package resolves (per 11A SS8, installing alone is insufficient while the root stub remains on `sys.path[0]`).
- No source change was needed in `login_server.py`: the MFA verify (L1704-1710) and `enable_mfa` (L1877-1895) handlers were already written against the real `pyotp` API (`TOTP.verify`, `random_base32`, `pyotp.totp.TOTP(...).provisioning_uri(...)`).

### 3.3 Stale MFA data reset
`Login_system/users.db` was inspected before any change:
- total users: **5**
- rows with `mfa_enabled=1`: **0**
- rows whose `mfa_secret` equalled the stub's `random_base32()` output: **0**

The reset `UPDATE users SET mfa_enabled=0, mfa_secret=NULL WHERE mfa_secret=<stub_value>` affected **0 rows**. No user was carrying a bogus stub secret, so no account state changed. The bogus value was derived at runtime from the stub file (evidence-based), not hardcoded into the remediation.

### 3.4 Post-change verification (real pyotp)
- Enrollment: `pyotp.random_base32()` returns a **32-char** random secret; `pyotp.totp.TOTP(secret).provisioning_uri(name=..., issuer_name="Assistify")` returns a valid `otpauth://totp/Assistify:...` URI with no exception.
- Verification: `pyotp.TOTP(secret).verify(pyotp.TOTP(secret).now())` -> `True`; an incorrect code -> `False`.

---

## 4. Deployment Risks Removed

1. **Silent MFA breakage / fail-closed lockout** - removed. Real `pyotp` is installed and resolves; MFA enroll + verify both function.
2. **Hardcoded constant secret** (`"BASE32SECRET"`, `"000000"`) on the production auth path - removed from `sys.path`; secrets are now cryptographically random per enrollment.
3. **Shadow persistence after a future dependency fix** - removed. Even with the repo root at `sys.path[0]`, `import pyotp` now resolves to site-packages because no root `pyotp.py` exists.
4. **`playwright` / `pyttsx3` / `reportlab` root-level name collisions** - removed from the repo root; they can no longer pre-empt an installed distribution of the same name in any future environment.
5. **False CI/test confidence from import-collection stubs** - reduced: these names now report `ModuleNotFoundError` (the honest "not installed" signal) instead of being silently satisfied by a placeholder.

---

## 5. Validation Evidence

### 5.1 Stub relocation + compile
```
$ git mv playwright.py legacy/stubs/playwright.py   # + pyttsx3.py, reportlab.py, pyotp.py
$ git status --porcelain
 M environment_main.yml
 M environment_main_locked.yml
R  playwright.py -> legacy/stubs/playwright.py
R  pyotp.py -> legacy/stubs/pyotp.py
R  pyttsx3.py -> legacy/stubs/pyttsx3.py
R  reportlab.py -> legacy/stubs/reportlab.py

$ python -m py_compile legacy/stubs/pyotp.py legacy/stubs/playwright.py legacy/stubs/pyttsx3.py legacy/stubs/reportlab.py Login_system/login_server.py
py_compile exit: 0
```

### 5.2 pyotp resolution (run from repo root, where shadowing would apply)
```
$ python -c "import sys; print(sys.path[0]); import pyotp; print(pyotp.__file__)"
sys.path[0]= ''
pyotp.__file__ => site-packages path under the active conda env
has TOTP.verify => True
has pyotp.totp => True
```

### 5.3 MFA enroll + verify paths
```
random_base32 len => 32
provisioning_uri => otpauth://totp/Assistify:alice?secret=... (valid)
verify(now) => True
verify(bad) => False
```

### 5.4 Import sanity (de-shadow confirmed)
```
pyotp     -> C:\...\assistify_main\Lib\site-packages\pyotp\__init__.py
playwright -> ModuleNotFoundError (expected; stub no longer shadows, real pkg not installed)
pyttsx3    -> ModuleNotFoundError (expected)
reportlab  -> ModuleNotFoundError (expected; importers fall back via try/except)
```

### 5.5 Startup imports
```
$ python -c "import Login_system.login_server as ls; print(type(ls.app).__name__, len(ls.app.routes))"
login app type => FastAPI ; login routes => 156 ; login_server import OK

$ python -c "import backend.assistify_rag_server as rs; print(type(rs.app).__name__, len(rs.app.routes))"
... CUDA / embedding model init logs ...
rag app type => FastAPI ; rag routes => 54 ; rag_server import OK
```

### 5.6 Route parity (`scripts/compare_routes.py`)
```
LOGIN decorator routes: current 147 audit 0
RAG decorator routes: current 45 audit 0
Login missing vs audit: 0 []
RAG missing vs audit: 0 []
```
The `audit 0` baseline is a **pre-existing** condition of the script (it expects the snapshot at `./assistify_refactor_audit/`, but the snapshot lives under `archive/audits/assistify_refactor_audit/`); it is unrelated to this phase. The relevant signal is that current route decorators still parse intact (147 login / 45 RAG) and no route files were touched in this phase, so route parity is preserved.

---

## 6. Commits

| Commit | Contents |
|---|---|
| `phase11b-stub-cleanup` | The four `git mv` relocations, `legacy/stubs/README.md`, and `pyotp==2.9.0` added to `environment_main.yml` + `environment_main_locked.yml`. (`Login_system/users.db` is git-ignored runtime data; the 0-row MFA reset is recorded here, not committed.) |
| `phase11b-report` | `Phase11B_Deployment_Hardening_Report.md` (this file). |

---

## 7. Residual Notes / Follow-ups

- **Re-enrollment caveat:** the stale-MFA reset affected 0 rows in this environment. Should any environment contain users previously flagged via the broken `enable_mfa` (which committed the bogus secret before crashing), those rows must be reset to `mfa_enabled=0, mfa_secret=NULL` and the users re-enrolled, because they were never able to provision a working authenticator.
- **Out of scope (left untouched):** the nested `assistify-rag-project-main/backend/chroma_db_reindex/chroma.sqlite3` stray artifact, the outer Chroma index, all backend business logic, and all RAG behavior.
- **Hardening recommendation (informational):** prefer installing the project as a package (e.g. `pip install -e .`) over exporting `PYTHONPATH=<repo root>`, so imports always resolve via site-packages rather than cwd. Avoid placing any `<pkgname>.py` at the repo root.

---

## 8. Genericity / Evidence / Future-Document Assessment

- **Genericity Assessment:** PASS. All changes operate on import resolution, dependency specs, and a security library - none depend on any company, product, document, dataset, metric, or known answer. The MFA fix uses the real `pyotp` library and cryptographically random secrets; the stale-row reset derives its match value from the stub file at runtime rather than hardcoding it. The work is fully document-agnostic.
- **Evidence-Origin Assessment:** PASS. Every claim is backed by reproduced command output - `git status` rename detection, `pyotp.__file__` pointing to site-packages, live `TOTP.verify(now())` -> `True` / bad-code -> `False`, `ModuleNotFoundError` for the de-shadowed names, FastAPI app import with route counts, and `py_compile` exit 0. No returned value originates from a code constant; the removed hardcoded constant (`"BASE32SECRET"`) was the defect being eliminated.
- **Future-Document Compatibility Assessment:** PASS. The shadowing fix and MFA remediation are independent of document content and would behave identically for any future document, domain, industry, company, or dataset.

*End of Phase 11B report.*
