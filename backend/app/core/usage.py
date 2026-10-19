"""Per-user cost protection: who is spending (context var), daily USD caps, hourly request limits and
concurrent-run limits. The global cap stays in app.llm.budget."""

from __future__ import annotations

import time
import uuid
from collections import defaultdict, deque
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime, timedelta

from fastapi import Depends, Request
from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.errors import AppError

_llm_user: ContextVar[uuid.UUID | None] = ContextVar("llm_user", default=None)


def llm_user() -> uuid.UUID | None:
    return _llm_user.get()


@contextmanager
def use_llm_user(user_id: uuid.UUID | None) -> Iterator[None]:
    tok = _llm_user.set(user_id)
    try:
        yield
    finally:
        _llm_user.reset(tok)


@contextmanager
def request_user_context(request: Request) -> Iterator[None]:
    """Attribute LLM spend in this request to the signed-in user (resolved from the session cookie)."""
    uid = None
    if request.url.path.startswith("/api/v1/") and not request.url.path.startswith("/api/v1/auth/"):
        from app.core.auth import session_from_request
        from app.db.session import SessionLocal

        try:
            with SessionLocal() as db:
                found = session_from_request(db, request)
                uid = found[1].id if found else None
        except Exception:  # attribution must never block a request; auth is enforced by the guard
            uid = None
    with use_llm_user(uid):
        yield


class AllowanceExceeded(AppError):
    def __init__(self, cap: float):
        reset = (datetime.now(UTC) + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        super().__init__("allowance_exceeded",
                         f"Daily AI allowance reached (${cap:.2f}). It resets at {reset:%H:%M} UTC.", 429,
                         {"resets_at": reset.isoformat(), "cap_usd": cap})


def user_cap(user) -> float:
    return user.daily_usd_cap if user.daily_usd_cap is not None else get_settings().user_daily_usd_cap


def spent_today(db, user_id: uuid.UUID) -> float:
    from app.db.models import LLMCall

    today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    return float(db.scalar(select(func.coalesce(func.sum(LLMCall.cost_usd), 0))
                           .where(LLMCall.user_id == user_id, LLMCall.created_at >= today)) or 0)


def check_user_allowance(estimated: float = 0.0) -> None:
    """Called before every live LLM call (after the global check)."""
    uid = llm_user()
    if uid is None:
        return
    from app.db.models import User
    from app.db.session import SessionLocal

    with SessionLocal() as db:
        user = db.get(User, uid)
        if user is None:
            return
        cap = user_cap(user)
        if spent_today(db, uid) + estimated >= cap:
            raise AllowanceExceeded(cap)


# ---- request rate limit for AI-triggering endpoints (per process; approximate across workers) ----
_hits: dict[uuid.UUID, deque[float]] = defaultdict(deque)


def ai_rate_limit(request: Request) -> None:
    uid = getattr(request.state, "user_id", None)
    if uid is None:
        return
    window, limit = 3600.0, get_settings().user_hourly_requests
    q = _hits[uid]
    now = time.monotonic()
    while q and now - q[0] > window:
        q.popleft()
    if len(q) >= limit:
        raise AppError("rate_limited", f"Too many AI requests this hour (limit {limit}). Please wait a bit.", 429)
    q.append(now)


def check_concurrency(db, user_id: uuid.UUID | None) -> None:
    if user_id is None:
        return
    from app.db.models import AgentSession, Job

    running = (db.scalar(select(func.count()).select_from(AgentSession).where(
        AgentSession.created_by == user_id, AgentSession.run_state == "running")) or 0) + (db.scalar(
        select(func.count()).select_from(Job).where(Job.user_id == user_id, Job.status.in_(("queued", "running"))))
        or 0)
    if running >= get_settings().max_concurrent_runs_per_user:
        raise AppError("too_many_runs", "You already have AI work running. Wait for it to finish.", 429)


AIRateLimit = Depends(ai_rate_limit)


MODEL_KEYS = {"model", "model_name", "provider", "llm_mode", "openai_model", "embedding_model", "reasoning_effort",
              "temperature", "llm_budget_usd", "budget_usd", "max_tokens", "api_key", "base_url"}


async def deny_model_override(request: Request) -> None:
    """Model, provider, mode and budget come from the environment only; a request trying to set them is refused."""
    if request.method in ("GET", "HEAD", "OPTIONS") or "json" not in request.headers.get("content-type", ""):
        return
    try:
        body = await request.json()
    except Exception:
        return
    if isinstance(body, dict) and (bad := MODEL_KEYS & {k.lower() for k in body}):
        import logging

        logging.getLogger("app.security").warning("model override attempt",
                                                  extra={"extra": {"path": request.url.path, "keys": sorted(bad)}})
        raise AppError("model_locked", "The AI model and its settings cannot be changed from the app.", 400)
