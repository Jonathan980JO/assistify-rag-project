"""Tests for per-conversation tenant selector and chat store."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend import chat_store
from backend.tenant_access import assert_chat_tenant_allowed, list_active_chat_tenants


def test_chat_store_per_message_tenant_and_active_state() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "chat.db"
        chat_store.DB_PATH = str(db_path)
        chat_store.init_chat_store_schema()

        conv = chat_store.create_conversation(owner="alice", active_tenant_id=1, title="Multi")
        cid = conv["id"]

        chat_store.append_message(cid, "user", "University question?", 1, owner="alice")
        chat_store.set_active_tenant(
            cid,
            2,
            owner="alice",
            system_message="Switched from Tenant #1 to Tenant #2",
            message_tenant_id=2,
        )
        chat_store.append_message(cid, "user", "Hospital question?", 2, owner="alice")

        loaded = chat_store.get_conversation(cid, "alice")
        assert loaded is not None
        assert loaded["active_tenant_id"] == 2
        assert len(loaded["messages"]) == 3
        assert loaded["messages"][0]["tenant_id"] == 1
        assert loaded["messages"][1]["role"] == "system"
        assert loaded["messages"][2]["tenant_id"] == 2

        assert chat_store.get_conversation(cid, "bob") is None


def test_list_conversations_owner_scoped_not_tenant_scoped() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "chat.db"
        chat_store.DB_PATH = str(db_path)
        chat_store.init_chat_store_schema()

        c1 = chat_store.create_conversation(owner="alice", active_tenant_id=1)
        chat_store.create_conversation(owner="alice", active_tenant_id=2)
        chat_store.create_conversation(owner="bob", active_tenant_id=1)

        alice_list = chat_store.list_conversations_summary(owner="alice")
        assert len(alice_list) == 2
        ids = {x["id"] for x in alice_list}
        assert c1["id"] in ids


def test_assert_chat_tenant_allowed_with_users_db() -> None:
    users_db = ROOT / "Login_system" / "users.db"
    if not users_db.exists():
        return
    tid = assert_chat_tenant_allowed(None, 1)
    assert tid == 1
    tenants = list_active_chat_tenants()
    assert isinstance(tenants, list)


def test_guest_owner_isolation() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "chat.db"
        chat_store.DB_PATH = str(db_path)
        chat_store.init_chat_store_schema()

        guest_a = "guest_" + ("a" * 32)
        guest_b = "guest_" + ("b" * 32)
        conv_a = chat_store.create_conversation(owner=guest_a, active_tenant_id=1)
        chat_store.create_conversation(owner=guest_b, active_tenant_id=2)

        assert chat_store.get_conversation(conv_a["id"], guest_a) is not None
        assert chat_store.get_conversation(conv_a["id"], guest_b) is None
        assert len(chat_store.list_conversations_summary(owner=guest_a)) == 1
        assert len(chat_store.list_conversations_summary(owner=guest_b)) == 1


def test_migrate_json_backfill_tenant_id() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "chat.db"
        json_path = Path(tmp) / "conversations.json"
        chat_store.DB_PATH = str(db_path)
        chat_store.init_chat_store_schema()

        payload = {
            "conversations": [
                {
                    "id": "legacy-1",
                    "title": "Old",
                    "tenant_id": 1,
                    "owner": "legacy_user",
                    "messages": [{"role": "user", "text": "hello"}],
                    "created_at": "2026-01-01T00:00:00+00:00",
                    "updated_at": "2026-01-01T00:00:00+00:00",
                }
            ]
        }
        json_path.write_text(json.dumps(payload), encoding="utf-8")
        n = chat_store.migrate_from_json(json_path, default_tenant_id=1)
        assert n == 1
        conv = chat_store.get_conversation("legacy-1", "legacy_user")
        assert conv is not None
        assert conv["messages"][0]["tenant_id"] == 1
        assert conv["active_tenant_id"] == 1
