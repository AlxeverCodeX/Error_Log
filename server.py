import json
import logging
import os
import secrets
import sqlite3
import uuid
from contextlib import asynccontextmanager, contextmanager
from datetime import date as date_type, datetime, timedelta, timezone
from typing import Optional, List

import bcrypt
import jwt
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger("error_log")

# Resolve paths relative to this file so it works regardless of cwd
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.getenv("DATABASE_PATH", os.path.join(BASE_DIR, "app.db"))
INDEX_PATH = os.path.join(BASE_DIR, "index.html")
LOGIN_PATH = os.path.join(BASE_DIR, "login.html")

# ---------- Auth config ----------
JWT_ALGORITHM = "HS256"
JWT_MIN_SECRET_LENGTH = 32
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "60"))
PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_BYTES = 72  # bcrypt rejects anything longer

def load_jwt_secret() -> str:
    secret = os.getenv("JWT_SECRET", "")
    if not secret:
        logger.warning("JWT_SECRET is not set; using a random key. Tokens will stop working when the server restarts.")
        return secrets.token_urlsafe(48)
    if len(secret) < JWT_MIN_SECRET_LENGTH:
        raise RuntimeError(f"JWT_SECRET must be at least {JWT_MIN_SECRET_LENGTH} characters long")
    return secret

JWT_SECRET = load_jwt_secret()

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(title="Error Log Book API", lifespan=lifespan)

# CORS - auth uses bearer tokens, not cookies, so credentials stay off
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- DB ----------
@contextmanager
def get_conn():
    """Commit on success, roll back on error, and always close the connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        with conn:
            yield conn
    finally:
        conn.close()

def gen_id(): return uuid.uuid4().hex[:10]

def row_to_dict(row):
    d = dict(row)
    try:
        d["tags"] = json.loads(d["tags"]) if d["tags"] else []
    except:
        d["tags"] = []
    return d

def init_db():
    with get_conn() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL UNIQUE COLLATE NOCASE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS logs (
            id TEXT PRIMARY KEY,
            project TEXT NOT NULL,
            title TEXT NOT NULL,
            severity TEXT NOT NULL,
            status TEXT NOT NULL,
            error TEXT NOT NULL,
            solution TEXT,
            tags TEXT,
            date TEXT NOT NULL,
            user_id TEXT REFERENCES users(id) ON DELETE CASCADE
        )
        """)
        # SQLite cannot add a NOT NULL column to an existing table, so user_id
        # stays nullable and older rows without an owner are never returned.
        log_cols = [r["name"] for r in conn.execute("PRAGMA table_info(logs)")]
        if "user_id" not in log_cols:
            conn.execute("ALTER TABLE logs ADD COLUMN user_id TEXT REFERENCES users(id) ON DELETE CASCADE")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_logs_user_date ON logs(user_id, date DESC)")
        conn.commit()

# ---------- Models ----------
class LogIn(BaseModel):
    project: str
    title: str
    severity: str = "medium"
    status: str = "open"
    error: str
    solution: Optional[str] = ""
    tags: Optional[List[str]] = []
    date: Optional[str] = None

class LogOut(LogIn):
    id: str

class UserOut(BaseModel):
    id: str
    username: str

class RegisterIn(BaseModel):
    username: str = Field(min_length=3, max_length=32, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=PASSWORD_MIN_LENGTH)

    @field_validator("username", mode="before")
    @classmethod
    def strip_username(cls, v):
        return v.strip() if isinstance(v, str) else v

    @field_validator("password")
    @classmethod
    def password_fits_bcrypt(cls, v: str) -> str:
        if len(v.encode("utf-8")) > PASSWORD_MAX_BYTES:
            raise ValueError(f"password must be at most {PASSWORD_MAX_BYTES} bytes")
        return v

class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"

# ---------- Auth helpers ----------
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")

def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("ascii"))
    except ValueError:
        # Password over 72 bytes or a malformed stored hash
        return False

def create_access_token(user_id: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": user_id, "iat": now, "exp": now + timedelta(minutes=JWT_EXPIRE_MINUTES)}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def decode_access_token(token: str) -> Optional[str]:
    """Return the user id from a valid token, or None for any invalid token."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM], options={"require": ["exp", "iat", "sub"]})
    except jwt.InvalidTokenError:
        return None
    user_id = payload.get("sub")
    return user_id if isinstance(user_id, str) and user_id else None

# Checked when the username does not exist, so both failure paths cost one bcrypt check
DUMMY_PASSWORD_HASH = hash_password(secrets.token_urlsafe(16))

def authenticate_user(username: str, password: str) -> Optional[UserOut]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, username, password_hash FROM users WHERE username = ? COLLATE NOCASE",
            (username.strip(),),
        ).fetchone()
    if not row:
        verify_password(password, DUMMY_PASSWORD_HASH)
        return None
    if not verify_password(password, row["password_hash"]):
        return None
    return UserOut(id=row["id"], username=row["username"])

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

def get_current_user(token: str = Depends(oauth2_scheme)) -> UserOut:
    credentials_error = HTTPException(401, "Could not validate credentials", headers={"WWW-Authenticate": "Bearer"})
    user_id = decode_access_token(token)
    if not user_id:
        raise credentials_error
    with get_conn() as conn:
        row = conn.execute("SELECT id, username FROM users WHERE id=?", (user_id,)).fetchone()
    if not row:
        raise credentials_error
    return UserOut(id=row["id"], username=row["username"])

# ---------- Health ----------
@app.get("/api/health")
def health():
    return {"status": "ok"}

# ---------- Auth ----------
@app.post("/api/auth/register", response_model=UserOut, status_code=201)
def register(payload: RegisterIn):
    user_id = gen_id()
    password_hash = hash_password(payload.password)
    taken = HTTPException(409, "Username already taken")
    with get_conn() as conn:
        # Older databases created users.username without COLLATE NOCASE
        if conn.execute("SELECT 1 FROM users WHERE username = ? COLLATE NOCASE", (payload.username,)).fetchone():
            raise taken
        try:
            conn.execute(
                "INSERT INTO users (id, username, password_hash, created_at) VALUES (?,?,?,?)",
                (user_id, payload.username, password_hash, datetime.now(timezone.utc).isoformat()),
            )
        except sqlite3.IntegrityError:
            raise taken from None
    return UserOut(id=user_id, username=payload.username)

@app.post("/api/auth/login", response_model=TokenOut)
def login(form: OAuth2PasswordRequestForm = Depends()):
    user = authenticate_user(form.username, form.password)
    if not user:
        raise HTTPException(401, "Incorrect username or password", headers={"WWW-Authenticate": "Bearer"})
    return TokenOut(access_token=create_access_token(user.id))

@app.get("/api/auth/me", response_model=UserOut)
def me(user: UserOut = Depends(get_current_user)):
    return user

# ---------- Logs (each user sees only their own) ----------
# Every query matches on user_id as well as id, so another user's log id
# behaves exactly like one that does not exist (404, never 403).
@app.get("/api/logs", response_model=List[LogOut])
def list_logs(user: UserOut = Depends(get_current_user)):
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM logs WHERE user_id=? ORDER BY date DESC, id DESC", (user.id,)).fetchall()
        return [row_to_dict(r) for r in rows]

@app.post("/api/logs", response_model=LogOut, status_code=201)
def create_log(payload: LogIn, user: UserOut = Depends(get_current_user)):
    if not payload.project.strip() or not payload.title.strip() or not payload.error.strip():
        raise HTTPException(400, "project, title and error are required")
    log_id = gen_id()
    tags_json = json.dumps(payload.tags or [])
    date_val = payload.date or date_type.today().isoformat()
    with get_conn() as conn:
        conn.execute("INSERT INTO logs (id, project, title, severity, status, error, solution, tags, date, user_id) VALUES (?,?,?,?,?,?,?,?,?,?)",
                     (log_id, payload.project.strip(), payload.title.strip(), payload.severity, payload.status, payload.error.strip(), (payload.solution or "").strip(), tags_json, date_val, user.id))
        conn.commit()
        row = conn.execute("SELECT * FROM logs WHERE id=? AND user_id=?", (log_id, user.id)).fetchone()
        return row_to_dict(row)

@app.put("/api/logs/{log_id}", response_model=LogOut)
def update_log(log_id: str, payload: LogIn, user: UserOut = Depends(get_current_user)):
    with get_conn() as conn:
        cur = conn.execute("SELECT id FROM logs WHERE id=? AND user_id=?", (log_id, user.id))
        if not cur.fetchone():
            raise HTTPException(404, "Not found")
        tags_json = json.dumps(payload.tags or [])
        date_val = payload.date or date_type.today().isoformat()
        conn.execute("UPDATE logs SET project=?, title=?, severity=?, status=?, error=?, solution=?, tags=?, date=? WHERE id=? AND user_id=?",
                     (payload.project.strip(), payload.title.strip(), payload.severity, payload.status, payload.error.strip(), (payload.solution or "").strip(), tags_json, date_val, log_id, user.id))
        conn.commit()
        row = conn.execute("SELECT * FROM logs WHERE id=? AND user_id=?", (log_id, user.id)).fetchone()
        return row_to_dict(row)

@app.delete("/api/logs/{log_id}")
def delete_log(log_id: str, user: UserOut = Depends(get_current_user)):
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM logs WHERE id=? AND user_id=?", (log_id, user.id))
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(404, "Not found")
        return {"deleted": log_id}

@app.delete("/api/logs")
def clear_logs(user: UserOut = Depends(get_current_user)):
    with get_conn() as conn:
        conn.execute("DELETE FROM logs WHERE user_id=?", (user.id,))
        conn.commit()
        return {"cleared": True}

@app.patch("/api/logs/{log_id}/toggle", response_model=LogOut)
def toggle_log(log_id: str, user: UserOut = Depends(get_current_user)):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM logs WHERE id=? AND user_id=?", (log_id, user.id)).fetchone()
        if not row:
            raise HTTPException(404, "Not found")
        d = row_to_dict(row)
        new_status = "open" if d["status"] == "solved" else "solved"
        conn.execute("UPDATE logs SET status=? WHERE id=? AND user_id=?", (new_status, log_id, user.id))
        conn.commit()
        updated = conn.execute("SELECT * FROM logs WHERE id=? AND user_id=?", (log_id, user.id)).fetchone()
        return row_to_dict(updated)

# ---------- Serve Frontend ----------
@app.get("/")
def serve_index():
    if os.path.exists(INDEX_PATH):
        return FileResponse(INDEX_PATH)
    return {"detail": "index.html not found"}

@app.get("/login")
def serve_login():
    if os.path.exists(LOGIN_PATH):
        return FileResponse(LOGIN_PATH)
    return {"detail": "login.html not found"}
