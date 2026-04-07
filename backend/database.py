# database.py - SQLite Database for Conversation History
import sqlite3
from datetime import datetime
from pathlib import Path
try:
    from config import DB_PATH
except Exception:
    DB_PATH = Path(__file__).resolve().parent / "conversations.db"

# Ensure DB_PATH is a string path for sqlite3
DB_PATH = str(DB_PATH)
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Database")

def init_database():
    """Initialize SQLite database with required tables"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Conversations table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                connection_id TEXT NOT NULL,
                user_message TEXT NOT NULL,
                ai_response TEXT NOT NULL,
                retrieved_docs TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Sessions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                connection_id TEXT UNIQUE NOT NULL,
                start_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                end_time DATETIME,
                message_count INTEGER DEFAULT 0
            )
        ''')
        
        conn.commit()
        conn.close()
        logger.info("✓ Database initialized")
        return True
    except Exception as e:
        logger.error(f"Database initialization error: {e}")
        return False

def save_conversation(connection_id: str, user_msg: str, ai_msg: str, docs: list = None):
    """Save a conversation exchange to database"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        docs_str = "\n---\n".join(docs) if docs else None
        
        cursor.execute('''
            INSERT INTO conversations (connection_id, user_message, ai_response, retrieved_docs)
            VALUES (?, ?, ?, ?)
        ''', (connection_id, user_msg, ai_msg, docs_str))
        
        # Update session message count
        cursor.execute('''
            UPDATE sessions 
            SET message_count = message_count + 1 
            WHERE connection_id = ?
        ''', (connection_id,))
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Error saving conversation: {e}")
        return False

def start_session(connection_id: str):
    """Start a new session"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR IGNORE INTO sessions (connection_id)
            VALUES (?)
        ''', (connection_id,))
        
        conn.commit()
        conn.close()
        logger.info(f"✓ Started session: {connection_id}")
        return True
    except Exception as e:
        logger.error(f"Error starting session: {e}")
        return False

def end_session(connection_id: str):
    """End a session"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE sessions 
            SET end_time = CURRENT_TIMESTAMP 
            WHERE connection_id = ? AND end_time IS NULL
        ''', (connection_id,))
        
        conn.commit()
        conn.close()
        logger.info(f"✓ Ended session: {connection_id}")
        return True
    except Exception as e:
        logger.error(f"Error ending session: {e}")
        return False

def get_conversation_history(connection_id: str, limit: int = 50):
    """Get conversation history for a connection"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT user_message, ai_response, timestamp 
            FROM conversations 
            WHERE connection_id = ? 
            ORDER BY timestamp DESC 
            LIMIT ?
        ''', (connection_id, limit))
        
        results = cursor.fetchall()
        conn.close()
        return results
    except Exception as e:
        logger.error(f"Error getting history: {e}")
        return []

def get_stats():
    """Get database statistics"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM conversations')
        total_messages = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM sessions')
        total_sessions = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM sessions WHERE end_time IS NOT NULL')
        completed_sessions = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            "total_messages": total_messages,
            "total_sessions": total_sessions,
            "completed_sessions": completed_sessions,
            "active_sessions": total_sessions - completed_sessions
        }
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        return {}

if __name__ == "__main__":
    # Test database
    print("Testing Database...")
    init_database()
    
    test_id = "test_123"
    start_session(test_id)
    save_conversation(test_id, "Hello", "Hi there!", ["doc1"])
    
    stats = get_stats()
    print(f"\nDatabase Stats: {stats}")
    
    end_session(test_id)
