import sqlite3
from datetime import datetime, timedelta
try:
    from config import ANALYTICS_DB
except Exception:
    from pathlib import Path as _P
    ANALYTICS_DB = _P(__file__).resolve().parent / "analytics.db"

try:
    from config import DEFAULT_TENANT_ID
except Exception:
    DEFAULT_TENANT_ID = 1

ANALYTICS_DB = str(ANALYTICS_DB)


def _coerce_tenant_id(tenant_id) -> int:
    try:
        tid = int(tenant_id)
    except (TypeError, ValueError):
        return DEFAULT_TENANT_ID
    return tid if tid > 0 else DEFAULT_TENANT_ID


def _ensure_tenant_column(cursor, table: str):
    """Add tenant_id to an existing analytics table and backfill default tenant."""
    try:
        cursor.execute(f"PRAGMA table_info({table})")
        cols = [row[1] for row in cursor.fetchall()]
        if "tenant_id" not in cols:
            cursor.execute(
                f"ALTER TABLE {table} ADD COLUMN tenant_id INTEGER DEFAULT {DEFAULT_TENANT_ID}"
            )
            cursor.execute(
                f"UPDATE {table} SET tenant_id=? WHERE tenant_id IS NULL",
                (DEFAULT_TENANT_ID,),
            )
    except Exception:
        pass


def init_analytics_db():
    conn = sqlite3.connect(ANALYTICS_DB)
    c = conn.cursor()
    
    # Main usage stats table (enhanced)
    c.execute("""
        CREATE TABLE IF NOT EXISTS usage_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            tenant_id INTEGER DEFAULT 1,
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
            tenant_id INTEGER DEFAULT 1,
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
            tenant_id INTEGER DEFAULT 1,
            username TEXT,
            user_role TEXT,
            queries_count INTEGER DEFAULT 0,
            avg_satisfaction REAL,
            session_duration_minutes INTEGER
        )
    """)

    # Knowledge Base document version/event log
    c.execute("""
        CREATE TABLE IF NOT EXISTS kb_document_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            tenant_id INTEGER DEFAULT 1,
            action TEXT,
            filename TEXT,
            chunks_added INTEGER DEFAULT 0,
            chunks_deleted INTEGER DEFAULT 0,
            kb_version INTEGER DEFAULT 1,
            triggered_by TEXT DEFAULT 'system'
        )
    """)

    # Backfill tenant_id for databases created before multi-tenancy.
    for _tbl in ("usage_stats", "satisfaction_ratings", "session_analytics", "kb_document_versions"):
        _ensure_tenant_column(c, _tbl)

    conn.commit()
    conn.close()


def log_usage(username, user_role, query_text, response_status="success", error_message=None, 
              response_time_ms=0, rag_docs_found=0, query_length=0, response_length=0, tenant_id=None):
    """Enhanced usage logging with performance metrics"""
    conn = sqlite3.connect(ANALYTICS_DB)
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO usage_stats (tenant_id, username, user_role, query_text, response_status, error_message,
                                response_time_ms, rag_docs_found, query_length, response_length)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (_coerce_tenant_id(tenant_id), username, user_role, query_text, response_status, error_message,
         response_time_ms, rag_docs_found, query_length, response_length),
    )
    conn.commit()
    conn.close()


def log_satisfaction(username, user_role, rating, feedback_text=None, query_id=None, tenant_id=None):
    """Log user satisfaction rating"""
    conn = sqlite3.connect(ANALYTICS_DB)
    c = conn.cursor()
    c.execute(
        """
        INSERT INTO satisfaction_ratings (tenant_id, username, user_role, query_id, rating, feedback_text)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (_coerce_tenant_id(tenant_id), username, user_role, query_id, rating, feedback_text),
    )
    conn.commit()
    conn.close()


def get_comprehensive_analytics(days=30, tenant_id=None):
    """Get comprehensive analytics for dashboard (optionally scoped to one tenant)"""
    conn = sqlite3.connect(ANALYTICS_DB)
    c = conn.cursor()
    
    cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()

    # Optional tenant scope appended to each WHERE clause.
    if tenant_id is None:
        tclause = ""
        tparam = ()
    else:
        tclause = " AND tenant_id = ?"
        tparam = (_coerce_tenant_id(tenant_id),)
    
    # Query success rate
    c.execute("""
        SELECT 
            COUNT(*) as total_queries,
            SUM(CASE WHEN response_status = 'success' THEN 1 ELSE 0 END) as successful_queries,
            ROUND(AVG(response_time_ms), 2) as avg_response_time,
            ROUND(AVG(CASE WHEN response_status = 'success' THEN response_time_ms END), 2) as avg_success_time
        FROM usage_stats
        WHERE timestamp > ?""" + tclause, (cutoff_date, *tparam))
    query_stats = c.fetchone()
    
    # Usage by role
    c.execute("""
        SELECT user_role, COUNT(*) as count,
               ROUND(AVG(response_time_ms), 2) as avg_time
        FROM usage_stats
        WHERE timestamp > ?""" + tclause + """
        GROUP BY user_role
        ORDER BY count DESC
    """, (cutoff_date, *tparam))
    usage_by_role = c.fetchall()
    
    # Top errors
    c.execute("""
        SELECT error_message, COUNT(*) as count
        FROM usage_stats
        WHERE response_status != 'success' AND timestamp > ?""" + tclause + """
        GROUP BY error_message
        ORDER BY count DESC
        LIMIT 10
    """, (cutoff_date, *tparam))
    top_errors = c.fetchall()
    
    # Average satisfaction rating
    c.execute("""
        SELECT 
            ROUND(AVG(rating), 2) as avg_rating,
            COUNT(*) as total_ratings,
            SUM(CASE WHEN rating >= 4 THEN 1 ELSE 0 END) as positive_ratings
        FROM satisfaction_ratings
        WHERE timestamp > ?""" + tclause, (cutoff_date, *tparam))
    satisfaction = c.fetchone()
    
    # RAG performance
    c.execute("""
        SELECT 
            ROUND(AVG(rag_docs_found), 2) as avg_docs_found,
            SUM(CASE WHEN rag_docs_found > 0 THEN 1 ELSE 0 END) as queries_with_docs,
            COUNT(*) as total_queries
        FROM usage_stats
        WHERE timestamp > ?""" + tclause, (cutoff_date, *tparam))
    rag_stats = c.fetchone()
    
    # Hourly distribution
    c.execute("""
        SELECT 
            strftime('%H', timestamp) as hour,
            COUNT(*) as count
        FROM usage_stats
        WHERE timestamp > ?""" + tclause + """
        GROUP BY hour
        ORDER BY hour
    """, (cutoff_date, *tparam))
    hourly_distribution = c.fetchall()
    
    # Daily trend (last 7 days)
    c.execute("""
        SELECT 
            DATE(timestamp) as day,
            COUNT(*) as total_queries,
            SUM(CASE WHEN response_status = 'success' THEN 1 ELSE 0 END) as successful_queries
        FROM usage_stats
        WHERE timestamp > datetime('now', '-7 days')""" + tclause + """
        GROUP BY day
        ORDER BY day DESC
    """, tparam)
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


def get_summary(limit=100, tenant_id=None):
    conn = sqlite3.connect(ANALYTICS_DB)
    c = conn.cursor()
    if tenant_id is None:
        c.execute("SELECT user_role, COUNT(*) FROM usage_stats GROUP BY user_role")
    else:
        c.execute(
            "SELECT user_role, COUNT(*) FROM usage_stats WHERE tenant_id = ? GROUP BY user_role",
            (_coerce_tenant_id(tenant_id),),
        )
    data = c.fetchall()
    conn.close()
    return data


def get_recent_errors(limit=50, tenant_id=None):
    conn = sqlite3.connect(ANALYTICS_DB)
    c = conn.cursor()
    if tenant_id is None:
        c.execute(
            "SELECT timestamp, username, error_message FROM usage_stats WHERE response_status != 'success' ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        )
    else:
        c.execute(
            "SELECT timestamp, username, error_message FROM usage_stats WHERE response_status != 'success' AND tenant_id = ? ORDER BY timestamp DESC LIMIT ?",
            (_coerce_tenant_id(tenant_id), limit),
        )
    rows = c.fetchall()
    conn.close()
    return rows


# ========== KNOWLEDGE BASE EVENT TRACKING ==========

def log_kb_event(action: str, filename: str, chunks_added: int = 0, chunks_deleted: int = 0,
                 kb_version: int = 0, triggered_by: str = "system", tenant_id=None):
    """Log a knowledge base document mutation event.

    Args:
        action: One of 'upload', 'update', 'delete', 'reindex', 'reindex_all', 'clear_cache'
        filename: Affected filename (or '*' for bulk operations)
        chunks_added: Number of new chunks indexed
        chunks_deleted: Number of old chunks removed
        kb_version: Global KB version counter at time of event
        triggered_by: 'admin', 'watcher', or 'system'
        tenant_id: Owning tenant (defaults to the canonical tenant)
    """
    try:
        conn = sqlite3.connect(ANALYTICS_DB)
        c = conn.cursor()
        c.execute(
            """INSERT INTO kb_document_versions
               (tenant_id, action, filename, chunks_added, chunks_deleted, kb_version, triggered_by)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (_coerce_tenant_id(tenant_id), action, filename, chunks_added, chunks_deleted, kb_version, triggered_by),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass  # Analytics must never crash the caller


def get_kb_events(limit: int = 100, tenant_id=None) -> list:
    """Return recent KB mutation events, newest first (optionally per tenant)."""
    try:
        conn = sqlite3.connect(ANALYTICS_DB)
        c = conn.cursor()
        if tenant_id is None:
            c.execute(
                """SELECT id, timestamp, action, filename, chunks_added, chunks_deleted,
                          kb_version, triggered_by
                   FROM kb_document_versions
                   ORDER BY id DESC LIMIT ?""",
                (limit,),
            )
        else:
            c.execute(
                """SELECT id, timestamp, action, filename, chunks_added, chunks_deleted,
                          kb_version, triggered_by
                   FROM kb_document_versions
                   WHERE tenant_id = ?
                   ORDER BY id DESC LIMIT ?""",
                (_coerce_tenant_id(tenant_id), limit),
            )
        rows = c.fetchall()
        conn.close()
        return [
            {
                "id": r[0], "timestamp": r[1], "action": r[2], "filename": r[3],
                "chunks_added": r[4], "chunks_deleted": r[5],
                "kb_version": r[6], "triggered_by": r[7],
            }
            for r in rows
        ]
    except Exception:
        return []


def get_kb_stats(days: int = 30, tenant_id=None) -> dict:
    """Return KB-specific performance metrics for the monitoring dashboard."""
    try:
        conn = sqlite3.connect(ANALYTICS_DB)
        c = conn.cursor()
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()

        if tenant_id is None:
            tclause = ""
            tparam = ()
        else:
            tclause = " AND tenant_id = ?"
            tparam = (_coerce_tenant_id(tenant_id),)

        # Total mutations in window
        c.execute(
            "SELECT COUNT(*), MAX(timestamp) FROM kb_document_versions WHERE timestamp > ?" + tclause,
            (cutoff, *tparam)
        )
        total_mutations, last_update = c.fetchone() or (0, None)

        # Mutations by action type
        c.execute(
            """SELECT action, COUNT(*) as cnt FROM kb_document_versions
               WHERE timestamp > ?""" + tclause + """ GROUP BY action ORDER BY cnt DESC""",
            (cutoff, *tparam)
        )
        mutations_by_action = [{"action": r[0], "count": r[1]} for r in c.fetchall()]

        # Files changed most often
        c.execute(
            """SELECT filename, COUNT(*) as cnt FROM kb_document_versions
               WHERE timestamp > ? AND filename != '*'""" + tclause + """
               GROUP BY filename ORDER BY cnt DESC LIMIT 10""",
            (cutoff, *tparam)
        )
        top_files = [{"filename": r[0], "mutations": r[1]} for r in c.fetchall()]

        # RAG hit rate from usage_stats
        c.execute(
            """SELECT COUNT(*) as total,
                      SUM(CASE WHEN rag_docs_found > 0 THEN 1 ELSE 0 END) as rag_hits,
                      ROUND(AVG(response_time_ms), 1) as avg_ms
               FROM usage_stats WHERE timestamp > ?""" + tclause,
            (cutoff, *tparam)
        )
        us = c.fetchone() or (0, 0, 0)
        total_q, rag_hits, avg_ms = us
        rag_hit_rate = round((rag_hits / total_q * 100) if total_q else 0, 1)

        # Daily KB mutation trend (last 14 days)
        c.execute(
            """SELECT DATE(timestamp) as day, COUNT(*) as cnt
               FROM kb_document_versions
               WHERE timestamp > datetime('now', '-14 days')""" + tclause + """
               GROUP BY day ORDER BY day""",
            tparam,
        )
        daily_mutations = [{"day": r[0], "count": r[1]} for r in c.fetchall()]

        # Chunks: total added vs deleted (all time)
        if tenant_id is None:
            c.execute("SELECT SUM(chunks_added), SUM(chunks_deleted) FROM kb_document_versions")
        else:
            c.execute(
                "SELECT SUM(chunks_added), SUM(chunks_deleted) FROM kb_document_versions WHERE tenant_id = ?",
                tparam,
            )
        ca, cd = c.fetchone() or (0, 0)

        conn.close()
        return {
            "total_mutations": total_mutations,
            "last_update": last_update,
            "mutations_by_action": mutations_by_action,
            "top_files": top_files,
            "rag_hit_rate": rag_hit_rate,
            "total_queries": total_q,
            "avg_response_ms": avg_ms or 0,
            "total_chunks_added": ca or 0,
            "total_chunks_deleted": cd or 0,
            "daily_mutations": daily_mutations,
        }
    except Exception as e:
        return {"error": str(e)}


def purge_tenant_analytics(tenant_id: int) -> dict:
    """Delete analytics rows scoped to a tenant."""
    tid = _coerce_tenant_id(tenant_id)
    counts: dict[str, int] = {}
    tables = (
        "satisfaction_ratings",
        "usage_stats",
        "session_analytics",
        "kb_document_versions",
    )
    conn = sqlite3.connect(ANALYTICS_DB)
    cursor = conn.cursor()
    try:
        for table in tables:
            cursor.execute(f"DELETE FROM {table} WHERE tenant_id = ?", (tid,))
            counts[table] = cursor.rowcount if cursor.rowcount >= 0 else 0
        conn.commit()
    finally:
        conn.close()
    return counts
