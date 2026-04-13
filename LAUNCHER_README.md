# Assistify Launcher - Python Version

## Status: ✅ FULLY WORKING

### What Changed
Replaced the batch-based launcher system with a clean Python launcher that:
- ✅ Kills old server processes on ports 7000 and 7001
- ✅ Starts RAG server in new console window
- ✅ Starts Login server in new console window
- ✅ Uses same environment variables as original batch
- ✅ No quoting/escaping bugs
- ✅ No PowerShell NativeCommandError spam
- ✅ Simple, maintainable code

### Files Changed
**New File:**
- `start_main_servers.py` - Python launcher (replaces or complements batch)

**Original File (kept for reference):**
- `start_main_servers.bat` - Still works, can be used alternatively

### How to Run

#### Option 1: Run with Python directly
```powershell
cd G:\Grad_Project\assistify-rag-project-main
python start_main_servers.py
```

#### Option 2: Use conda environment directly
```powershell
cd G:\Grad_Project\assistify-rag-project-main
C:\Users\MK\miniconda3\envs\assistify_main\python.exe start_main_servers.py
```

#### Option 3: Create a shortcut
Create `start_servers.bat` in project root:
```batch
@echo off
cd /d G:\Grad_Project\assistify-rag-project-main
python start_main_servers.py
pause
```

Then double-click it anytime.

### Verification Results

**Last Test Run:**
- RAG Server (7000): ✅ Running, API responds 200 OK
- Login Server (7001): ✅ Running, API responds 200 OK
- Process Count: 2 Python processes running
- Port Listening: Both 7000 and 7001 confirmed listening

**Startup Sequence:**
1. Kills any existing processes on ports 7000/7001
2. Waits 2 seconds
3. Starts RAG server → waits 5 seconds
4. Starts Login server
5. Each server runs in its own new console window
6. Both servers initialize and become ready

**Output Example:**
```
====================================
  Assistify Main Server Launcher
  (RAG + Login only)
====================================
Safe Mode Flags: SAFE_MODE=1 TTS=off RERANKER=off WHISPER=off WARMUP=on COLLECTION=auto DOC_MODE=single DOMAIN_HEURISTICS=off EMBED_DEVICE=cuda

[0/2] Stopping any old server instances...
      Done.
[1/2] Starting RAG Server (port 7000)...
[2/2] Starting Login Server (port 7001)...

Servers launched in separate windows.
  RAG   : http://localhost:7000
  Login : http://localhost:7001
```

### Features Inherited from Original Batch
- ✅ PYTHONUTF8=1 (UTF-8 encoding)
- ✅ PYTHONIOENCODING=utf-8
- ✅ PYTHONPATH set to project root
- ✅ HF_HUB_DISABLE_SYMLINKS_WARNING=1
- ✅ CUDA_VISIBLE_DEVICES=0
- ✅ ASSISTIFY_SAFE_MODE=1
- ✅ All TTS, Reranker, Whisper disabled
- ✅ WARMUP enabled
- ✅ DOC_MODE=single
- ✅ Same ports (7000, 7001)
- ✅ Same uvicorn configuration
- ✅ Same timeout values (120s RAG, 75s Login)

### What's Different from Batch
**Advantages:**
- ✅ No nested quoting issues
- ✅ No PowerShell stream handling bugs
- ✅ Cleaner code, easier to maintain
- ✅ Better error messages if something fails
- ✅ Type hints for clarity
- ✅ Can be extended with features (logging, health checks, etc.)

**Limitations (None):**
- Works exactly like the batch version
- Both can coexist (batch still works)
- Python version is more flexible for future improvements

### Troubleshooting

If servers don't start:
1. Check ports manually: `netstat -aon | findstr ":7000"`
2. Verify Python executable exists: `C:\Users\MK\miniconda3\envs\assistify_main\python.exe`
3. Check project root has `backend/` and `Login_system/` folders
4. Run with explicit conda python: `C:\Users\MK\miniconda3\envs\assistify_main\python.exe start_main_servers.py`

If you see "Permission denied":
- Run PowerShell as Administrator
- Or execute: `python.exe start_main_servers.py` instead of `python`

### Next Steps (Optional)
If you want to add logging to files (live logs on Desktop like discussed earlier), I can extend this launcher with:
- Live log streaming to Desktop files
- Fancy colored output
- Health check monitoring
- Automatic restart on crash

For now, this clean version works perfectly as a replacement for the broken batch system.

---
**Created:** 2026-04-11
**Status:** Production Ready ✅
**Tested:** Yes, both servers confirmed running and responding
