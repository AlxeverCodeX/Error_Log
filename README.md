# Error Log Book

> A beautiful, fast, and simple error tracker for developers. Log bugs, document fixes, and never solve the same error twice.

![Python](https://img.shields.io/badge/python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688?style=flat-square&logo=fastapi&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-3-003B57?style=flat-square&logo=sqlite&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-green?style=flat-square)

Single-folder app — **SQLite + FastAPI + vanilla HTML/CSS/JS** in one directory. Copy, install, run.

Anyone who opens the site can create an account. Each account gets its own private error log: you only ever see, edit, or delete your own entries.

---

## Features

- **Personal accounts** — sign up with a username and password, then sign in; your entries are private to you
- **Create / Edit / Delete** error entries with project, severity, status, tags & date
- **Toggle Solved** with one click — tracks `open` / `in-progress` / `solved`
- **Search & Filter** — by text, project, status, severity + sort by newest/oldest/project
- **Stats header** — total / solved / open / project count at a glance
- **Glass + Terminal themes** — modern glassmorphism with a cyber `terminal` variant
- **Export / Import JSON** — backup or migrate your logs in one file
- **Zero setup database** — `app.db` and its tables are created automatically on first run
- **Fully offline** — no external DB or cloud service required
- **Standalone** — works regardless of `cwd` (`BASE_DIR` relative paths + `DATABASE_PATH` override)

---

## Tech Stack

| Layer    | Technology |
|----------|------------|
| Backend  | Python 3.11+, FastAPI, Pydantic, Uvicorn |
| Auth     | bcrypt password hashing, PyJWT bearer tokens (HS256), FastAPI `OAuth2PasswordBearer` |
| Database | SQLite 3 (single file `app.db`, `sqlite3` stdlib, no ORM) |
| Frontend | `index.html` + `login.html` — HTML + CSS + vanilla JS, no build step, no framework |
| Tests    | pytest + FastAPI `TestClient` |

---

## Project Structure

```
Error_Log/
├── server.py              # FastAPI app: auth, SQLite logic, serves the two pages
├── index.html             # Error log page (glass + terminal theme)
├── login.html             # Sign in / create account page
├── app.db                 # SQLite DB — auto-created on first run, never committed
├── requirements.txt       # runtime dependencies
├── requirements-dev.txt   # runtime + pytest + httpx
├── pyproject.toml         # package metadata, dev extra, pytest config
├── tests/                 # pytest suite (auth helpers, auth routes, per-user logs)
├── check_backend.py       # Offline smoke check (TestClient, temporary DB)
├── live_server_check.py   # Live check — spawns uvicorn on :8001 with a temporary DB
└── README.md              # this file
```

---

## Quick Start

### 1. Install dependencies

```bash
# option A — requirements.txt
pip install -r requirements.txt

# option B — editable install via pyproject.toml
pip install -e .
```

> Requires Python `>=3.11`.

### 2. Set a secret for signing login tokens

Use any random string of **at least 32 characters**. Keep it the same across restarts, or everyone gets signed out.

```bash
# macOS / Linux
export JWT_SECRET="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
```

```powershell
# Windows PowerShell
$env:JWT_SECRET = python -c "import secrets; print(secrets.token_urlsafe(48))"
```

If `JWT_SECRET` is not set, the server still starts, but uses a random key and prints a warning. Tokens then stop working whenever the server restarts — fine for a quick try, not for real use.

### 3. Start the server

```bash
# recommended
uvicorn server:app --reload

# alternative
python -m uvicorn server:app --host 127.0.0.1 --port 8000
```

Open **http://127.0.0.1:8000**. You'll be sent to the sign-in page; click **New here? Create an account**.

If you run from the parent `MINI_CLAUDE_CODE` repo root instead:

```bash
uvicorn Error_Log.server:app --reload
```

---

## Usage

### Accounts

1. Open the site and click **New here? Create an account**.
2. Pick a username (3–32 characters: letters, numbers, `_` `.` `-`) and a password (at least 8 characters). Usernames are case-insensitive: `Alice` and `alice` are the same account.
3. **Create account & sign in** takes you straight to your (empty) error log.
4. Your username is shown in the header. **Log out** signs you out on this browser.

Sessions last 60 minutes by default (`JWT_EXPIRE_MINUTES`). When a session expires you're sent back to the sign-in page.

### Error log

1. Fill **Project Name**, **Title**, **Severity**, **Status**, **Error Details** on the left form. Add optional **Solution** and **Tags**.
2. Click **Save Entry** — it appears instantly in the log list on the right.
3. Use the **toolbar** to search (`title / project / error / solution`) and filter by project, status, severity, or sort order.
4. On each card: **Edit**, **Copy** (to clipboard), **Delete**, and **Solve/Open** toggle.
5. Header actions: **Export** (download JSON), **Import** (load JSON), **Clear all** (your entries only).

### Database

Both tables are created automatically on startup.

**`users`**

| Column          | Type | Notes |
|-----------------|------|-------|
| `id`            | TEXT | PK, 10-char hex (`uuid4`) |
| `username`      | TEXT | Unique, case-insensitive (`COLLATE NOCASE`) |
| `password_hash` | TEXT | bcrypt hash — the password itself is never stored |
| `created_at`    | TEXT | ISO timestamp (UTC) |

**`logs`**

| Column     | Type | Notes |
|------------|------|-------|
| `id`       | TEXT | PK, 10-char hex (`uuid4`) |
| `project`  | TEXT | e.g. `payment-service` |
| `title`    | TEXT | Short issue title |
| `severity` | TEXT | `low` / `medium` / `high` / `critical` |
| `status`   | TEXT | `open` / `in-progress` / `solved` |
| `error`    | TEXT | Stack trace / details |
| `solution` | TEXT | Fix (optional) |
| `tags`     | TEXT | JSON array string |
| `date`     | TEXT | ISO date `YYYY-MM-DD` |
| `user_id`  | TEXT | Owner — references `users.id`; deleting a user deletes their logs |

An index on `(user_id, date)` keeps each person's list fast. New accounts start with an empty log.

**Older databases:** if `server.py` finds an `app.db` from before accounts existed, it adds the `user_id` column on startup. Entries created before that have no owner and are not shown to anyone.

---

## API Reference

Base URL: `http://127.0.0.1:8000`

All responses are JSON. Interactive docs at `/docs` (Swagger — use **Authorize** to sign in) and `/redoc`.

### Authentication

| Method | Path | Body | Response |
|--------|------|------|----------|
| `POST` | `/api/auth/register` | JSON `{"username", "password"}` | `201` `{"id", "username"}` · `409` username taken · `422` invalid input |
| `POST` | `/api/auth/login` | **Form** fields `username`, `password` | `200` `{"access_token", "token_type": "bearer"}` · `401` wrong username or password |
| `GET`  | `/api/auth/me` | — | `200` `{"id", "username"}` |

Send the token on every log request:

```
Authorization: Bearer <access_token>
```

Missing, invalid, or expired tokens get `401` with `WWW-Authenticate: Bearer`.

### Logs — sign-in required, your entries only

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/logs` | List your logs (ordered by `date DESC`) |
| `POST` | `/api/logs` | Create a log → `201` + created object |
| `PUT` | `/api/logs/{id}` | Replace one of your logs |
| `PATCH` | `/api/logs/{id}/toggle` | Toggle `solved` ↔ `open` |
| `DELETE` | `/api/logs/{id}` | Delete one of your logs |
| `DELETE` | `/api/logs` | Delete **all of your** logs |

Another user's log id behaves exactly like one that doesn't exist: `404 Not found`.

### Public

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/health` | Health check → `{"status":"ok"}` |
| `GET` | `/` | Error log page (`index.html`) |
| `GET` | `/login` | Sign-in page (`login.html`) |

### Example — sign up, sign in, create a log

```bash
curl -X POST http://127.0.0.1:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username": "alice", "password": "correct-horse"}'

TOKEN=$(curl -s -X POST http://127.0.0.1:8000/api/auth/login \
  -d "username=alice&password=correct-horse" \
  | python -c "import sys, json; print(json.load(sys.stdin)['access_token'])")

curl -X POST http://127.0.0.1:8000/api/logs \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "project": "api-v2",
    "title": "Prisma P1001: Can'\''t reach database on Docker",
    "severity": "critical",
    "status": "open",
    "error": "Error: P1001: Can'\''t reach database server at db:5432",
    "solution": "",
    "tags": ["prisma","docker","postgres"],
    "date": "2026-10-01"
  }'
```

### Example — list / toggle / delete

```bash
curl http://127.0.0.1:8000/api/logs -H "Authorization: Bearer $TOKEN"
curl -X PATCH http://127.0.0.1:8000/api/logs/<id>/toggle -H "Authorization: Bearer $TOKEN"
curl -X DELETE http://127.0.0.1:8000/api/logs/<id> -H "Authorization: Bearer $TOKEN"
```

`project`, `title`, and `error` are required when creating a log (non-empty after trim).

---

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `JWT_SECRET` | random per process (with a warning) | Key that signs login tokens. **Set it** — at least 32 characters, kept secret, same across restarts |
| `JWT_EXPIRE_MINUTES` | `60` | How long a sign-in lasts |
| `DATABASE_PATH` | `<BASE_DIR>/app.db` (`app.db` next to `server.py`) | Override SQLite file location |

```bash
# custom DB path + secret
JWT_SECRET=... DATABASE_PATH=/data/my-logs.db uvicorn server:app --host 0.0.0.0 --port 8000
```

`server.py` resolves `app.db`, `index.html` and `login.html` via `BASE_DIR = os.path.dirname(__file__)` — no matter where you run it from.

---

## Tests and Checks

```bash
pip install -r requirements-dev.txt   # or: pip install -e .[dev]

# full test suite — every test uses its own temporary database
python -m pytest
```

The suite covers password hashing, token validation (expired, tampered, unsigned, missing claims), registration and login rules, and that users can never see or change each other's logs.

Quick smoke checks, also on temporary databases:

```bash
# offline — FastAPI TestClient: tables, public routes, sign-up, sign-in, CRUD, isolation
python check_backend.py

# live — spawns uvicorn on 127.0.0.1:8001 and runs the same flow over HTTP
python live_server_check.py
```

Both exit with code `1` if any check fails. `check_backend.py` forces UTF-8 on Windows so output doesn't crash on `cp1252` consoles.

---

## Deployment

Always set `JWT_SECRET` in production. Every worker and every restart must use the same value.

### Any VPS (systemd / pm2 / Docker)

```bash
pip install -r requirements.txt
export JWT_SECRET=...   # at least 32 random characters
uvicorn server:app --host 0.0.0.0 --port 8000
```

SQLite allows one writer at a time, so a single worker is the safe default.

### Docker (example)

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY server.py index.html login.html ./
# app.db is auto-created on first run; mount a volume to persist it
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
```

```bash
docker build -t error-log-book .
docker run -p 8000:8000 -v ./data:/app/data \
  -e DATABASE_PATH=/app/data/app.db \
  -e JWT_SECRET=... \
  error-log-book
```

### Render / Railway / Fly.io

- Build command: `pip install -r requirements.txt`
- Start command: `uvicorn server:app --host 0.0.0.0 --port $PORT`
- Environment: set `JWT_SECRET`; set `DATABASE_PATH` to a persistent disk path so accounts and logs survive redeploys.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Everyone gets signed out after a restart | `JWT_SECRET` isn't set, so a new random key is used each start. Set it to a fixed value |
| Server won't start: `JWT_SECRET must be at least 32 characters long` | Use a longer secret, e.g. `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `409 Username already taken` | Usernames are case-insensitive — `Alice` and `alice` are the same name |
| Old entries disappeared after upgrading | They were created before accounts existed and have no owner. They're still in `app.db` but not shown to anyone |
| `app.db` not found after `git clone` | Normal — it's ignored by git and auto-created on first run |
| `address already in use :8000` | `uvicorn server:app --port 8001` or `lsof -i :8000` / `netstat -ano \| findstr 8000` |
| `pytest` not recognized on Windows | Run `python -m pytest` instead — pip installs `pytest.exe` to a folder that may not be on `PATH` |
| Windows `charmap` / `UnicodeEncodeError` | Fixed — `check_backend.py` reconfigures stdout to UTF-8 |
| Page keeps sending you to the sign-in page | Make sure `uvicorn server:app` is running and you're opening `http://127.0.0.1:8000` (not `file://`) |

---

## License

MIT — use it for personal or commercial projects, no attribution required.

---

Made for developers who are tired of solving the same bug twice.
