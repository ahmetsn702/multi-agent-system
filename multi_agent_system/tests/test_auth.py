"""
tests/test_auth.py
Auth, session management, and brute force protection tests.
"""
import os
from datetime import datetime, timedelta

import pytest

os.environ.setdefault("WEB_PASSWORD", "testpass123")

from api.main_api import (
    _auth_sessions,
    _create_session,
    _is_valid_session,
    _invalidate_session,
    _verify_password,
    _is_locked,
    _record_failed,
    _clear_attempts,
    _login_attempts,
    _cleanup_expired_sessions,
    _get_csrf_token,
    MAX_ATTEMPTS,
)


@pytest.fixture(autouse=True)
def clean_state():
    _auth_sessions.clear()
    _login_attempts.clear()
    yield
    _auth_sessions.clear()
    _login_attempts.clear()


# ── Password verification ─────────────────────────────────────────────────────

def test_verify_correct_password():
    assert _verify_password("testpass123") is True


def test_verify_wrong_password():
    assert _verify_password("wrong") is False


def test_verify_empty_password():
    assert _verify_password("") is False


# ── Session lifecycle ─────────────────────────────────────────────────────────

def test_create_session():
    token = _create_session()
    assert len(token) > 20
    assert token in _auth_sessions
    assert "created_at" in _auth_sessions[token]
    assert "csrf_token" in _auth_sessions[token]


def test_valid_session():
    token = _create_session()
    assert _is_valid_session(token) is True


def test_invalid_session():
    assert _is_valid_session("nonexistent") is False
    assert _is_valid_session(None) is False
    assert _is_valid_session("") is False


def test_invalidate_session():
    token = _create_session()
    _invalidate_session(token)
    assert _is_valid_session(token) is False


def test_session_expiry():
    token = _create_session()
    # Backdate the session to 31 days ago
    _auth_sessions[token]["created_at"] = datetime.now() - timedelta(days=31)
    assert _is_valid_session(token) is False
    assert token not in _auth_sessions  # Should be cleaned up


# ── CSRF token ────────────────────────────────────────────────────────────────

def test_csrf_token_present():
    token = _create_session()
    csrf = _get_csrf_token(token)
    assert len(csrf) > 10


def test_csrf_token_missing_session():
    assert _get_csrf_token("nonexistent") == ""
    assert _get_csrf_token(None) == ""


# ── Session cleanup ───────────────────────────────────────────────────────────

def test_cleanup_expired_sessions():
    # Create fresh and expired sessions
    fresh = _create_session()
    expired = _create_session()
    _auth_sessions[expired]["created_at"] = datetime.now() - timedelta(days=31)

    removed = _cleanup_expired_sessions()
    assert removed == 1
    assert _is_valid_session(fresh) is True
    assert expired not in _auth_sessions


# ── Brute force protection ────────────────────────────────────────────────────

def test_not_locked_initially():
    locked, _ = _is_locked("1.2.3.4")
    assert locked is False


def test_lockout_after_max_attempts():
    ip = "10.0.0.1"
    for _ in range(MAX_ATTEMPTS):
        _record_failed(ip)
    locked, remaining = _is_locked(ip)
    assert locked is True
    assert remaining > 0


def test_clear_attempts():
    ip = "10.0.0.2"
    for _ in range(3):
        _record_failed(ip)
    _clear_attempts(ip)
    locked, _ = _is_locked(ip)
    assert locked is False
