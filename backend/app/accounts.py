"""Accounts: email + password sign-up, login sessions and roles (user, admin).

Passwords are stored as PBKDF2-SHA256 hashes with a random salt (never the password itself).
A session is a random token in an httponly cookie; only its SHA-256 hash is stored, so a stolen
database cannot be used to log in. A guest (cookie id, no password) can sign up and keeps all chats.
"""
import hashlib
import hmac
import re
import secrets

from .db import DB, now

ITERATIONS = 240_000
SESSION_DAYS = 30
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[A-Za-z]{2,24}$")


class AuthError(Exception):
    pass


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS)
    return f"pbkdf2_sha256${ITERATIONS}${salt.hex()}${dk.hex()}"


def check_password(password: str, stored: str | None) -> bool:
    try:
        algo, iters, salt, digest = (stored or "").split("$")
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iters))
        return hmac.compare_digest(dk.hex(), digest)
    except (ValueError, TypeError):
        hashlib.pbkdf2_hmac("sha256", password.encode(), b"0" * 16, ITERATIONS)  # same time either way
        return False


def valid_email(email: str) -> str:
    email = (email or "").strip().lower()
    if not EMAIL_RE.match(email):
        raise AuthError("Please enter a valid email address.")
    return email


def check_strength(password: str) -> None:
    if len(password or "") < 8:
        raise AuthError("Use a password with at least 8 characters.")
    if len(password) > 200:
        raise AuthError("That password is too long.")


def by_email(db: DB, email: str) -> dict | None:
    return db.one("SELECT * FROM users WHERE email=?", (email.strip().lower(),))


def register(db: DB, guest_user_id: str, email: str, password: str, name: str = "") -> dict:
    """Turn the current guest into a real account (keeps chats, credits and memory)."""
    email = valid_email(email)
    check_strength(password)
    if by_email(db, email):
        raise AuthError("An account with this email already exists. Log in instead.")
    guest = db.one("SELECT * FROM users WHERE id=?", (guest_user_id,))
    if guest and guest.get("email"):
        raise AuthError("You are already logged in.")
    db.run("UPDATE users SET email=?, pw_hash=?, name=COALESCE(NULLIF(?, ''), name) WHERE id=?",
           (email, hash_password(password), name.strip()[:40], guest_user_id))
    return db.one("SELECT * FROM users WHERE id=?", (guest_user_id,))


def authenticate(db: DB, email: str, password: str) -> dict:
    user = by_email(db, email or "")
    if not user or not check_password(password or "", user.get("pw_hash")):
        if not user:
            check_password(password or "", None)
        raise AuthError("Wrong email or password.")
    if user.get("status") == "blocked":
        raise AuthError("This account is blocked. Contact support.")
    return user


def create_session(db: DB, user_id: str, ip: str = "", agent: str = "") -> str:
    token = secrets.token_urlsafe(32)
    db.run("INSERT INTO sessions(token_hash,user_id,created_at,expires_at,ip,agent) VALUES(?,?,?,?,?,?)",
           (_h(token), user_id, now(), now() + SESSION_DAYS * 86400, ip[:64], agent[:200]))
    return token


def session_user(db: DB, token: str | None) -> dict | None:
    if not token or len(token) > 100:
        return None
    s = db.one("SELECT * FROM sessions WHERE token_hash=?", (_h(token),))
    if not s or s["expires_at"] < now():
        return None
    return db.one("SELECT * FROM users WHERE id=?", (s["user_id"],))


def end_session(db: DB, token: str | None) -> None:
    if token:
        db.run("DELETE FROM sessions WHERE token_hash=?", (_h(token),))


def end_all_sessions(db: DB, user_id: str) -> None:
    db.run("DELETE FROM sessions WHERE user_id=?", (user_id,))


def ensure_admin(db: DB, email: str, password: str, user_id: str = "u_admin") -> dict:
    """Create or update the admin login (from ADMIN_EMAIL / ADMIN_PASSWORD or scripts/create_admin.py)."""
    email = valid_email(email)
    check_strength(password)
    existing = by_email(db, email)
    if existing:
        db.run("UPDATE users SET role='admin', pw_hash=?, status='active' WHERE id=?", (hash_password(password), existing["id"]))
        return db.one("SELECT * FROM users WHERE id=?", (existing["id"],))
    db.run("INSERT INTO users(id,name,plan,auto_spend,created_at,email,pw_hash,role,status) VALUES(?,?,?,?,?,?,?,?,?)",
           (user_id, "Admin", "pro", 20, now(), email, hash_password(password), "admin", "active"))
    return db.one("SELECT * FROM users WHERE id=?", (user_id,))


def _h(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
