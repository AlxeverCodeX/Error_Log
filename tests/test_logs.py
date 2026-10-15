import sqlite3

import pytest

import server

PASSWORD = "correct-horse"


def auth_headers(client, username):
    assert client.post("/api/auth/register", json={"username": username, "password": PASSWORD}).status_code == 201
    token = client.post("/api/auth/login", data={"username": username, "password": PASSWORD}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def alice(client):
    return auth_headers(client, "alice")


@pytest.fixture
def bob(client):
    return auth_headers(client, "bob")


def new_log(**overrides):
    log = {"project": "api", "title": "Boom", "error": "Traceback...", "severity": "high",
           "status": "open", "solution": "", "tags": ["python"], "date": "2026-10-15"}
    log.update(overrides)
    return log


def create(client, headers, **overrides):
    r = client.post("/api/logs", json=new_log(**overrides), headers=headers)
    assert r.status_code == 201
    return r.json()


# ---------- Login required ----------
@pytest.mark.parametrize("method, path", [
    ("GET", "/api/logs"),
    ("POST", "/api/logs"),
    ("DELETE", "/api/logs"),
    ("PUT", "/api/logs/abc"),
    ("DELETE", "/api/logs/abc"),
    ("PATCH", "/api/logs/abc/toggle"),
])
@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer not.a.jwt"}], ids=["no-token", "bad-token"])
def test_log_routes_require_login(client, method, path, headers):
    r = client.request(method, path, json=new_log(), headers=headers)
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize("path", ["/api/health", "/", "/login"])
def test_public_routes_stay_public(client, path):
    assert client.get(path).status_code == 200


# ---------- Own logs ----------
def test_owner_can_create_list_update_toggle_delete(client, alice):
    log = create(client, alice)
    assert "user_id" not in log

    assert [l["id"] for l in client.get("/api/logs", headers=alice).json()] == [log["id"]]

    r = client.put(f"/api/logs/{log['id']}", json=new_log(title="Boom fixed", solution="Pinned dep"), headers=alice)
    assert r.status_code == 200
    assert r.json()["title"] == "Boom fixed"

    assert client.patch(f"/api/logs/{log['id']}/toggle", headers=alice).json()["status"] == "solved"

    assert client.delete(f"/api/logs/{log['id']}", headers=alice).status_code == 200
    assert client.get("/api/logs", headers=alice).json() == []


def test_new_log_is_owned_by_caller_even_if_body_names_another_user(client, alice, bob, db_path):
    alice_id = client.get("/api/auth/me", headers=alice).json()["id"]
    log = client.post("/api/logs", json={**new_log(), "user_id": alice_id}, headers=bob).json()
    assert client.get("/api/logs", headers=alice).json() == []
    with sqlite3.connect(db_path) as conn:
        owner = conn.execute("SELECT user_id FROM logs WHERE id=?", (log["id"],)).fetchone()[0]
    assert owner != alice_id


# ---------- Isolation between users ----------
def test_users_only_see_their_own_logs(client, alice, bob):
    a = create(client, alice, title="Alice's bug")
    b = create(client, bob, title="Bob's bug")
    assert [l["id"] for l in client.get("/api/logs", headers=alice).json()] == [a["id"]]
    assert [l["id"] for l in client.get("/api/logs", headers=bob).json()] == [b["id"]]


@pytest.mark.parametrize("method, suffix", [("PUT", ""), ("DELETE", ""), ("PATCH", "/toggle")])
def test_other_users_log_looks_like_it_does_not_exist(client, alice, bob, method, suffix):
    log = create(client, alice)
    theirs = client.request(method, f"/api/logs/{log['id']}{suffix}", json=new_log(title="hijacked"), headers=bob)
    missing = client.request(method, f"/api/logs/doesnotexist{suffix}", json=new_log(), headers=bob)
    assert theirs.status_code == missing.status_code == 404
    assert theirs.json() == missing.json()
    assert client.get("/api/logs", headers=alice).json() == [log]


def test_clear_all_only_clears_callers_logs(client, alice, bob):
    a = create(client, alice)
    create(client, bob)
    assert client.delete("/api/logs", headers=bob).status_code == 200
    assert client.get("/api/logs", headers=bob).json() == []
    assert client.get("/api/logs", headers=alice).json() == [a]


# ---------- Data without an owner, and deleted users ----------
def test_logs_without_owner_are_never_reachable(client, alice, db_path):
    with sqlite3.connect(db_path) as conn:
        conn.execute("INSERT INTO logs (id, project, title, severity, status, error, date) "
                     "VALUES ('orphan', 'old', 'From before auth', 'low', 'open', 'e', '2026-10-01')")
    conn.close()
    assert client.get("/api/logs", headers=alice).json() == []
    assert client.patch("/api/logs/orphan/toggle", headers=alice).status_code == 404
    assert client.delete("/api/logs/orphan", headers=alice).status_code == 404
    assert client.delete("/api/logs", headers=alice).status_code == 200
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM logs WHERE id='orphan'").fetchone()[0] == 1
    conn.close()


def test_deleting_a_user_deletes_their_logs(client, alice, bob):
    create(client, alice)
    b = create(client, bob)
    alice_id = client.get("/api/auth/me", headers=alice).json()["id"]
    with server.get_conn() as conn:
        conn.execute("DELETE FROM users WHERE id=?", (alice_id,))
        assert conn.execute("SELECT COUNT(*) FROM logs WHERE user_id=?", (alice_id,)).fetchone()[0] == 0
    assert client.get("/api/logs", headers=alice).status_code == 401
    assert client.get("/api/logs", headers=bob).json() == [b]
