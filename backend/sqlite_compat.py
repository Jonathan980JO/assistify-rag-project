"""Bootstrap sqlite3 — stdlib first, pysqlite3-binary fallback on Windows DLL blocks."""
from __future__ import annotations

import sys

_SQLITE_HELP = """
sqlite3 failed to load. On Windows this often means Application Control blocked
the native _sqlite3 DLL in your Python environment.

Fixes (try in order):
  1. Settings → Windows Security → App & browser control → Smart App Control → Off
     (reboot required), then: python -c "import sqlite3"
  2. conda activate assistify_main
     conda install -c conda-forge sqlite libsqlite python=3.11 --force-reinstall -y
  3. See docs/WINDOWS_TROUBLESHOOTING.md
"""


def _try_pysqlite3_fallback() -> bool:
    try:
        import pysqlite3.dbapi2 as sqlite3_mod
    except ImportError:
        return False
    sys.modules["sqlite3"] = sqlite3_mod
    sys.modules["sqlite3.dbapi2"] = sqlite3_mod
    return True


def ensure_sqlite3():
    """Return a working sqlite3 module; patch sys.modules on fallback."""
    if "sqlite3" in sys.modules:
        return sys.modules["sqlite3"]
    try:
        import sqlite3
        return sqlite3
    except ImportError as exc:
        if _try_pysqlite3_fallback():
            return sys.modules["sqlite3"]
        raise RuntimeError(f"{_SQLITE_HELP.strip()}\n\nOriginal error: {exc}") from exc


ensure_sqlite3()
