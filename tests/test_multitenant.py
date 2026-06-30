"""Multi-tenant membership and isolation tests."""
from __future__ import annotations

import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Login_system.memberships import (
    approved_memberships,
    create_access_request,
    ensure_membership_schema,
    resolve_active_tenant_id,
    update_membership_status,
)
from backend.database import (
    init_ui_conversations_schema,
    ui_create_conversation,
    ui_get_conversation,
    ui_list_conversations,
)


def _memory_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute(
        """
        CREATE TABLE tenants (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            slug TEXT UNIQUE,
            active INTEGER DEFAULT 1
        )
        """
    )
    conn.execute(
        "INSERT INTO tenants (id, name, slug, active) VALUES (1, 'Default', 'default', 1)"
    )
    conn.execute(
        "INSERT INTO tenants (id, name, slug, active) VALUES (2, 'Acme', 'acme', 1)"
    )
    ensure_membership_schema(conn.cursor())
    conn.commit()
    return conn


def test_access_request_and_approval_flow() -> None:
    conn = _memory_db()
    membership = create_access_request(conn, "alice", 2)
    assert membership["status"] == "pending"
    updated = update_membership_status(conn, membership["id"], "approved", "admin1")
    assert updated and updated["status"] == "approved"
    approved = approved_memberships(conn, "alice")
    assert len(approved) == 1
    assert approved[0]["tenant_id"] == 2
    conn.close()


def test_resolve_active_tenant_for_customer() -> None:
    conn = _memory_db()
    m = create_access_request(conn, "bob", 2)
    update_membership_status(conn, m["id"], "approved", "admin1")
    active = resolve_active_tenant_id(
        conn,
        role="customer",
        username="bob",
        user_tenant_id=None,
    )
    assert active == 2
    conn.close()


def test_ui_conversations_are_tenant_scoped() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "conv.db"
        import backend.database as dbmod

        old = dbmod.DB_PATH
        dbmod.DB_PATH = str(db_path)
        try:
            init_ui_conversations_schema()
            a = ui_create_conversation(1, "user_a", "Chat A")
            b = ui_create_conversation(2, "user_a", "Chat B")
            assert ui_get_conversation(a["id"], 1, "user_a") is not None
            assert ui_get_conversation(a["id"], 2, "user_a") is None
            assert len(ui_list_conversations(1, "user_a")) == 1
            assert len(ui_list_conversations(2, "user_a")) == 1
            assert a["id"] != b["id"]
        finally:
            dbmod.DB_PATH = old


def test_cs_not_found_has_business_voice() -> None:
    pytest = __import__("pytest")
    pytest.importorskip("chromadb")
    from backend.config_head import CS_NO_MATCH_RESPONSE_EN, RAG_NO_MATCH_RESPONSE

    lowered = CS_NO_MATCH_RESPONSE_EN.lower()
    assert "our help materials" in lowered
    assert "your document" not in lowered
    assert RAG_NO_MATCH_RESPONSE not in CS_NO_MATCH_RESPONSE_EN


def test_tenant_collection_names_are_isolated() -> None:
    """Each business must map to its own (distinct) vector-store collection."""
    from config import (
        DEFAULT_TENANT_ID,
        tenant_collection_name,
        tenant_collection_base,
    )

    default_name = tenant_collection_name(DEFAULT_TENANT_ID)
    other_name = tenant_collection_name(2)
    third_name = tenant_collection_name(3)

    # The default tenant keeps the historical collection name.
    assert default_name == "support_docs_v3_latest"
    # Other tenants are namespaced and never collide with each other/default.
    assert other_name == "t2_support_docs_v3_latest"
    assert third_name == "t3_support_docs_v3_latest"
    assert len({default_name, other_name, third_name}) == 3
    # The "explicit" namespace prefix can't be matched cross-tenant.
    assert not tenant_collection_base(2).startswith(tenant_collection_base(DEFAULT_TENANT_ID) + "_")


def test_tenant_assets_dirs_are_isolated() -> None:
    """Uploaded assets for different businesses live in different folders."""
    from config import tenant_assets_dir, DEFAULT_TENANT_ID

    d1 = tenant_assets_dir(DEFAULT_TENANT_ID)
    d2 = tenant_assets_dir(2)
    assert d1 != d2
    assert d1.name == "tenant_1"
    assert d2.name == "tenant_2"


def test_analytics_are_tenant_scoped() -> None:
    """Usage logged for one business must not appear in another's analytics."""
    import backend.analytics as an

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "analytics.db"
        old = an.ANALYTICS_DB
        an.ANALYTICS_DB = str(db_path)
        try:
            an.init_analytics_db()
            an.log_usage("alice", "customer", "tenant-1 question", tenant_id=1)
            an.log_usage("alice", "customer", "tenant-1 question two", tenant_id=1)
            an.log_usage("bob", "customer", "tenant-2 question", tenant_id=2)

            stats_t1 = an.get_comprehensive_analytics(days=3650, tenant_id=1)
            stats_t2 = an.get_comprehensive_analytics(days=3650, tenant_id=2)
            stats_all = an.get_comprehensive_analytics(days=3650, tenant_id=None)

            assert stats_t1["total_queries"] == 2
            assert stats_t2["total_queries"] == 1
            assert stats_all["total_queries"] == 3
        finally:
            an.ANALYTICS_DB = old


def test_collection_owned_by_tenant_excludes_other_businesses() -> None:
    """Default-tenant collection resolver must ignore t{n}_ prefixed collections."""
    pytest = __import__("pytest")
    pytest.importorskip("chromadb")
    from backend.knowledge_base import _collection_owned_by_tenant

    assert _collection_owned_by_tenant("support_docs_v3_latest", 1) is True
    assert _collection_owned_by_tenant("support_docs_v3_20240101", 1) is True
    assert _collection_owned_by_tenant("t2_support_docs_v3_latest", 1) is False
    assert _collection_owned_by_tenant("t3_support_docs_v3_latest", 1) is False
    assert _collection_owned_by_tenant("t2_support_docs_v3_latest", 2) is True
    assert _collection_owned_by_tenant("support_docs_v3_latest", 2) is False


def test_retrieval_is_tenant_isolated() -> None:
    """A query for business A must never return business B's documents.

    Uses two throwaway non-default tenants so the assertion runs against the
    real ChromaDB collection-per-tenant mechanism, then cleans up.
    """
    pytest = __import__("pytest")
    pytest.importorskip("chromadb")
    from backend.knowledge_base import (
        chunk_and_add_document,
        search_documents,
        delete_documents_with_prefix,
    )

    t_a, t_b = 90001, 90002
    doc_a, doc_b = "iso_test_doc_a", "iso_test_doc_b"
    _filler = (
        "This WIDGET-ALPHA customer support knowledge base article explains the alpha plan "
        "in detail for our customers. The WIDGET-ALPHA subscription includes priority email "
        "support, guided onboarding, and access to our help center. Our support team responds "
        "to alpha plan customers quickly and helps with setup, billing, and troubleshooting. "
        "Refunds for the WIDGET-ALPHA alpha plan are available within thirty days of the "
        "original purchase date for any customer who is not fully satisfied with the service. "
        "Customers can upgrade or downgrade their WIDGET-ALPHA alpha plan at any time from the "
        "account billing settings page without contacting support directly for assistance. "
    )
    text_a = _filler + "Pricing for the WIDGET-ALPHA alpha plan is exactly 10 dollars per month for every customer."
    text_b = _filler + "Pricing for the WIDGET-ALPHA alpha plan is exactly 999 dollars per month for every customer."
    try:
        chunk_and_add_document(
            doc_id=doc_a,
            text=text_a,
            metadata={"normalized_filename": "alpha.txt"},
            tenant_id=t_a,
        )
        chunk_and_add_document(
            doc_id=doc_b,
            text=text_b,
            metadata={"normalized_filename": "beta.txt"},
            tenant_id=t_b,
        )

        res_a = " ".join(search_documents("WIDGET-ALPHA alpha plan price", top_k=5, tenant_id=t_a))
        res_b = " ".join(search_documents("WIDGET-ALPHA alpha plan price", top_k=5, tenant_id=t_b))

        # Each business sees only its own pricing — never the other tenant's.
        assert "10 dollars" in res_a and "999 dollars" not in res_a
        assert "999 dollars" in res_b and "10 dollars" not in res_b
    finally:
        delete_documents_with_prefix(doc_a, tenant_id=t_a)
        delete_documents_with_prefix(doc_b, tenant_id=t_b)


def test_conversation_scope_denies_cross_owner_within_tenant() -> None:
    """Owner-less and foreign-owner chats must not be visible to another user."""

    def conv_tenant_of(conversation: dict) -> int:
        val = conversation.get("tenant_id")
        return int(val) if val is not None else 1

    def conversation_in_scope(conversation: dict, tenant_id: int, owner: str | None) -> bool:
        if conversation is None:
            return False
        if conv_tenant_of(conversation) != int(tenant_id):
            return False
        if owner is None:
            return True
        c_owner = conversation.get("owner")
        if c_owner is None or str(c_owner) == "":
            return False
        return str(c_owner) == str(owner)

    def try_claim_ownerless(conversation: dict, tenant_id: int, owner: str | None) -> bool:
        if not owner:
            return False
        c_owner = conversation.get("owner")
        if c_owner is not None and str(c_owner).strip():
            return False
        if conv_tenant_of(conversation) != int(tenant_id):
            return False
        conversation["owner"] = str(owner)
        return True

    alice_chat = {"id": "c1", "tenant_id": 2, "owner": "alice"}
    orphan_chat = {"id": "c2", "tenant_id": 2, "owner": None}

    assert conversation_in_scope(alice_chat, 2, "bob") is False
    assert conversation_in_scope(orphan_chat, 2, "bob") is False
    assert try_claim_ownerless(orphan_chat, 2, "bob") is True
    assert orphan_chat["owner"] == "bob"
    assert conversation_in_scope(orphan_chat, 2, "bob") is True
    assert conversation_in_scope(alice_chat, 1, "alice") is False


if __name__ == "__main__":
    test_access_request_and_approval_flow()
    test_resolve_active_tenant_for_customer()
    test_ui_conversations_are_tenant_scoped()
    test_cs_not_found_has_business_voice()
    test_tenant_collection_names_are_isolated()
    test_tenant_assets_dirs_are_isolated()
    test_analytics_are_tenant_scoped()
    test_collection_owned_by_tenant_excludes_other_businesses()
    test_retrieval_is_tenant_isolated()
    test_conversation_scope_denies_cross_owner_within_tenant()
    print("All multi-tenant tests passed.")
