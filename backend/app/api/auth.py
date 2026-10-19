"""Sign-up, sign-in, sign-out, profile, password change and one-time reset links."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import auth as A
from app.core.config import get_settings
from app.core.errors import AppError
from app.db.models import PasswordReset, User
from app.db.session import get_db

router = APIRouter(prefix="/auth", tags=["auth"])

GENERIC_LOGIN_ERROR = "Email or password is incorrect"


class SignupIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)
    invite_code: str | None = Field(None, max_length=200)


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=1, max_length=200)


class ProfileIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class PasswordIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=1, max_length=200)


class ResetIn(BaseModel):
    token: str = Field(min_length=10, max_length=200)
    new_password: str = Field(min_length=1, max_length=200)


class OnboardingIn(BaseModel):
    state: dict


class QuickIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: str | None = Field(None, max_length=200)


def me_out(u: User) -> dict:
    return {"id": str(u.id), "name": u.name, "email": u.email, "role": u.role,
            "onboarding_state": u.onboarding_state or {}, "last_login_at": u.last_login_at,
            "display_currency": u.display_currency or "VND", "tag_colors": u.tag_colors or {}}


def _login(db: Session, request: Request, response: Response, user: User) -> dict:
    token = A.create_session(db, user, request.headers.get("user-agent", ""))
    db.commit()
    A.set_session_cookie(response, token)
    A.set_csrf_cookie(response)
    return me_out(user)


@router.get("/csrf")
def csrf(request: Request, response: Response) -> dict:
    """Issues the CSRF cookie (double-submit); the client echoes it in X-CSRF-Token on writes."""
    value = request.cookies.get(A.CSRF_COOKIE) or A.set_csrf_cookie(response)
    if request.cookies.get(A.CSRF_COOKIE):
        A.set_csrf_cookie(response, value)
    return {"csrf": value}


@router.get("/config")
def config() -> dict:
    return {"signup_mode": get_settings().signup_mode, "auth_mode": get_settings().auth_mode}


@router.post("/quick")
def quick_signin(body: QuickIn, request: Request, response: Response, db: Session = Depends(get_db)) -> dict:
    """AUTH_MODE=quick: no password. Reusing an email resumes that member's account; admins must use a password."""
    if get_settings().auth_mode != "quick":
        raise AppError("quick_disabled", "Quick sign-in is not enabled", 403)
    key = A.throttle_key(request, "quick")
    A.check_throttle(db, key)
    email = (body.email or "").strip().lower()
    user = db.scalar(select(User).where(func.lower(User.email) == email)) if email else None
    if user is not None and (user.role == "admin" or user.archived or not user.is_active):
        raise AppError("password_required", "This account signs in with a password", 403)
    if user is None:
        user = User(name=body.name.strip(), email=email or f"guest-{uuid.uuid4().hex[:12]}@guest.calibr",
                    role="member", is_active=True, onboarding_state={})
        db.add(user)
        db.flush()
    A.record_attempt(db, key, True)
    return _login(db, request, response, user)


@router.post("/signup", status_code=201)
def signup(body: SignupIn, request: Request, response: Response, db: Session = Depends(get_db)) -> dict:
    s = get_settings()
    if s.signup_mode == "closed":
        raise AppError("signup_closed", "Sign-up is closed. Ask an administrator for an account.", 403)
    if s.signup_mode == "invite":
        import hmac

        if not s.invite_code or not body.invite_code or not hmac.compare_digest(body.invite_code, s.invite_code):
            raise AppError("invalid_invite", "The invite code is not valid", 403)
    email = body.email.strip().lower()
    if problem := A.password_problem(body.password, email):
        raise AppError("weak_password", problem, 422)
    if db.scalar(select(User).where(func.lower(User.email) == email)):
        # Same response shape as success would leak nothing if we silently ignored; we must tell the user,
        # but keep the wording neutral.
        raise AppError("signup_failed", "Could not create an account with these details", 409)
    user = User(name=body.name.strip(), email=email, role="member", password_hash=A.hash_password(body.password),
                is_active=True, onboarding_state={})
    db.add(user)
    db.flush()
    return _login(db, request, response, user)


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)) -> dict:
    email = body.email.strip().lower()
    key = A.throttle_key(request, email)
    A.check_throttle(db, key)
    user = db.scalar(select(User).where(func.lower(User.email) == email))
    ok = A.verify_password(body.password, user.password_hash if user else None) and bool(user and user.is_active)
    A.record_attempt(db, key, ok)
    if not ok:
        db.commit()
        raise AppError("invalid_credentials", GENERIC_LOGIN_ERROR, 401)
    return _login(db, request, response, user)


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, db: Session = Depends(get_db)) -> Response:
    found = A.session_from_request(db, request)
    if found:
        found[0].revoked_at = datetime.now(UTC)
        db.commit()
    response.delete_cookie(A.SESSION_COOKIE, path="/")
    response.status_code = 204
    return response


@router.get("/me")
def me(user: User = Depends(A.current_user)) -> dict:
    return me_out(user)


@router.get("/session")
def session_status(request: Request, db: Session = Depends(get_db)) -> dict:
    """For public pages: 200 either way, so anonymous visitors do not produce 401 noise."""
    found = A.session_from_request(db, request)
    return {"user": me_out(found[1]) if found else None}


@router.patch("/me")
def update_me(body: ProfileIn, user: User = Depends(A.current_user), db: Session = Depends(get_db)) -> dict:
    u = db.get(User, user.id)
    u.name = body.name.strip()
    db.commit()
    return me_out(u)


@router.put("/me/onboarding")
def update_onboarding(body: OnboardingIn, user: User = Depends(A.current_user), db: Session = Depends(get_db)) -> dict:
    u = db.get(User, user.id)
    u.onboarding_state = {**(u.onboarding_state or {}), **body.state}
    db.commit()
    return me_out(u)


@router.post("/password", status_code=204)
def change_password(body: PasswordIn, request: Request, user: User = Depends(A.current_user),
                    db: Session = Depends(get_db)) -> Response:
    u = db.get(User, user.id)
    if not A.verify_password(body.current_password, u.password_hash):
        raise AppError("invalid_credentials", "Current password is incorrect", 400)
    if problem := A.password_problem(body.new_password, u.email):
        raise AppError("weak_password", problem, 422)
    u.password_hash = A.hash_password(body.new_password)
    token = request.cookies.get(A.SESSION_COOKIE)
    A.revoke_sessions(db, u.id, except_digest=A._digest(token) if token else None)
    db.commit()
    return Response(status_code=204)


@router.post("/reset")
def reset_password(body: ResetIn, request: Request, response: Response, db: Session = Depends(get_db)) -> dict:
    digest = A._digest(body.token)
    r = db.scalar(select(PasswordReset).where(PasswordReset.token_hash == digest))
    if r is None or r.used_at is not None or r.expires_at < datetime.now(UTC):
        raise AppError("invalid_reset", "This reset link is invalid or has expired", 400)
    user = db.get(User, r.user_id)
    if user is None or not user.is_active:
        raise AppError("invalid_reset", "This reset link is invalid or has expired", 400)
    if problem := A.password_problem(body.new_password, user.email):
        raise AppError("weak_password", problem, 422)
    user.password_hash = A.hash_password(body.new_password)
    r.used_at = datetime.now(UTC)
    A.revoke_sessions(db, user.id)
    return _login(db, request, response, user)


def create_reset_link(db: Session, user_id: uuid.UUID, admin_id: uuid.UUID) -> str:
    token, digest = A.new_token()
    db.add(PasswordReset(user_id=user_id, token_hash=digest, expires_at=datetime.now(UTC) + timedelta(hours=24),
                         created_by=admin_id))
    db.flush()
    return f"{get_settings().public_app_url.rstrip('/')}/reset?token={token}"


RoleLiteral = Literal["admin", "member"]
