"""
Database Migration: Rehash Legacy Passwords
This script updates any passwords that are not in bcrypt format.
"""

import sqlite3
from passlib.context import CryptContext

# Import bcrypt configuration
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import BCRYPT_ROUNDS

pwd_context = CryptContext(schemes=["bcrypt"], bcrypt__rounds=BCRYPT_ROUNDS)

def get_db():
    """Connect to the database."""
    db_path = os.path.join(os.path.dirname(__file__), "Login_system", "users.db")
    if not os.path.exists(db_path):
        # Try alternative path
        db_path = os.path.join(os.path.dirname(__file__), "..", "Login_system", "users.db")
    return sqlite3.connect(db_path)

def migrate_passwords():
    """Update all non-bcrypt password hashes to bcrypt."""
    conn = get_db()
    c = conn.cursor()
    
    # Get all users
    c.execute("SELECT id, username, password_hash FROM users WHERE password_hash != ''")
    users = c.fetchall()
    
    updated_count = 0
    skipped_count = 0
    
    for user_id, username, password_hash in users:
        # Check if password is already bcrypt (starts with $2b$ or $2a$ or $2y$)
        if password_hash.startswith(('$2b$', '$2a$', '$2y$')):
            print(f"✓ {username}: Already bcrypt, skipping")
            skipped_count += 1
            continue
        
        # This is a legacy password (plain text or other format)
        print(f"⚠ {username}: Non-bcrypt hash detected")
        print(f"  Old hash: {password_hash[:20]}...")
        
        # Re-hash the password (assuming it's stored as plain text)
        try:
            new_hash = pwd_context.hash(password_hash)
            c.execute("UPDATE users SET password_hash=? WHERE id=?", (new_hash, user_id))
            print(f"✓ {username}: Password re-hashed successfully")
            updated_count += 1
        except Exception as e:
            print(f"✗ {username}: Failed to re-hash - {e}")
    
    conn.commit()
    conn.close()
    
    print(f"\n{'='*60}")
    print(f"Migration Complete!")
    print(f"{'='*60}")
    print(f"Updated: {updated_count} users")
    print(f"Skipped: {skipped_count} users (already bcrypt)")
    print(f"Total:   {len(users)} users")
    
    if updated_count > 0:
        print(f"\n⚠ WARNING: Users with updated passwords will need to use their")
        print(f"  OLD password to log in (which is now properly hashed).")
        print(f"  If you don't know the old passwords, you may need to reset them.")

if __name__ == "__main__":
    print("="*60)
    print("Password Migration Script")
    print("="*60)
    print("This script will re-hash any non-bcrypt passwords in the database.")
    print()
    
    response = input("Continue? (yes/no): ")
    if response.lower() in ['yes', 'y']:
        migrate_passwords()
    else:
        print("Migration cancelled.")
