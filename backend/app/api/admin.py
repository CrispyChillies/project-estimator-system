"""Admin-only: users, usage and caps, archived reference library switch, learning hyperparameters, LLM usage."""

import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.auth import create_reset_link
from app.core.access import ARCHIVE_SETTING, include_archive_for_all
from app.core.auth import require_admin, revoke_sessions
from app.core.config import get_settings
from app.core.errors import AppError, NotFound
from app.db.models import (
    Document,
    Estimate,
    LLMCall,
    Project,
    Setting,
    Task,
    TaskActual,
    User,
)
from app.db.session import get_db
from app.llm import budget
from app.llm.gateway import get_gateway
from app.services.settings import DEFAULTS, LearningParams, get_params, reset_params, save_params

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)])


class UserPatch(BaseModel):
    is_active: bool | None = None
    role: Literal["admin", "member"] | None = None
    daily_usd_cap: float | None = Field(None, ge=0)


class ArchiveIn(BaseModel):
    include_archive_for_all: bool


def month_start() -> datetime:
    now = datetime.now(UTC)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _spend_by_user(db: Session, since: datetime) -> dict[uuid.UUID, dict]:
    rows = db.execute(select(LLMCall.user_id, func.count(), func.coalesce(func.sum(LLMCall.cost_usd), 0),
                             func.coalesce(func.sum(LLMCall.input_tokens + LLMCall.output_tokens), 0))
                      .where(LLMCall.created_at >= since).group_by(LLMCall.user_id))
    return {u: {"calls": c, "cost_usd": float(x), "tokens": int(t)} for u, c, x, t in rows}


@router.get("/users")
def list_users(db: Session = Depends(get_db)) -> list[dict]:
    spend = _spend_by_user(db, month_start())
    counts = dict(db.execute(select(Project.owner_id, func.count()).group_by(Project.owner_id)).all())
    cap = get_settings().user_daily_usd_cap
    return [{"id": str(u.id), "name": u.name, "email": u.email, "role": u.role, "is_active": u.is_active,
             "archived": u.archived, "last_login_at": u.last_login_at, "projects": counts.get(u.id, 0),
             "spend_month": spend.get(u.id, {"calls": 0, "cost_usd": 0.0, "tokens": 0}),
             "daily_usd_cap": u.daily_usd_cap if u.daily_usd_cap is not None else cap}
            for u in db.scalars(select(User).order_by(User.archived, User.created_at))]


@router.patch("/users/{user_id}")
def patch_user(user_id: uuid.UUID, body: UserPatch, admin: User = Depends(require_admin),
               db: Session = Depends(get_db)) -> dict:
    u = db.get(User, user_id)
    if u is None:
        raise NotFound("User")
    if u.id == admin.id and (body.is_active is False or body.role == "member"):
        raise AppError("self_lockout", "You cannot deactivate or demote yourself", 409)
    if body.is_active is not None:
        if body.is_active and (u.archived or not u.password_hash):
            raise AppError("archived_user", "Archived users cannot be activated", 409)
        u.is_active = body.is_active
        if not body.is_active:
            revoke_sessions(db, u.id)
    if body.role:
        u.role = body.role
    if body.daily_usd_cap is not None:
        if body.daily_usd_cap > get_settings().llm_budget_usd:
            raise AppError("cap_too_high", "A user cap cannot exceed the global budget", 422)
        u.daily_usd_cap = body.daily_usd_cap
    db.commit()
    return {"id": str(u.id), "is_active": u.is_active, "role": u.role, "daily_usd_cap": u.daily_usd_cap}


@router.post("/users/{user_id}/reset-link")
def reset_link(user_id: uuid.UUID, admin: User = Depends(require_admin), db: Session = Depends(get_db)) -> dict:
    u = db.get(User, user_id)
    if u is None or u.archived:
        raise NotFound("User")
    link = create_reset_link(db, u.id, admin.id)
    db.commit()
    return {"url": link, "expires_in_hours": 24}


@router.get("/usage")
def usage(db: Session = Depends(get_db)) -> dict:
    today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    users = {u.id: u for u in db.scalars(select(User))}
    def rows(since):
        return [{"user_id": str(k) if k else None, "name": users[k].name if k in users else "system", **v}
                for k, v in _spend_by_user(db, since).items()]
    gw = get_gateway()
    return {"today": rows(today), "month": rows(month_start()),
            "global": {"budget_usd": get_settings().llm_budget_usd, "spent_usd": budget.spend_fn(),
                       "user_daily_usd_cap": get_settings().user_daily_usd_cap},
            "model": {"mode": gw.mode, "model": gw.model, "embedding_model": gw.embedding_model}}


@router.get("/archive")
def archive(db: Session = Depends(get_db)) -> dict:
    pids = select(Project.id).where(Project.is_archive.is_(True))
    eids = select(Estimate.id).where(Estimate.project_id.in_(pids))
    return {
        "description": "Archived synthetic test data, kept for storage and reference.",
        "include_archive_for_all": include_archive_for_all(db),
        "counts": {
            "projects": db.scalar(select(func.count()).select_from(Project).where(Project.is_archive.is_(True))),
            "estimates": db.scalar(select(func.count()).select_from(Estimate).where(Estimate.project_id.in_(pids))),
            "tasks": db.scalar(select(func.count()).select_from(Task).where(Task.estimate_id.in_(eids))),
            "actuals": db.scalar(select(func.count()).select_from(TaskActual).join(Task, Task.id == TaskActual.task_id)
                                 .where(Task.estimate_id.in_(eids))),
            "documents": db.scalar(select(func.count()).select_from(Document).where(Document.project_id.in_(pids))),
        },
    }


@router.put("/archive")
def set_archive(body: ArchiveIn, db: Session = Depends(get_db)) -> dict:
    row = db.get(Setting, ARCHIVE_SETTING)
    if row is None:
        db.add(Setting(key=ARCHIVE_SETTING, value={"include_archive_for_all": body.include_archive_for_all}))
    else:
        row.value = {**(row.value or {}), "include_archive_for_all": body.include_archive_for_all}
    db.commit()
    return {"include_archive_for_all": body.include_archive_for_all}


@router.get("/learning")
def learning(db: Session = Depends(get_db)) -> dict[str, Any]:
    schema = LearningParams.model_json_schema()["properties"]
    return {"values": get_params(db).model_dump(), "defaults": DEFAULTS.model_dump(),
            "descriptions": {k: v.get("description", "") for k, v in schema.items()}}


@router.put("/learning")
def update_learning(values: dict[str, Any], db: Session = Depends(get_db)) -> dict[str, Any]:
    return save_params(db, values).model_dump()


@router.post("/learning/reset")
def reset_learning_params(db: Session = Depends(get_db)) -> dict[str, Any]:
    return reset_params(db).model_dump()


@router.get("/llm-usage")
def admin_llm_usage(db: Session = Depends(get_db)) -> dict[str, Any]:
    def grouped(col):
        rows = db.execute(select(col, func.count(), func.coalesce(func.sum(LLMCall.cost_usd), 0),
                                 func.coalesce(func.sum(LLMCall.input_tokens), 0),
                                 func.coalesce(func.sum(LLMCall.output_tokens), 0),
                                 func.count().filter(LLMCall.cache_hit.is_(True))).group_by(col)).all()
        return [{"key": k, "calls": c, "cost_usd": float(x), "input_tokens": i, "output_tokens": o, "cache_hits": h}
                for k, c, x, i, o, h in rows]

    total = float(db.scalar(select(func.coalesce(func.sum(LLMCall.cost_usd), 0))) or 0)
    return {"total_cost_usd": total, "ledger_cost_usd": budget.spend_fn(), "budget_usd": get_settings().llm_budget_usd,
            "by_purpose": grouped(LLMCall.purpose), "by_model": grouped(LLMCall.model)}


@router.get("/model-status")
def model_status(db: Session = Depends(get_db)) -> dict[str, Any]:
    from app.services.learning import model_status as status

    return status(db)
