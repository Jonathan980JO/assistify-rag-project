"""
Database Migration Script
Migrates analytics.db to the new schema with enhanced columns
"""

import sqlite3
import os
from pathlib import Path

# Find analytics database
ANALYTICS_DB = Path(__file__).parent / "backend" / "analytics.db"

def migrate_analytics_db():
    """Migrate old analytics schema to new enhanced schema"""
    
    if not ANALYTICS_DB.exists():
        print(f"❌ Database not found at {ANALYTICS_DB}")
        return False
    
    print(f"📊 Migrating database: {ANALYTICS_DB}")
    
    conn = sqlite3.connect(ANALYTICS_DB)
    c = conn.cursor()
    
    try:
        # Check current schema
        c.execute("PRAGMA table_info(usage_stats)")
        columns = {row[1] for row in c.fetchall()}
        print(f"Current columns: {columns}")
        
        # Check if migration is needed
        if 'response_time_ms' in columns:
            print("✅ Database already has new schema. No migration needed.")
            conn.close()
            return True
        
        print("🔄 Starting migration...")
        
        # Create new table with enhanced schema
        c.execute("""
            CREATE TABLE IF NOT EXISTS usage_stats_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                username TEXT,
                user_role TEXT,
                query_text TEXT,
                response_status TEXT,
                error_message TEXT,
                response_time_ms INTEGER DEFAULT 0,
                rag_docs_found INTEGER DEFAULT 0,
                query_length INTEGER DEFAULT 0,
                response_length INTEGER DEFAULT 0
            )
        """)
        
        # Copy data from old table to new table
        c.execute("""
            INSERT INTO usage_stats_new 
                (id, timestamp, username, user_role, query_text, response_status, error_message,
                 response_time_ms, rag_docs_found, query_length, response_length)
            SELECT 
                id, timestamp, username, user_role, query_text, response_status, error_message,
                0, 0, 0, 0
            FROM usage_stats
        """)
        
        # Drop old table
        c.execute("DROP TABLE usage_stats")
        
        # Rename new table to original name
        c.execute("ALTER TABLE usage_stats_new RENAME TO usage_stats")
        
        conn.commit()
        print("✅ Migration completed successfully!")
        
        # Verify new schema
        c.execute("PRAGMA table_info(usage_stats)")
        new_columns = [row[1] for row in c.fetchall()]
        print(f"New columns: {new_columns}")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        conn.rollback()
        conn.close()
        return False


if __name__ == "__main__":
    print("="*60)
    print("ANALYTICS DATABASE MIGRATION")
    print("="*60)
    success = migrate_analytics_db()
    
    if success:
        print("\n🎉 Database migration successful!")
        print("You can now restart the server.")
    else:
        print("\n❌ Migration failed. Please check the error above.")
