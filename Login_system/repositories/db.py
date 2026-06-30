"""Database connection factory for the login system (users database).

Extracted from ``login_server.py`` during the Phase 2 refactor. This is the
single data-access entry point for the SQLite users database; all repository
modules and (currently) the route handlers obtain their connection here.

The database path is resolved relative to the ``Login_system`` package root
(parent of this ``repositories`` package) so it points at exactly the same
``Login_system/users.db`` file the monolith used before the refactor.
"""
import sqlite3
from pathlib import Path

# NOTE: parent.parent == the Login_system package dir, matching the original
# definition `Path(login_server.py).resolve().parent / "users.db"`.
DB_PATH = str((Path(__file__).resolve().parent.parent / "users.db"))


def get_db():
    conn = sqlite3.connect(DB_PATH)
    return conn
