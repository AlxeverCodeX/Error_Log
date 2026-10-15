import subprocess, time, sys, os, urllib.request, urllib.error, urllib.parse, json, shutil, tempfile, uuid
import pathlib

BASE_DIR = pathlib.Path(__file__).parent.resolve()
URL = "http://127.0.0.1:8001"

# Throwaway database and secret so the real app.db is never touched
tmp_dir = tempfile.mkdtemp(prefix="error_log_live_")
env = {**os.environ,
       "DATABASE_PATH": os.path.join(tmp_dir, "live.db"),
       "JWT_SECRET": "live-check-secret-" + "x" * 32}

print("Starting live server on 127.0.0.1:8001...")
print(f"Working dir: {BASE_DIR}")
print(f"Temporary DB: {env['DATABASE_PATH']}")

proc = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "server:app", "--host", "127.0.0.1", "--port", "8001"],
    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=str(BASE_DIR), env=env
)

def request(method, path, body=None, form=None, token=None):
    headers, data = {}, None
    if body is not None:
        data, headers["Content-Type"] = json.dumps(body).encode(), "application/json"
    if form is not None:
        data, headers["Content-Type"] = urllib.parse.urlencode(form).encode(), "application/x-www-form-urlencoded"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(URL + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, r.read(), r.headers.get_content_type()
    except urllib.error.HTTPError as e:
        return e.code, e.read(), e.headers.get_content_type()

# wait for startup
ok = False
for i in range(12):
    time.sleep(0.7)
    try:
        status, body, _ = request("GET", "/api/health")
        print(f"[try {i+1}] GET /api/health -> {status} {body.decode()}")
        ok = True
        break
    except Exception as e:
        print(f"[try {i+1}] waiting... ({e})")
        if proc.poll() is not None:
            print("Server exited early!")
            break

failures = []
def check(label, passed):
    print(f"  [{'OK' if passed else 'FAIL'}] {label}")
    if not passed:
        failures.append(label)

if ok:
    try:
        for path in ["/", "/login"]:
            status, body, ctype = request("GET", path)
            check(f"GET {path} -> {status} ({len(body)} bytes, ct={ctype})", status == 200 and ctype == "text/html")

        status, _, _ = request("GET", "/api/logs")
        check(f"GET /api/logs without token -> {status}", status == 401)

        username = "live_" + uuid.uuid4().hex[:6]
        status, _, _ = request("POST", "/api/auth/register", body={"username": username, "password": "live-check-pw"})
        check(f"POST /api/auth/register -> {status}", status == 201)
        status, body, _ = request("POST", "/api/auth/login", form={"username": username, "password": "live-check-pw"})
        check(f"POST /api/auth/login -> {status}", status == 200)
        token = json.loads(body)["access_token"]

        status, body, _ = request("GET", "/api/auth/me", token=token)
        check(f"GET /api/auth/me -> {status} {json.loads(body).get('username')}", status == 200)

        status, body, _ = request("POST", "/api/logs", token=token,
                                  body={"project": "_live", "title": "live check", "error": "e"})
        check(f"POST /api/logs -> {status}", status == 201)
        status, body, _ = request("GET", "/api/logs", token=token)
        logs = json.loads(body)
        check(f"GET /api/logs with token -> {status} ({len(logs)} entries)", status == 200 and len(logs) == 1)
    except Exception as e:
        check(f"request failed: {e}", False)
    print("\nLIVE SERVER + DB + AUTH: " + ("REACHABLE" if not failures else f"{len(failures)} check(s) FAILED"))
else:
    failures.append("startup")
    print("\nLIVE SERVER: failed to start")

# shutdown
proc.terminate()
try:
    proc.wait(timeout=5)
except subprocess.TimeoutExpired:
    proc.kill()
    proc.wait()
print("Server stopped.")
out = proc.stdout.read() if proc.stdout else ""
if out:
    print("--- server log (last 800 chars) ---")
    print(out[-800:])
shutil.rmtree(tmp_dir, ignore_errors=True)
sys.exit(1 if failures else 0)
