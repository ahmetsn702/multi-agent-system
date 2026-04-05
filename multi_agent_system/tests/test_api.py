"""
tests/test_api.py
FastAPI endpoint tests using TestClient.
"""
import os
import pytest
from unittest.mock import patch

# Set WEB_PASSWORD before importing the app
os.environ.setdefault("WEB_PASSWORD", "testpass123")

from fastapi.testclient import TestClient
from api.main_api import app, _auth_sessions, SESSION_COOKIE, _create_session


@pytest.fixture(autouse=True)
def clean_sessions():
    """Clear session store between tests."""
    _auth_sessions.clear()
    yield
    _auth_sessions.clear()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def auth_client(client):
    """Client with a valid session cookie."""
    token = _create_session()
    client.cookies.set(SESSION_COOKIE, token)
    return client


# ── Health ────────────────────────────────────────────────────────────────────

def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


# ── Login ─────────────────────────────────────────────────────────────────────

def test_login_page_loads(client):
    r = client.get("/login")
    assert r.status_code == 200
    assert "password" in r.text


def test_login_success(client):
    r = client.post("/login", data={"password": "testpass123"}, follow_redirects=False)
    assert r.status_code == 302
    assert SESSION_COOKIE in r.cookies


def test_login_wrong_password(client):
    r = client.post("/login", data={"password": "wrongpass"}, follow_redirects=False)
    assert r.status_code == 401


# ── Auth redirect ─────────────────────────────────────────────────────────────

def test_unauthenticated_redirect(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 302
    assert "/login" in r.headers.get("location", "")


def test_authenticated_access(auth_client):
    r = auth_client.get("/", follow_redirects=False)
    # Should serve the page, not redirect
    assert r.status_code == 200


# ── Logout ────────────────────────────────────────────────────────────────────

def test_logout(auth_client):
    r = auth_client.get("/logout", follow_redirects=False)
    assert r.status_code == 302
    assert "/login" in r.headers.get("location", "")


# ── Projects endpoint ─────────────────────────────────────────────────────────

def test_projects_list(auth_client):
    r = auth_client.get("/projects")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


# ── Sessions endpoint ─────────────────────────────────────────────────────────

def test_sessions_list(auth_client):
    r = auth_client.get("/sessions")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


# ── CSRF token endpoint ──────────────────────────────────────────────────────

def test_csrf_token_endpoint(auth_client):
    r = auth_client.get("/csrf-token")
    assert r.status_code == 200
    data = r.json()
    assert "csrf_token" in data
    assert len(data["csrf_token"]) > 0
