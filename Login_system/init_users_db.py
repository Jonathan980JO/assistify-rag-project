import os
import sqlite3
from datetime import datetime


def main():
    this_dir = os.path.dirname(__file__)
    db_path = os.path.join(this_dir, "users.db")
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # Create users table if missing (minimal subset used by auth)
    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password_hash TEXT,
        role TEXT,
        mfa_enabled INTEGER DEFAULT 0,
        mfa_secret TEXT,
        active INTEGER DEFAULT 1,
        google_id TEXT UNIQUE,
        email TEXT,
        profile_picture TEXT,
        auth_provider TEXT DEFAULT 'local',
        email_verified INTEGER DEFAULT 0,
        full_name TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    conn.commit()

    # Insert or replace simple dev users (passwords intentionally simple for development)
    now = datetime.utcnow().isoformat()
    users = [
        ("admin", "", "admin", 1, now),
        ("employee", "", "employee", 1, now),
    ]
    for username, pwd_hash, role, active, created_at in users:
        c.execute("DELETE FROM users WHERE username=?", (username,))
        c.execute(
            "INSERT INTO users (username, password_hash, role, active, created_at) VALUES (?, ?, ?, ?, ?)",
            (username, pwd_hash, role, active, created_at),
        )
    conn.commit()
    conn.close()

    print(f"Created {db_path} with users: admin, employee (password = username in dev)")


if __name__ == '__main__':
    main()
