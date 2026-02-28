"""
Check user password hashes in the database
"""
import sqlite3
import os

db_path = os.path.join(os.path.dirname(__file__), "Login_system", "users.db")
conn = sqlite3.connect(db_path)
c = conn.cursor()

print("="*60)
print("USER PASSWORD HASH INSPECTION")
print("="*60)

c.execute("SELECT id, username, password_hash FROM users")
users = c.fetchall()

print(f"\nTotal users: {len(users)}\n")

for user_id, username, password_hash in users:
    print(f"ID: {user_id}")
    print(f"  Username: {username}")
    print(f"  Password Hash: {password_hash[:50]}..." if len(password_hash) > 50 else f"  Password Hash: {password_hash}")
    
    # Check hash type
    if password_hash.startswith('$2b$') or password_hash.startswith('$2a$') or password_hash.startswith('$2y$'):
        print(f"  Hash Type: ✓ BCRYPT (secure)")
    elif password_hash == "":
        print(f"  Hash Type: EMPTY")
    else:
        print(f"  Hash Type: ⚠ UNKNOWN/PLAINTEXT (insecure!)")
    print()

conn.close()
