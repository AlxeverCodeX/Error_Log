from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

import server


# ---------- Passwords ----------
def test_hash_password_is_salted_bcrypt():
    first = server.hash_password("correct-horse")
    second = server.hash_password("correct-horse")
    assert first.startswith("$2b$")
    assert "correct-horse" not in first
    assert first != second


def test_verify_password():
    stored = server.hash_password("correct-horse")
    assert server.verify_password("correct-horse", stored)
    assert not server.verify_password("wrong-horse", stored)


def test_verify_password_rejects_over_72_bytes_without_raising():
    stored = server.hash_password("a" * 72)
    assert not server.verify_password("a" * 73, stored)


def test_verify_password_handles_malformed_hash():
    assert not server.verify_password("correct-horse", "not-a-bcrypt-hash")


# ---------- JWT secret ----------
def test_jwt_secret_from_env(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "s" * 32)
    assert server.load_jwt_secret() == "s" * 32


def test_jwt_secret_too_short_fails_fast(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "short")
    with pytest.raises(RuntimeError):
        server.load_jwt_secret()


def test_jwt_secret_missing_generates_random_key(monkeypatch):
    monkeypatch.delenv("JWT_SECRET", raising=False)
    first, second = server.load_jwt_secret(), server.load_jwt_secret()
    assert len(first) >= server.JWT_MIN_SECRET_LENGTH
    assert first != second


# ---------- Tokens ----------
def make_token(**overrides):
    now = datetime.now(timezone.utc)
    payload = {"sub": "abc123", "iat": now, "exp": now + timedelta(minutes=5)}
    payload.update(overrides)
    payload = {k: v for k, v in payload.items() if v is not None}
    return jwt.encode(payload, server.JWT_SECRET, algorithm="HS256")


def test_token_round_trip():
    token = server.create_access_token("abc123")
    assert server.decode_access_token(token) == "abc123"


def test_token_expiry_matches_config():
    token = server.create_access_token("abc123")
    payload = jwt.decode(token, server.JWT_SECRET, algorithms=["HS256"])
    assert payload["exp"] - payload["iat"] == server.JWT_EXPIRE_MINUTES * 60


def test_expired_token_rejected():
    past = datetime.now(timezone.utc) - timedelta(minutes=10)
    assert server.decode_access_token(make_token(iat=past, exp=past + timedelta(minutes=1))) is None


def test_token_signed_with_other_secret_rejected():
    token = jwt.encode({"sub": "abc123", "iat": 0, "exp": 9999999999}, "o" * 40, algorithm="HS256")
    assert server.decode_access_token(token) is None


def test_unsigned_alg_none_token_rejected():
    token = jwt.encode({"sub": "abc123", "iat": 0, "exp": 9999999999}, None, algorithm="none")
    assert server.decode_access_token(token) is None


@pytest.mark.parametrize("missing", ["sub", "exp", "iat"])
def test_token_missing_required_claim_rejected(missing):
    assert server.decode_access_token(make_token(**{missing: None})) is None


def test_garbage_token_rejected():
    assert server.decode_access_token("not.a.jwt") is None


# ---------- get_current_user ----------
@pytest.fixture
def whoami(db_path):
    app = FastAPI()

    @app.get("/whoami", response_model=server.UserOut)
    def _whoami(user: server.UserOut = Depends(server.get_current_user)):
        return user

    return TestClient(app)


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def test_current_user_with_valid_token(whoami, make_user):
    user_id = make_user("alice")
    r = whoami.get("/whoami", headers=bearer(server.create_access_token(user_id)))
    assert r.status_code == 200
    assert r.json() == {"id": user_id, "username": "alice"}


def test_current_user_without_token(whoami):
    r = whoami.get("/whoami")
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == "Bearer"


def test_current_user_with_invalid_token(whoami):
    r = whoami.get("/whoami", headers=bearer("not.a.jwt"))
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == "Bearer"


def test_current_user_deleted_after_token_issued(whoami, make_user):
    user_id = make_user("alice")
    token = server.create_access_token(user_id)
    with server.get_conn() as conn:
        conn.execute("DELETE FROM users WHERE id=?", (user_id,))
    assert whoami.get("/whoami", headers=bearer(token)).status_code == 401
