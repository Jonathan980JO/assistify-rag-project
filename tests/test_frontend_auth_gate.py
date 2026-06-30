"""Regression tests for /frontend/ server-side auth gate."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import ALLOW_PUBLIC_GUEST_CHAT, SESSION_COOKIE
from Login_system.login_server import app, create_session_token


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


def test_unauthenticated_frontend_root_redirects_to_login(client: TestClient) -> None:
    response = client.get("/frontend/", follow_redirects=False)
    assert response.status_code == 307
    assert "/frontend/login" in response.headers.get("location", "")


def test_unauthenticated_admin_knowledge_redirects_to_login(client: TestClient) -> None:
    response = client.get("/frontend/admin/knowledge/", follow_redirects=False)
    assert response.status_code == 307
    assert "/frontend/login" in response.headers.get("location", "")


def test_unauthenticated_login_page_is_public(client: TestClient) -> None:
    response = client.get("/frontend/login/", follow_redirects=False)
    assert response.status_code == 200


@pytest.mark.skipif(not ALLOW_PUBLIC_GUEST_CHAT, reason="Guest chat disabled")
def test_unauthenticated_guest_page_is_public(client: TestClient) -> None:
    response = client.get("/frontend/guest/", follow_redirects=False)
    assert response.status_code == 200


def test_unauthenticated_head_frontend_returns_401(client: TestClient) -> None:
    response = client.head("/frontend/", follow_redirects=False)
    assert response.status_code == 401


def test_authenticated_admin_can_load_protected_frontend(client: TestClient) -> None:
    token = create_session_token("admin", "admin")
    response = client.get(
        "/frontend/admin/knowledge/",
        cookies={SESSION_COOKIE: token},
        follow_redirects=False,
    )
    assert response.status_code == 200
