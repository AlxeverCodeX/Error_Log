import os
import tempfile

# Must be set before server is imported: it reads both at import time.
os.environ["JWT_SECRET"] = "test-secret-" + "x" * 40
os.environ["DATABASE_PATH"] = os.path.join(tempfile.gettempdir(), "error_log_unused_test.db")

import pytest
from fastapi.testclient import TestClient

import server


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    path = str(tmp_path / "test.db")
    monkeypatch.setattr(server, "DB_PATH", path)
    server.init_db()
    return path


@pytest.fixture
def client(db_path):
    with TestClient(server.app) as c:
        yield c


@pytest.fixture
def make_user(db_path):
    def _make_user(username="alice", password="correct-horse"):
        user_id = server.gen_id()
        with server.get_conn() as conn:
            conn.execute(
                "INSERT INTO users (id, username, password_hash, created_at) VALUES (?,?,?,?)",
                (user_id, username, server.hash_password(password), "2026-10-15T00:00:00+00:00"),
            )
        return user_id
    return _make_user
