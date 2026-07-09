"""Auth unit tests — run against the in-memory db fallback (no AWS needed)."""

import jwt as pyjwt
import pytest
from fastapi.testclient import TestClient

from api import db
from api.auth_utils import (
    create_token,
    decode_token,
    hash_password,
    verify_password,
)
from api.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _clean_db():
    db._mem_users.clear()
    db._mem_runs.clear()
    yield


# ── Primitives ────────────────────────────────────────────────────────────────
def test_password_roundtrip():
    h = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", h)
    assert not verify_password("wrong", h)
    assert not verify_password("x", "not-even-base64!!")


def test_token_roundtrip():
    t = create_token("u1", "a@b.com", "Alice", "admin")
    p = decode_token(t)
    assert p["sub"] == "u1"
    assert p["role"] == "admin"
    with pytest.raises(pyjwt.PyJWTError):
        decode_token(t + "tampered")


# ── Endpoints ─────────────────────────────────────────────────────────────────
def _signup(email="alice@example.com", password="password123", name="Alice"):
    return client.post(
        "/api/auth/signup", json={"email": email, "password": password, "name": name}
    )


def test_signup_first_user_is_admin():
    r = _signup()
    assert r.status_code == 200
    body = r.json()
    assert body["user"]["role"] == "admin"
    assert "password_hash" not in body["user"]

    r2 = _signup(email="bob@example.com", name="Bob")
    assert r2.json()["user"]["role"] == "user"


def test_signup_validation():
    assert _signup(password="short").status_code == 400
    assert _signup(name="  ").status_code == 400
    _signup()
    assert _signup().status_code == 409  # duplicate email


def test_signup_domain_allowlist(monkeypatch):
    monkeypatch.setenv("ALLOWED_SIGNUP_EMAIL_DOMAINS", "corp.com")
    assert _signup(email="eve@evil.com").status_code == 403
    assert _signup(email="ok@corp.com").status_code == 200


def test_login_and_me():
    _signup()
    r = client.post(
        "/api/auth/login", json={"email": "alice@example.com", "password": "password123"}
    )
    assert r.status_code == 200
    token = r.json()["token"]

    bad = client.post(
        "/api/auth/login", json={"email": "alice@example.com", "password": "nope"}
    )
    assert bad.status_code == 401

    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["user"]["email"] == "alice@example.com"

    assert client.get("/api/auth/me").status_code == 401


def test_okta_disabled_by_default():
    assert client.get("/api/auth/okta/config").json() == {"enabled": False}
