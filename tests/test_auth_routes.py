import sqlite3

import jwt
import pytest
from fastapi.testclient import TestClient

import server

PASSWORD = "correct-horse"


def register(client, username="alice", password=PASSWORD, **extra):
    return client.post("/api/auth/register", json={"username": username, "password": password, **extra})


def login(client, username="alice", password=PASSWORD):
    return client.post("/api/auth/login", data={"username": username, "password": password})


# ---------- Registration ----------
def test_register_creates_user_with_hashed_password(client, db_path):
    r = register(client)
    assert r.status_code == 201
    body = r.json()
    assert set(body) == {"id", "username"}
    assert body["username"] == "alice"
    with sqlite3.connect(db_path) as conn:
        stored = conn.execute("SELECT password_hash FROM users WHERE id=?", (body["id"],)).fetchone()[0]
    assert stored.startswith("$2b$")
    assert PASSWORD not in stored


def test_register_ignores_role_field_sent_by_old_login_page(client):
    r = register(client, role="admin")
    assert r.status_code == 201
    assert "role" not in r.json()


def test_register_strips_surrounding_whitespace(client):
    assert register(client, username="  alice  ").json()["username"] == "alice"


@pytest.mark.parametrize("username", ["alice", "ALICE", "Alice"])
def test_register_duplicate_username_any_case(client, username):
    assert register(client, username="alice").status_code == 201
    r = register(client, username=username)
    assert r.status_code == 409
    assert r.json()["detail"] == "Username already taken"


@pytest.mark.parametrize("username", ["ab", "a" * 33, "has space", "semi;colon", ""])
def test_register_rejects_invalid_username(client, username):
    assert register(client, username=username).status_code == 422


def test_register_rejects_short_password(client):
    assert register(client, password="a" * 7).status_code == 422


def test_register_password_byte_limit_counts_utf8_bytes(client):
    assert register(client, username="exact72", password="é" * 36).status_code == 201
    assert register(client, username="over72", password="é" * 37).status_code == 422


def test_register_requires_both_fields(client):
    assert client.post("/api/auth/register", json={"username": "alice"}).status_code == 422
    assert client.post("/api/auth/register", json={"password": PASSWORD}).status_code == 422


# ---------- Login ----------
def test_login_returns_bearer_token_for_user(client):
    user_id = register(client).json()["id"]
    r = login(client)
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer"
    payload = jwt.decode(body["access_token"], server.JWT_SECRET, algorithms=["HS256"])
    assert payload["sub"] == user_id


def test_login_username_is_case_insensitive(client):
    register(client, username="Alice")
    assert login(client, username="alice").status_code == 200


def test_wrong_password_and_unknown_user_look_identical(client):
    register(client)
    wrong_password = login(client, password="wrong-horse")
    unknown_user = login(client, username="nobody")
    for r in (wrong_password, unknown_user):
        assert r.status_code == 401
        assert r.headers["www-authenticate"] == "Bearer"
    assert wrong_password.json() == unknown_user.json() == {"detail": "Incorrect username or password"}


def test_login_with_overlong_password_is_401_not_500(client):
    register(client)
    assert login(client, password="a" * 100).status_code == 401


def test_login_requires_form_body(client):
    register(client)
    r = client.post("/api/auth/login", json={"username": "alice", "password": PASSWORD})
    assert r.status_code == 422


# ---------- /me and /login ----------
def test_full_flow_register_login_me(client):
    user_id = register(client).json()["id"]
    token = login(client).json()["access_token"]
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json() == {"id": user_id, "username": "alice"}


def test_me_requires_token(client):
    r = client.get("/api/auth/me")
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == "Bearer"


def test_login_page_is_served(client):
    r = client.get("/login")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert "/api/auth/login" in r.text


# ---------- Database created by the earlier version ----------
def test_register_and_login_on_old_users_schema(tmp_path, monkeypatch):
    path = str(tmp_path / "old.db")
    with sqlite3.connect(path) as conn:
        conn.execute("""
        CREATE TABLE users (
            id TEXT PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'admin',
            created_at TEXT NOT NULL
        )""")
    conn.close()
    monkeypatch.setattr(server, "DB_PATH", path)
    with TestClient(server.app) as client:
        assert register(client, username="alice").status_code == 201
        assert register(client, username="ALICE").status_code == 409
        assert login(client, username="Alice").status_code == 200
