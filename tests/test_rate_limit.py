import pytest

import server

PASSWORD = "correct-horse"


@pytest.fixture
def limits(monkeypatch):
    monkeypatch.setattr(server, "LOGIN_MAX_FAILURES", 3)
    monkeypatch.setattr(server, "LOGIN_MAX_FAILURES_PER_IP", 5)
    monkeypatch.setattr(server, "LOGIN_WINDOW_SECONDS", 900)


@pytest.fixture
def clock(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(server, "_clock", lambda: now[0])
    return now


def register(client, username="alice"):
    assert client.post("/api/auth/register", json={"username": username, "password": PASSWORD}).status_code == 201


def login(client, username="alice", password=PASSWORD):
    return client.post("/api/auth/login", data={"username": username, "password": password})


def test_locked_after_max_failures_even_with_right_password(client, limits, clock):
    register(client)
    for _ in range(3):
        assert login(client, password="wrong-horse").status_code == 401
    r = login(client)
    assert r.status_code == 429
    assert r.headers["retry-after"] == "900"
    assert "Too many failed sign-in attempts" in r.json()["detail"]


def test_lock_expires_after_window(client, limits, clock):
    register(client)
    for _ in range(3):
        login(client, password="wrong-horse")
    clock[0] += 899
    assert login(client).status_code == 429
    clock[0] += 1
    assert login(client).status_code == 200


def test_successful_login_resets_the_count(client, limits, clock):
    register(client)
    for _ in range(2):
        login(client, password="wrong-horse")
    assert login(client).status_code == 200
    for _ in range(2):
        assert login(client, password="wrong-horse").status_code == 401
    assert login(client).status_code == 200


def test_username_is_matched_case_insensitively(client, limits, clock):
    register(client)
    for name in ["alice", "ALICE", "Alice"]:
        login(client, username=name, password="wrong-horse")
    assert login(client).status_code == 429


def test_one_locked_user_does_not_block_another(client, limits, clock):
    register(client, "alice")
    register(client, "bob")
    for _ in range(3):
        login(client, "alice", "wrong-horse")
    assert login(client, "alice").status_code == 429
    assert login(client, "bob").status_code == 200


def test_per_ip_cap_stops_trying_many_usernames(client, limits, clock):
    register(client, "alice")
    for i in range(5):
        assert login(client, f"guess{i}", "wrong-horse").status_code == 401
    assert login(client, "alice").status_code == 429


def test_unknown_users_count_toward_the_limit(client, limits, clock):
    for _ in range(3):
        assert login(client, "nobody", "wrong-horse").status_code == 401
    assert login(client, "nobody", "wrong-horse").status_code == 429


def test_expired_entries_are_swept_when_table_is_large(limits, clock, monkeypatch):
    monkeypatch.setattr(server, "LOGIN_TRACKED_KEYS_SWEEP", 4)
    for i in range(3):
        server.record_login_failure(f"10.0.0.{i}", "someone")
    assert len(server._login_failures) == 6
    clock[0] += 901
    server.record_login_failure("10.0.0.99", "someone")
    assert len(server._login_failures) == 2


# ---------- Production secret check ----------
def test_production_requires_jwt_secret(monkeypatch):
    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "production")
    with pytest.raises(RuntimeError, match="JWT_SECRET must be set"):
        server.load_jwt_secret()


def test_production_with_secret_is_fine(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("JWT_SECRET", "p" * 40)
    assert server.load_jwt_secret() == "p" * 40
