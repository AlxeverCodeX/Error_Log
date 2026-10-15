# Error Log Book

> A fast, simple error tracker for developers. Log bugs, document fixes, and never solve the same error twice.

![Python](https://img.shields.io/badge/python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.141-009688?style=flat-square&logo=fastapi&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-3-003B57?style=flat-square&logo=sqlite&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-green?style=flat-square)

Anyone who opens the site can create an account. Each account gets its own private error log: you only ever see, edit, or delete your own entries.

One small app — **FastAPI + SQLite + vanilla HTML/CSS/JS** — with no build step and no external services. Run it locally with Python, or deploy the Docker image anywhere that gives you a persistent disk.

---

## Contents

- [Features](#features)
- [Tech stack](#tech-stack)
- [Project structure](#project-structure)
- [Run locally](#run-locally)
- [Using the app](#using-the-app)
- [Configuration](#configuration)
- [API reference](#api-reference)
- [Database](#database)
- [Tests and CI](#tests-and-ci)
- [Push to GitHub](#push-to-github)
- [Deployment](#deployment)
- [Security](#security)
- [Troubleshooting](#troubleshooting)
- [License](#license)

---

## Features

- **Personal accounts** — sign up with a username and password; your entries are private to you
- **Create / Edit / Delete** error entries with project, severity, status, tags & date
- **Toggle Solved** with one click — tracks `open` / `in-progress` / `solved`
- **Search & Filter** — by text, project, status, severity + sort by newest/oldest/project
- **Stats header** — total / solved / open / project count at a glance
- **Glass + Terminal themes** — modern glassmorphism with a cyber `terminal` variant
- **Export / Import JSON** — back up or move your logs in one file
- **Zero-setup database** — `app.db` and its tables are created automatically on first start
- **Brute-force protection** — repeated failed sign-ins are temporarily blocked
- **Production-ready container** — non-root, health-checked, refuses to start without a secret

---

## Tech stack

| Layer    | Technology |
|----------|------------|
| Backend  | Python 3.11+, FastAPI, Pydantic, Uvicorn |
| Auth     | bcrypt password hashing, PyJWT bearer tokens (HS256), FastAPI `OAuth2PasswordBearer` |
| Database | SQLite 3 (single file, `sqlite3` stdlib, no ORM) |
| Frontend | `index.html` + `login.html` — HTML + CSS + vanilla JS, no framework |
| Tests    | pytest + FastAPI `TestClient`, GitHub Actions |
| Deploy   | Docker (`python:3.11-slim`) |

---

## Project structure

```
.
├── server.py               # FastAPI app: auth, rate limiting, SQLite, serves both pages
├── index.html              # Error log page
├── login.html              # Sign in / create account page
├── requirements.txt        # pinned runtime dependencies (used by Docker and CI)
├── requirements-dev.txt    # runtime + pytest + httpx
├── pyproject.toml          # project metadata and pytest config
├── .env.example            # template for your local .env
├── Dockerfile              # production image
├── docker-entrypoint.sh    # fixes data-volume ownership, then drops to a non-root user
├── .dockerignore
├── tests/                  # pytest suite
├── check_backend.py        # offline smoke check (temporary database)
├── live_server_check.py    # starts a real server on :8001 and checks it over HTTP
├── .github/
│   ├── workflows/ci.yml    # runs tests and builds/smoke-tests the image on every push
│   └── dependabot.yml      # weekly dependency update PRs
└── LICENSE
```

`app.db` (your data) and `.env` (your secret) are created locally and are **never committed** — see `.gitignore`.

---

## Run locally

Requires **Python 3.11+**.

```bash
git clone https://github.com/<your-username>/error-log-book.git
cd error-log-book

python -m venv .venv
# Windows:  .venv\Scripts\activate
# macOS / Linux:  source .venv/bin/activate

pip install -r requirements.txt
```

Create your `.env` from the template and fill in a secret of **at least 32 characters**:

```bash
cp .env.example .env          # Windows PowerShell: Copy-Item .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(48))"   # paste the output after JWT_SECRET=
```

Start the server:

```bash
uvicorn server:app --reload    # auto-reloads when you edit code
# or
python server.py               # uses HOST / PORT, default 127.0.0.1:8000
```

Open **http://127.0.0.1:8000** and click **New here? Create an account**.

> Without a `JWT_SECRET` the server still starts locally, but uses a random key and prints a warning — everyone is signed out on each restart.

---

## Using the app

### Accounts

- **Username:** 3–32 characters — letters, numbers, `_` `.` `-`. Case-insensitive: `Alice` and `alice` are the same account.
- **Password:** at least 8 characters (at most 72 bytes, a bcrypt limit).
- **Create account & sign in** registers and opens your empty log in one step.
- Your username is shown in the header; **Log out** signs you out on this browser.
- Sign-ins last 60 minutes by default (`JWT_EXPIRE_MINUTES`); then you're sent back to the sign-in page.
- After 10 wrong passwords for the same username from the same address within 15 minutes, sign-in is blocked for that username until the window passes. One address is capped at 50 failures across all usernames.

### Error log

1. Fill **Project Name**, **Title**, **Severity**, **Status**, **Error Details** on the left. Add an optional **Solution** and **Tags**.
2. **Save Entry** — it appears instantly in the list on the right.
3. Use the **toolbar** to search and filter by project, status, severity, or sort order.
4. On each card: **Edit**, **Copy**, **Delete**, and **Solve / Open**.
5. Header: **Export** (download JSON), **Import** (load JSON), **Clear all** (your entries only).

---

## Configuration

Set these in `.env` (local) or as environment variables (hosting platforms). Real environment variables take priority over `.env`.

| Variable | Default | Description |
|----------|---------|-------------|
| `JWT_SECRET` | random per process, with a warning | **Required in production.** Signs login tokens. At least 32 characters; keep it secret and the same across restarts and deploys |
| `ENVIRONMENT` | unset (`production` in Docker) | When `production`, the server refuses to start without `JWT_SECRET` |
| `DATABASE_PATH` | `app.db` next to `server.py` (`/data/app.db` in Docker) | SQLite file location — must be on persistent storage in production |
| `JWT_EXPIRE_MINUTES` | `60` | How long a sign-in lasts |
| `LOGIN_MAX_FAILURES` | `10` | Failed sign-ins allowed per username + address within the window |
| `LOGIN_MAX_FAILURES_PER_IP` | `50` | Failed sign-ins allowed per address across all usernames |
| `LOGIN_WINDOW_SECONDS` | `900` | Length of the rate-limit window (15 minutes) |
| `PORT` | `8000` | Port to listen on (Docker and `python server.py`); most platforms set this for you |
| `HOST` | `127.0.0.1` | Bind address for `python server.py` (Docker always binds `0.0.0.0`) |
| `FORWARDED_ALLOW_IPS` | `127.0.0.1` (`*` in Docker) | Proxies whose `X-Forwarded-For` uvicorn trusts — needed so the rate limiter sees the real client address behind a platform's load balancer |

---

## API reference

Interactive docs: **`/docs`** (Swagger — click **Authorize** to sign in) and **`/redoc`**.

### Authentication

| Method | Path | Body | Response |
|--------|------|------|----------|
| `POST` | `/api/auth/register` | JSON `{"username", "password"}` | `201` `{"id", "username"}` · `409` username taken · `422` invalid input |
| `POST` | `/api/auth/login` | **Form** fields `username`, `password` | `200` `{"access_token", "token_type": "bearer"}` · `401` wrong username or password · `429` too many failures (`Retry-After` header in seconds) |
| `GET`  | `/api/auth/me` | — | `200` `{"id", "username"}` |

Send the token on every log request:

```
Authorization: Bearer <access_token>
```

Missing, invalid, or expired tokens get `401` with `WWW-Authenticate: Bearer`.

### Logs — sign-in required, your entries only

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/logs` | List your logs, newest date first |
| `POST` | `/api/logs` | Create a log → `201` |
| `PUT` | `/api/logs/{id}` | Replace one of your logs |
| `PATCH` | `/api/logs/{id}/toggle` | `solved` → `open`; anything else → `solved` |
| `DELETE` | `/api/logs/{id}` | Delete one of your logs |
| `DELETE` | `/api/logs` | Delete **all of your** logs |

`project`, `title`, and `error` must be non-empty on create and update (`400` otherwise). Another user's log id behaves exactly like one that doesn't exist: `404`.

### Public

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/health` | `{"status": "ok"}` — used by the Docker health check |
| `GET` | `/` | Error log page |
| `GET` | `/login` | Sign-in page |

### Example

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
  -d '{"project": "api-v2", "title": "Prisma P1001 on Docker", "severity": "critical",
       "error": "P1001: Can'\''t reach database server at db:5432", "tags": ["prisma", "docker"]}'

curl http://127.0.0.1:8000/api/logs -H "Authorization: Bearer $TOKEN"
```

---

## Database

Tables are created on startup; there's nothing to migrate by hand.

**`users`** — `id` (PK), `username` (unique, case-insensitive), `password_hash` (bcrypt — the password itself is never stored), `created_at`.

**`logs`** — `id` (PK), `project`, `title`, `severity` (`low`/`medium`/`high`/`critical`), `status` (`open`/`in-progress`/`solved`), `error`, `solution`, `tags` (JSON array), `date` (`YYYY-MM-DD`), `user_id` (owner → `users.id`; deleting a user deletes their logs). Indexed on `(user_id, date)`.

If the server finds a database from before accounts existed, it adds `user_id` on startup. Those older entries have no owner and aren't shown to anyone.

---

## Tests and CI

```bash
pip install -r requirements-dev.txt
python -m pytest            # full suite; every test uses its own temporary database
python check_backend.py     # offline smoke check
python live_server_check.py # starts a real server on :8001 and checks it over HTTP
```

The suite covers password hashing, token validation (expired, tampered, unsigned, missing claims), registration and login rules, rate limiting, and that users can never see or change each other's logs.

**GitHub Actions** (`.github/workflows/ci.yml`) runs on every push to `main` and every pull request:

1. installs the pinned dependencies, runs `pytest` and `check_backend.py`;
2. builds the Docker image, checks it refuses to start without `JWT_SECRET`, then starts it and waits for a healthy health check.

**Dependabot** opens weekly pull requests to bump the pinned Python packages, the base image, and the Actions versions; CI tests each one before you merge.

---

## Push to GitHub

1. Create an **empty** repository on GitHub (no README, `.gitignore`, or license — this project already has them).
2. Push:

   ```bash
   git remote add origin https://github.com/<your-username>/<repo-name>.git
   git push -u origin main
   ```

3. Open the **Actions** tab to watch the first CI run.

Before pushing, `git status` should show no `app.db`, `app.db.bak`, or `.env` — they are ignored on purpose. Never commit your real `JWT_SECRET`.

---

## Deployment

### Checklist

- [ ] **`JWT_SECRET`** set as a secret/environment variable on the platform (at least 32 random characters). The container won't start without it.
- [ ] **Persistent disk/volume mounted at `/data`.** Without one, every account and log is lost on each redeploy or restart.
- [ ] **One instance.** SQLite has a single writer and the sign-in limiter lives in memory — don't scale horizontally.
- [ ] **Health check path** `/api/health` (if the platform asks).
- [ ] **HTTPS** — all the platforms below provide it automatically; never serve sign-ins over plain HTTP.

The image listens on `$PORT` (default `8000`), stores data in `/data/app.db`, and runs the server as an unprivileged user. Platforms that set `PORT` themselves work without changes.

### Docker (any server or VPS)

```bash
docker build -t error-log-book .
docker volume create error-log-data

docker run -d --name error-log-book --restart unless-stopped \
  -p 8000:8000 \
  -v error-log-data:/data \
  -e JWT_SECRET="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')" \
  error-log-book
```

Store that secret somewhere safe; reusing it on the next `docker run` keeps everyone signed in. Put a reverse proxy with HTTPS (Caddy, nginx, Traefik) in front of port 8000.

### Render

1. **New → Web Service**, connect the GitHub repo. Render detects the `Dockerfile`.
2. **Environment:** add `JWT_SECRET`.
3. **Disks:** add a disk with mount path `/data` (requires a paid instance type — on the free type your data is wiped on every deploy).
4. **Health check path:** `/api/health`.

### Railway

1. **New Project → Deploy from GitHub repo.** Railway detects the `Dockerfile`.
2. **Variables:** add `JWT_SECRET`.
3. Add a **Volume** to the service, mounted at `/data`.
4. **Settings → Networking → Generate Domain.**

### Fly.io

```bash
fly launch --no-deploy                 # detects the Dockerfile and writes fly.toml
fly volumes create error_log_data --size 1
fly secrets set JWT_SECRET="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
```

In `fly.toml`, make sure `internal_port = 8000` and add:

```toml
[mounts]
  source = "error_log_data"
  destination = "/data"
```

Then `fly deploy`, and keep a single machine: `fly scale count 1`.

### Updating

Push to `main`. CI runs; Render and Railway redeploy automatically from GitHub (Fly: run `fly deploy`). The database on the volume is kept, and tables are upgraded on startup.

### Backups

Your data is one file. To take a consistent copy while the app is running:

```bash
docker exec error-log-book python -c "import sqlite3; sqlite3.connect('/data/app.db').backup(sqlite3.connect('/data/backup.db'))"
docker cp error-log-book:/data/backup.db ./backup-$(date +%F).db
```

On a platform, run the same `python -c ...` command from its shell/console.

---

## Security

What's in place:

- Passwords are hashed with bcrypt (per-password salt); plain passwords are never stored or logged.
- Tokens are HS256 JWTs with an expiry; the algorithm is pinned, so unsigned or re-signed tokens are rejected.
- Every log query is scoped to the signed-in user; other users' entries return `404`.
- Wrong password and unknown username give the same response and take the same time.
- Repeated failed sign-ins are rate-limited per username + address and per address.
- The container runs as a non-root user and refuses to start without `JWT_SECRET`.
- The database and secrets are git-ignored and excluded from the Docker image.

Known limitations:

- Tokens are kept in the browser's `localStorage`, so a cross-site-scripting bug could expose them. All user content is HTML-escaped before rendering.
- There's no password reset or account deletion in the UI yet.
- Registration isn't rate-limited, so automated sign-ups are possible.
- The sign-in limiter is per process and resets on restart.

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Container exits with `JWT_SECRET must be set when ENVIRONMENT=production` | Set `JWT_SECRET` on the platform or with `docker run -e JWT_SECRET=...` |
| `JWT_SECRET must be at least 32 characters long` | Generate one: `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| Everyone gets signed out after a restart | `JWT_SECRET` isn't fixed. Locally put it in `.env`; on a platform set it as a variable |
| Accounts and logs disappear after a deploy | No persistent volume at `/data` — see the [deployment checklist](#checklist) |
| `429 Too many failed sign-in attempts` | Wait for the time shown, or restart the server to clear the limiter |
| Everyone gets `429` at once behind a proxy | The proxy isn't trusted, so all requests look like one address. Set `FORWARDED_ALLOW_IPS` to the proxy's address (Docker already uses `*`) |
| `409 Username already taken` | Usernames are case-insensitive — `Alice` and `alice` are the same |
| Old entries vanished after upgrading | They predate accounts and have no owner; they're still in the database file |
| `address already in use :8000` | `uvicorn server:app --port 8001`, or find the process: `netstat -ano \| findstr 8000` (Windows) / `lsof -i :8000` |
| `pytest` not recognized on Windows | Run `python -m pytest` |
| Page keeps sending you to the sign-in page | Make sure the server is running and you're on `http://127.0.0.1:8000`, not a `file://` URL |

---

## License

[MIT](LICENSE) © 2026 Emmanuel Albert

---

Made for developers who are tired of solving the same bug twice.
