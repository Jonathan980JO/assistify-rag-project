# Windows Troubleshooting

## sqlite3 blocked by Application Control

### Symptom

RAG or Login fails immediately on startup with:

```
ImportError: DLL load failed while importing _sqlite3:
An Application Control policy has blocked this file.
```

The coordinator may hang for up to 10 minutes waiting for RAG on port 7000, and Login never opens.

### Why it happens

Windows **Smart App Control** (or other application-control policies) can block the native `_sqlite3` extension DLL inside your conda Python environment. Both RAG and Login require `sqlite3` for conversations, sessions, analytics, and ChromaDB metadata.

### Fix (try in order)

**1. Confirm the failure**

```powershell
conda activate assistify_main
python -c "import sqlite3; print('sqlite3 OK', sqlite3.sqlite_version)"
```

**2. Disable Smart App Control (personal Windows 11 PCs)**

1. Open **Settings → Privacy & security → Windows Security**
2. **App & browser control → Smart App Control**
3. Set to **Off** (reboot required)
4. Re-run the `python -c "import sqlite3"` test

**3. Repair conda SQLite packages**

```powershell
conda activate assistify_main
conda install -c conda-forge sqlite libsqlite python=3.11 --force-reinstall -y
python -c "import sqlite3; print('sqlite3 OK', sqlite3.sqlite_version)"
```

If still failing:

```powershell
conda install -c conda-forge python=3.11 --force-reinstall -y
```

**4. Optional: move the project out of Downloads**

Some policies treat `Downloads` as untrusted. Clone or move the repo to e.g. `C:\dev\assistify-rag-project` and restart with `python start_main_servers.py`.

**5. pysqlite3-binary fallback**

The repo includes `backend/sqlite_compat.py`, which tries stdlib `sqlite3` first, then `pysqlite3-binary`:

```powershell
pip install pysqlite3-binary
```

This is wired into RAG and Login entrypoints automatically.

### Preflight check

Run before starting servers:

```powershell
python scripts/preflight_check.py
```

A working environment prints `sqlite3: OK (3.x.x)`. The split launcher also checks sqlite3 at startup and exits immediately if it fails.

### After fixing

```powershell
python start_main_servers.py --restart-ollama
python scripts/verify_stack.py
```

Open http://127.0.0.1:7001/login when the coordinator reports `[LOGIN] Ready`.

## Login port already in use (EADDRINUSE / WinError 10048)

### Symptom

The **Assistify Login** window shows:

```
ERROR: [Errno 10048] error while attempting to bind on address ('127.0.0.1', 7001):
only one usage of each socket address (protocol/network address/port) is normally permitted
```

The coordinator may still print `[LOGIN] Ready` because it health-checks whatever is already listening on 7001, while a **second** Login window fails to bind.

### Why it happens

- A previous Login server is still running (leftover `Assistify Login` cmd window or verification process).
- The launcher spawned a duplicate Login window while port 7001 was already taken (often after a long RAG boot).

### Fix

1. Close the failed Login window (`Press any key to continue`).
2. Keep the working `Assistify Login` window that shows `Uvicorn running on http://127.0.0.1:7001`, or restart cleanly:

```powershell
# See what holds the port
netstat -ano | findstr :7001

# Stop the process (replace PID)
taskkill /PID <pid> /F
```

3. Close all `Assistify *` service windows, then:

```powershell
python start_main_servers.py --restart-ollama
```

`--kill-ports` is enabled by default and frees 7001 before Login starts. The launcher also skips opening a new Login window when port 7001 is already healthy.

### Verify

```powershell
python scripts/verify_stack.py
```

Expect `Login (7001): OK`. Open http://127.0.0.1:7001/login in the browser.

## Stuck on email verification (/verify-otp)

### Symptom

After registering, the browser shows **Verify Your Email** and no code arrives (EmailJS not configured yet).

### Fix (development)

Add to your `.env` file (copy from `.env.example` if needed):

```
SKIP_EMAIL_OTP=true
```

Restart the Login server, then register again at http://127.0.0.1:7001/register. The account is created immediately and you are redirected to login.

**Note:** A registration that stopped on `/verify-otp` did not create the user yet — register again after enabling the flag.

Alternatively, use dev logins (`admin` / `admin`) until EmailJS is configured for production.

### Production

Set real `EMAILJS_*` credentials in `.env`, keep `SKIP_EMAIL_OTP` unset or `false`, and leave `ENVIRONMENT=production`.
