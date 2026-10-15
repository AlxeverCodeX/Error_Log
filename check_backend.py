import os, sqlite3, sys, tempfile, traceback, shutil

# Fix Windows cp1252 console so checkmarks don't crash
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

print("=== Backend + DB + Auth Check ===\n")

# Run against a throwaway database so the real app.db is never touched.
# Both must be set before server is imported.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TMP_DIR = tempfile.mkdtemp(prefix="error_log_check_")
DB_PATH = os.path.join(TMP_DIR, "check.db")
os.environ["DATABASE_PATH"] = DB_PATH
os.environ.setdefault("JWT_SECRET", "check-backend-secret-" + "x" * 32)
print(f"1. Temporary DB_PATH: {DB_PATH}")

failures = []

def check(label, ok, detail=""):
    print(f"   [{'OK' if ok else 'FAIL'}] {label}" + (f"  ({detail})" if detail else ""))
    if not ok:
        failures.append(label)

try:
    if BASE_DIR not in sys.path:
        sys.path.insert(0, BASE_DIR)
    from fastapi.testclient import TestClient
    from server import app

    with TestClient(app) as client:
        # 2. Schema created by startup
        with sqlite3.connect(DB_PATH) as conn:
            tables = sorted(r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'"))
        conn.close()
        print(f"\n2. Tables in DB: {tables}")
        check("users and logs tables exist", tables == ["logs", "users"])

        # 3. Public routes
        print("\n3. Public routes:")
        for path in ["/api/health", "/", "/login"]:
            r = client.get(path)
            check(f"GET {path} -> {r.status_code}", r.status_code == 200)

        # 4. Log routes refuse anonymous requests
        print("\n4. Log routes without a token:")
        r = client.get("/api/logs")
        check(f"GET /api/logs -> {r.status_code}", r.status_code == 401)

        # 5. Register + login
        print("\n5. Register and login:")
        def sign_up(username):
            r = client.post("/api/auth/register", json={"username": username, "password": "check-password"})
            check(f"POST /api/auth/register {username} -> {r.status_code}", r.status_code == 201)
            r = client.post("/api/auth/login", data={"username": username, "password": "check-password"})
            check(f"POST /api/auth/login {username} -> {r.status_code}", r.status_code == 200)
            return {"Authorization": f"Bearer {r.json()['access_token']}"}
        alice = sign_up("check_alice")
        bob = sign_up("check_bob")
        r = client.post("/api/auth/login", data={"username": "check_alice", "password": "wrong-password"})
        check(f"wrong password -> {r.status_code}", r.status_code == 401)
        r = client.get("/api/auth/me", headers=alice)
        check(f"GET /api/auth/me -> {r.status_code}", r.status_code == 200 and r.json()["username"] == "check_alice", r.json().get("username", ""))

        # 6. CRUD on own logs
        print("\n6. Own logs:")
        payload = {"project": "_healthcheck", "title": "backend connectivity test", "severity": "low",
                   "status": "open", "error": "test error from check script", "solution": "",
                   "tags": ["healthcheck"], "date": "2026-01-01"}
        r = client.post("/api/logs", json=payload, headers=alice)
        check(f"POST /api/logs -> {r.status_code}", r.status_code == 201)
        log_id = r.json()["id"]
        r = client.put(f"/api/logs/{log_id}", json={**payload, "solution": "fixed"}, headers=alice)
        check(f"PUT /api/logs/{log_id} -> {r.status_code}", r.status_code == 200)
        r = client.patch(f"/api/logs/{log_id}/toggle", headers=alice)
        check(f"PATCH toggle -> {r.status_code} {r.json().get('status')}", r.status_code == 200)
        r = client.get("/api/logs", headers=alice)
        check(f"GET /api/logs -> {r.status_code} (count={len(r.json())})", r.status_code == 200 and len(r.json()) == 1)

        # 7. Another user cannot see or touch it
        print("\n7. Isolation between users:")
        r = client.get("/api/logs", headers=bob)
        check(f"other user's list is empty (count={len(r.json())})", r.json() == [])
        r = client.delete(f"/api/logs/{log_id}", headers=bob)
        check(f"other user DELETE -> {r.status_code}", r.status_code == 404)
        r = client.delete(f"/api/logs/{log_id}", headers=alice)
        check(f"owner DELETE -> {r.status_code}", r.status_code == 200)

    print("\n   Backend + Database + Auth: " + ("CONNECTED [OK]" if not failures else f"{len(failures)} check(s) FAILED [ERR]"))
except Exception as e:
    failures.append(str(e))
    print(f"   Check FAILED: {e}")
    traceback.print_exc()
    print("\n   Backend + Database + Auth: FAILED [ERR]")
finally:
    shutil.rmtree(TMP_DIR, ignore_errors=True)

print("\n=== Done ===")
sys.exit(1 if failures else 0)
