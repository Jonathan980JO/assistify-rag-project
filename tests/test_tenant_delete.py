"""Tests for permanent tenant deletion (superadmin delete business)."""
from __future__ import annotations

import sqlite3
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Login_system.memberships import ensure_membership_schema
from Login_system.tenant_lifecycle import delete_tenant_permanently, purge_tenant_users_db
from backend import analytics as analytics_mod
from backend import chat_store


def _memory_users_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    c = conn.cursor()
    c.execute(
        """
        CREATE TABLE tenants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            slug TEXT UNIQUE NOT NULL,
            active INTEGER DEFAULT 1,
            plan TEXT DEFAULT 'standard',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    c.execute(
        """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT,
            role TEXT NOT NULL,
            tenant_id INTEGER DEFAULT 1,
            active INTEGER DEFAULT 1
        )
        """
    )
    c.execute(
        """
        CREATE TABLE audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            action TEXT,
            old_value TEXT,
            new_value TEXT,
            ip_address TEXT,
            performed_by TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    c.execute(
        """
        CREATE TABLE support_tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_number TEXT UNIQUE NOT NULL,
            customer_id INTEGER NOT NULL,
            customer_username TEXT NOT NULL,
            subject TEXT NOT NULL,
            description TEXT NOT NULL,
            tenant_id INTEGER DEFAULT 1
        )
        """
    )
    c.execute(
        """
        CREATE TABLE ticket_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER NOT NULL,
            sender_username TEXT NOT NULL,
            sender_role TEXT NOT NULL,
            message TEXT NOT NULL
        )
        """
    )
    c.execute(
        """
        CREATE TABLE notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_username TEXT NOT NULL,
            user_role TEXT NOT NULL,
            notification_type TEXT NOT NULL,
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            related_ticket_id INTEGER
        )
        """
    )
    c.execute(
        """
        CREATE TABLE customer_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            customer_username TEXT NOT NULL,
            note TEXT NOT NULL,
            created_by TEXT NOT NULL
        )
        """
    )
    ensure_membership_schema(c)
    c.execute(
        "INSERT INTO tenants (id, name, slug, active) VALUES (1, 'Default', 'default', 1)"
    )
    c.execute(
        "INSERT INTO tenants (id, name, slug, active) VALUES (2, 'Acme', 'acme', 0)"
    )
    c.execute(
        "INSERT INTO users (username, password_hash, role, tenant_id) VALUES ('ma1', 'x', 'master_admin', 2)"
    )
    c.execute(
        "INSERT INTO users (username, password_hash, role, tenant_id) VALUES ('cust1', 'x', 'customer', 1)"
    )
    c.execute(
        "INSERT INTO tenant_memberships (username, tenant_id, status) VALUES ('cust1', 2, 'approved')"
    )
    c.execute(
        """
        INSERT INTO support_tickets (ticket_number, customer_id, customer_username, subject, description, tenant_id)
        VALUES ('T-001', 2, 'cust1', 'Help', 'Need help', 2)
        """
    )
    conn.commit()
    return conn


def test_cannot_delete_default_tenant() -> None:
    conn = _memory_users_db()
    with pytest.raises(PermissionError):
        delete_tenant_permanently(conn, 1, performed_by="superadmin")
    conn.close()


def test_cannot_delete_active_tenant() -> None:
    conn = _memory_users_db()
    conn.execute("INSERT INTO tenants (name, slug, active) VALUES ('Beta', 'beta', 1)")
    conn.commit()
    tenant_id = conn.execute("SELECT id FROM tenants WHERE slug='beta'").fetchone()[0]
    with pytest.raises(RuntimeError):
        delete_tenant_permanently(conn, tenant_id, performed_by="superadmin")
    conn.close()


def test_delete_inactive_tenant_purges_users_db() -> None:
    conn = _memory_users_db()
    result = delete_tenant_permanently(conn, 2, performed_by="superadmin", ip_address="127.0.0.1")
    assert result["status"] == "deleted"
    assert result["tenant_id"] == 2
    assert result["users_deleted"] == 1
    assert result["memberships_deleted"] == 1
    assert result["tickets_deleted"] == 1

    assert conn.execute("SELECT id FROM tenants WHERE id=2").fetchone() is None
    assert conn.execute("SELECT id FROM users WHERE tenant_id=2").fetchone() is None
    assert conn.execute("SELECT id FROM tenant_memberships WHERE tenant_id=2").fetchone() is None
    assert conn.execute("SELECT id FROM support_tickets WHERE tenant_id=2").fetchone() is None
    assert conn.execute("SELECT id FROM users WHERE username='cust1'").fetchone() is not None

    audit = conn.execute(
        "SELECT action FROM audit_logs WHERE action='SUPERADMIN_TENANT_DELETE'"
    ).fetchone()
    assert audit is not None
    conn.close()


def test_purge_tenant_users_db_only() -> None:
    conn = _memory_users_db()
    summary = purge_tenant_users_db(conn, 2)
    conn.commit()
    assert summary["users_deleted"] == 1
    assert summary["memberships_deleted"] == 1
    assert conn.execute("SELECT id FROM tenants WHERE id=2").fetchone() is None
    conn.close()


def test_purge_tenant_chat_data() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "chat.db"
        chat_store.DB_PATH = str(db_path)
        chat_store.init_chat_store_schema()

        conv = chat_store.create_conversation(owner="alice", active_tenant_id=2, title="Test")
        cid = conv["id"]
        chat_store.append_message(cid, "user", "Hello", 2, owner="alice")
        chat_store.append_message(cid, "assistant", "Hi", 2, owner="alice")

        result = chat_store.purge_tenant_chat_data(2)
        assert result["messages_deleted"] == 2
        assert result["states_reset"] == 1

        active = chat_store.get_active_tenant_id(cid, owner="alice")
        assert active == 1
        messages = chat_store.load_conversation_messages(cid, owner="alice")
        assert messages == []


def test_purge_tenant_analytics() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        analytics_mod.ANALYTICS_DB = str(Path(tmp) / "analytics.db")
        analytics_mod.init_analytics_db()
        analytics_mod.log_usage("alice", "customer", "test query", tenant_id=2)
        analytics_mod.log_satisfaction("alice", "customer", 5, tenant_id=2)

        counts = analytics_mod.purge_tenant_analytics(2)
        assert counts["usage_stats"] >= 1
        assert counts["satisfaction_ratings"] >= 1

        conn = sqlite3.connect(analytics_mod.ANALYTICS_DB)
        remaining = conn.execute(
            "SELECT COUNT(*) FROM usage_stats WHERE tenant_id=2"
        ).fetchone()[0]
        conn.close()
        assert remaining == 0
