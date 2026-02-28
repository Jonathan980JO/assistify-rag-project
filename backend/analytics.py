import sqlite3
from datetime import datetime, timedelta
try:
    from config import ANALYTICS_DB
except Exception:
    from pathlib import Path as _P
    ANALYTICS_DB = _P(__file__).resolve().parent / "analytics.db"

ANALYTICS_DB = str(ANALYTICS_DB)

def init_analytics_db():
    conn = sqlite3.connect(ANALYTICS_DB)
    c = conn.cursor()
    
    # Main usage stats table (enhanced)
    c.execute("""
        CREATE TABLE IF NOT EXISTS usage_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            username TEXT,
            user_role TEXT,
            query_text TEXT,
            response_status TEXT,
            error_message TEXT,
            response_time_ms INTEGER,
            rag_docs_found INTEGER,
            query_length INTEGER,
            response_length INTEGER
        )
    """)
    
    # User satisfaction feedback table
    c.execute("""
        CREATE TABLE IF NOT EXISTS satisfaction_ratings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            username TEXT,
            user_role TEXT,
            query_id INTEGER,
            rating INTEGER CHECK(rating BETWEEN 1 AND 5),
            feedback_text TEXT,
            FOREIGN KEY (query_id) REFERENCES usage_stats(id)
        )
    """)
    
    # Model performance metrics table
    c.execute("""
        CREATE TABLE IF NOT EXISTS model_performance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            model_name TEXT,
            avg_response_time_ms REAL,
            success_rate REAL,
            tokens_processed INTEGER,
            cache_hits INTEGER,
            cache_misses INTEGER
        )
    """)
    
    # Session analytics table
    c.execute("""
        CREATE TABLE IF NOT EXISTS session_analytics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_start DATETIME DEFAULT CURRENT_TIMESTAMP,
            session_end DATETIME,
            username TEXT,
            user_role TEXT,
            queries_count INTEGER DEFAULT 0,
            avg_satisfaction REAL,
            session_duration_minutes INTEGER
        )
    """)
    
    conn.commit()
    conn.close()


def log_usage(username, user_role, query_text, response_status="success", error_message=None, 
              response_time_ms=0, rag_docs_found=0, query_length=0, response_length=0):
    """Enhanced usage logging with performance metrics"""
    conn = sqlite3.connect(ANALYTICS_DB)
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO usage_stats (username, user_role, query_text, response_status, error_message,
                                response_time_ms, rag_docs_found, query_length, response_length)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (username, user_role, query_text, response_status, error_message,
         response_time_ms, rag_docs_found, query_length, response_length),
    )
    conn.commit()
    conn.close()


def log_satisfaction(username, user_role, rating, feedback_text=None, query_id=None):
    """Log user satisfaction rating"""
    conn = sqlite3.connect(ANALYTICS_DB)
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO satisfaction_ratings (username, user_role, query_id, rating, feedback_text)
        VALUES (?, ?, ?, ?, ?)
        """,
        (username, user_role, query_id, rating, feedback_text),
    )
    conn.commit()
    conn.close()


def get_comprehensive_analytics(days=30):
    """Get comprehensive analytics for dashboard"""
    conn = sqlite3.connect(ANALYTICS_DB)
    c = conn.cursor()
    
    cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
    
    # Query success rate
    c.execute("""
        SELECT 
            COUNT(*) as total_queries,
            SUM(CASE WHEN response_status = 'success' THEN 1 ELSE 0 END) as successful_queries,
            ROUND(AVG(response_time_ms), 2) as avg_response_time,
            ROUND(AVG(CASE WHEN response_status = 'success' THEN response_time_ms END), 2) as avg_success_time
        FROM usage_stats
        WHERE timestamp > ?
    """, (cutoff_date,))
    query_stats = c.fetchone()
    
    # Usage by role
    c.execute("""
        SELECT user_role, COUNT(*) as count,
               ROUND(AVG(response_time_ms), 2) as avg_time
        FROM usage_stats
        WHERE timestamp > ?
        GROUP BY user_role
        ORDER BY count DESC
    """, (cutoff_date,))
    usage_by_role = c.fetchall()
    
    # Top errors
    c.execute("""
        SELECT error_message, COUNT(*) as count
        FROM usage_stats
        WHERE response_status != 'success' AND timestamp > ?
        GROUP BY error_message
        ORDER BY count DESC
        LIMIT 10
    """, (cutoff_date,))
    top_errors = c.fetchall()
    
    # Average satisfaction rating
    c.execute("""
        SELECT 
            ROUND(AVG(rating), 2) as avg_rating,
            COUNT(*) as total_ratings,
            SUM(CASE WHEN rating >= 4 THEN 1 ELSE 0 END) as positive_ratings
        FROM satisfaction_ratings
        WHERE timestamp > ?
    """, (cutoff_date,))
    satisfaction = c.fetchone()
    
    # RAG performance
    c.execute("""
        SELECT 
            ROUND(AVG(rag_docs_found), 2) as avg_docs_found,
            SUM(CASE WHEN rag_docs_found > 0 THEN 1 ELSE 0 END) as queries_with_docs,
            COUNT(*) as total_queries
        FROM usage_stats
        WHERE timestamp > ?
    """, (cutoff_date,))
    rag_stats = c.fetchone()
    
    # Hourly distribution
    c.execute("""
        SELECT 
            strftime('%H', timestamp) as hour,
            COUNT(*) as count
        FROM usage_stats
        WHERE timestamp > ?
        GROUP BY hour
        ORDER BY hour
    """, (cutoff_date,))
    hourly_distribution = c.fetchall()
    
    # Daily trend (last 7 days)
    c.execute("""
        SELECT 
            DATE(timestamp) as day,
            COUNT(*) as total_queries,
            SUM(CASE WHEN response_status = 'success' THEN 1 ELSE 0 END) as successful_queries
        FROM usage_stats
        WHERE timestamp > datetime('now', '-7 days')
        GROUP BY day
        ORDER BY day DESC
    """)
    daily_trend = c.fetchall()
    
    conn.close()
    
    total_queries, successful_queries, avg_response_time, avg_success_time = query_stats or (0, 0, 0, 0)
    avg_rating, total_ratings, positive_ratings = satisfaction or (0, 0, 0)
    avg_docs_found, queries_with_docs, total_rag_queries = rag_stats or (0, 0, 0)
    
    success_rate = (successful_queries / total_queries * 100) if total_queries > 0 else 0
    rag_hit_rate = (queries_with_docs / total_rag_queries * 100) if total_rag_queries > 0 else 0
    satisfaction_rate = (positive_ratings / total_ratings * 100) if total_ratings > 0 else 0
    
    return {
        "total_queries": total_queries,
        "success_rate": round(success_rate, 2),
        "avg_response_time": avg_response_time or 0,
        "avg_success_time": avg_success_time or 0,
        "usage_by_role": [{"role": r[0], "count": r[1], "avg_time": r[2]} for r in usage_by_role],
        "top_errors": [{"error": e[0], "count": e[1]} for e in top_errors],
        "satisfaction": {
            "avg_rating": avg_rating or 0,
            "total_ratings": total_ratings,
            "satisfaction_rate": round(satisfaction_rate, 2)
        },
        "rag_performance": {
            "avg_docs_found": avg_docs_found or 0,
            "rag_hit_rate": round(rag_hit_rate, 2),
            "queries_with_docs": queries_with_docs
        },
        "hourly_distribution": [{"hour": h[0], "count": h[1]} for h in hourly_distribution],
        "daily_trend": [{"day": d[0], "total": d[1], "successful": d[2]} for d in daily_trend]
    }


def get_summary(limit=100):
    conn = sqlite3.connect(ANALYTICS_DB)
    c = conn.cursor()
    c.execute("SELECT user_role, COUNT(*) FROM usage_stats GROUP BY user_role")
    data = c.fetchall()
    conn.close()
    return data


def get_recent_errors(limit=50):
    conn = sqlite3.connect(ANALYTICS_DB)
    c = conn.cursor()
    c.execute(
        "SELECT timestamp, username, error_message FROM usage_stats WHERE response_status != 'success' ORDER BY timestamp DESC LIMIT ?",
        (limit,),
    )
    rows = c.fetchall()
    conn.close()
    return rows

