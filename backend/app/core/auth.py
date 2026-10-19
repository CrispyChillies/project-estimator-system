"""Authentication: argon2 password hashing, opaque server-side sessions in an HTTP-only cookie, double-submit
CSRF, login throttling, and the request-scoped current user."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, Request, Response
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError
from app.db.models import AuthSession, LoginAttempt, User
from app.db.session import get_db

SESSION_COOKIE = "calibr_session"
CSRF_COOKIE = "calibr_csrf"
CSRF_HEADER = "x-csrf-token"
MIN_PASSWORD = 10
_ph = PasswordHasher()


class Unauthorized(AppError):
    def __init__(self, message: str = "Please sign in"):
        super().__init__("unauthorized", message, 401)


class Forbidden(AppError):
    def __init__(self, message: str = "You do not have access to this"):
        super().__init__("forbidden", message, 403)


def hash_password(pw: str) -> str:
    return _ph.hash(pw)


def verify_password(pw: str, hashed: str | None) -> bool:
    if not hashed:
        _ph.hash("timing-equaliser")  # keep timing similar for unknown users
        return False
    try:
        return _ph.verify(hashed, pw)
    except (VerificationError, InvalidHashError):
        return False


def password_problem(pw: str, email: str = "") -> str | None:
    if len(pw) < MIN_PASSWORD:
        return f"Password must be at least {MIN_PASSWORD} characters"
    if email and pw.lower() == email.lower():
        return "Password must not equal the email address"
    if len(set(pw)) < 4:
        return "Password is too simple"
    return None


def _digest(token: str) -> str:
    key = (get_settings().session_secret or "dev-only-secret").encode()
    return hmac.new(key, token.encode(), hashlib.sha256).hexdigest()


def new_token() -> tuple[str, str]:
    t = secrets.token_urlsafe(32)
    return t, _digest(t)


def set_session_cookie(resp: Response, token: str) -> None:
    s = get_settings()
    resp.set_cookie(SESSION_COOKIE, token, max_age=s.session_days * 86400, httponly=True, secure=s.secure_cookies,
                    samesite="lax", path="/")


def set_csrf_cookie(resp: Response, value: str | None = None) -> str:
    v = value or secrets.token_urlsafe(24)
    resp.set_cookie(CSRF_COOKIE, v, max_age=get_settings().session_days * 86400, httponly=False,
                    secure=get_settings().secure_cookies, samesite="lax", path="/")
    return v


def create_session(db: Session, user: User, user_agent: str = "") -> str:
    token, digest = new_token()
    now = datetime.now(UTC)
    db.add(AuthSession(user_id=user.id, token_hash=digest, expires_at=now + timedelta(days=get_settings().session_days),
                       last_seen_at=now, user_agent=user_agent[:300]))
    user.last_login_at = now
    db.flush()
    return token


def revoke_sessions(db: Session, user_id: uuid.UUID, except_digest: str | None = None) -> None:
    q = update(AuthSession).where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
    if except_digest:
        q = q.where(AuthSession.token_hash != except_digest)
    db.execute(q.values(revoked_at=datetime.now(UTC)))


def session_from_request(db: Session, request: Request) -> tuple[AuthSession, User] | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    sess = db.scalar(select(AuthSession).where(AuthSession.token_hash == _digest(token)))
    now = datetime.now(UTC)
    if sess is None or sess.revoked_at is not None or sess.expires_at < now:
        return None
    user = db.get(User, sess.user_id)
    if user is None or not user.is_active:
        return None
    # Sliding expiry, written at most every 10 minutes.
    if sess.last_seen_at is None or now - sess.last_seen_at > timedelta(minutes=10):
        sess.last_seen_at = now
        sess.expires_at = now + timedelta(days=get_settings().session_days)
        db.commit()
    return sess, user


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    found = session_from_request(db, request)
    if found is None:
        raise Unauthorized()
    request.state.user_id = found[1].id
    return found[1]


def current_user_id(user: User = Depends(current_user)) -> uuid.UUID:
    return user.id


def require_admin(user: User = Depends(current_user)) -> User:
    if user.role != "admin":
        raise Forbidden("Admins only")
    return user


# ---------------- login throttling ----------------
WINDOW = timedelta(minutes=15)
MAX_FAILURES = 5


def throttle_key(request: Request, email: str) -> str:
    ip = request.client.host if request.client else "?"
    return f"{ip}|{email.strip().lower()}"[:300]


def check_throttle(db: Session, key: str) -> None:
    since = datetime.now(UTC) - WINDOW
    fails = db.scalar(select(func.count()).select_from(LoginAttempt).where(
        LoginAttempt.key == key, LoginAttempt.success.is_(False), LoginAttempt.created_at >= since)) or 0
    if fails >= MAX_FAILURES:
        # Exponential backoff: each extra failure doubles the wait (capped at the window).
        last = db.scalar(select(func.max(LoginAttempt.created_at)).where(LoginAttempt.key == key))
        wait = min(WINDOW, timedelta(seconds=30 * 2 ** (fails - MAX_FAILURES)))
        if last and datetime.now(UTC) - last < wait:
            raise AppError("too_many_attempts", "Too many sign-in attempts. Try again in a few minutes.", 429)


def record_attempt(db: Session, key: str, success: bool) -> None:
    db.add(LoginAttempt(key=key, success=success))
    db.flush()


# ---------------- CSRF (double submit) ----------------
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
CSRF_EXEMPT = {"/api/v1/auth/csrf"}


def csrf_ok(request: Request) -> bool:
    if request.method in SAFE_METHODS or request.url.path in CSRF_EXEMPT or not request.url.path.startswith("/api/"):
        return True
    cookie = request.cookies.get(CSRF_COOKIE)
    header = request.headers.get(CSRF_HEADER)
    return bool(cookie and header and hmac.compare_digest(cookie, header))
