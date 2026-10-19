import uuid
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.auth import current_user, require_admin
from app.core.config import get_settings
from app.core.errors import AppError, NotFound
from app.db.models import DeliveryRole, LLMCall, TaskCategory, User
from app.db.session import get_db
from app.schemas import api as S
from app.services import fx, jobs, money
from app.services.rates import PALETTE

router = APIRouter(tags=["settings"])
public = APIRouter(tags=["health"])


@public.get("/health")
def health(db: Session = Depends(get_db)) -> dict:
    db.execute(text("SELECT 1"))
    rev = db.execute(text("SELECT version_num FROM alembic_version")).scalar()
    return {"status": "ok", "db": True, "migration": rev}


@public.get("/ready")
def ready(db: Session = Depends(get_db)) -> dict:
    from pathlib import Path

    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[2] / "alembic"))
    head = ScriptDirectory.from_config(cfg).get_current_head()
    rev = db.execute(text("SELECT version_num FROM alembic_version")).scalar()
    if rev != head:
        from app.core.errors import AppError

        raise AppError("not_ready", "Database migrations are not up to date", 503)
    return {"status": "ready", "migration": rev}


def _color(user: User, kind: str, ref: uuid.UUID, default: str) -> str:
    c = (user.tag_colors or {}).get(f"{kind}:{ref}")
    return c if c in PALETTE else default


def _role_out(r: DeliveryRole, user: User) -> dict:
    mine = (user.rate_overrides or {}).get(str(r.id))
    mine = int(mine) if isinstance(mine, int | float) and mine > 0 else None
    default = int(r.hourly_rate_vnd or 0)
    return {"id": r.id, "name": r.name, "color": _color(user, "role", r.id, r.color), "default_color": r.color,
            "hourly_rate_vnd": default, "my_rate_vnd": mine, "rate_vnd": mine or default}


def _vnd(db: Session, body: S.RoleUpdate) -> int:
    if body.amount is None:
        raise AppError("bad_value", "amount is required", 422)
    return money.to_vnd(body.amount, body.currency, fx.get_rate(db))


@router.get("/roles", response_model=list[S.RoleOut])
def roles(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return [_role_out(r, user) for r in db.scalars(select(DeliveryRole).order_by(DeliveryRole.name))]


@router.put("/roles/{role_id}", response_model=S.RoleOut, dependencies=[Depends(require_admin)])
def update_role(role_id: uuid.UUID, body: S.RoleUpdate, db: Session = Depends(get_db),
                user: User = Depends(current_user)):
    """Admin: workspace default rate (and default colour) of a role."""
    r = db.get(DeliveryRole, role_id)
    if r is None:
        raise NotFound("Role")
    if body.amount is not None:
        r.hourly_rate_vnd = _vnd(db, body)
    if body.color:
        _check_color(body.color)
        r.color = body.color
    db.commit()
    return _role_out(r, user)


def _check_color(c: str) -> None:
    if c not in PALETTE:
        raise AppError("bad_color", f"color must be one of: {', '.join(PALETTE)}", 422)


@router.put("/me/rates/{rate_role}", response_model=S.RoleOut)
def set_my_rate(rate_role: uuid.UUID, body: S.RoleUpdate, db: Session = Depends(get_db),
                user: User = Depends(current_user)):
    """The signed-in user's own hourly rate for a role (used for their cost figures)."""
    r = db.get(DeliveryRole, rate_role)
    if r is None:
        raise NotFound("Role")
    vnd = _vnd(db, body)
    if vnd <= 0:
        raise AppError("bad_value", "rate must be greater than zero", 422)
    user.rate_overrides = {**(user.rate_overrides or {}), str(r.id): vnd}
    db.commit()
    return _role_out(r, user)


@router.delete("/me/rates/{rate_role}", response_model=S.RoleOut)
def reset_my_rate(rate_role: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(current_user)):
    r = db.get(DeliveryRole, rate_role)
    if r is None:
        raise NotFound("Role")
    user.rate_overrides = {k: v for k, v in (user.rate_overrides or {}).items() if k != str(r.id)}
    db.commit()
    return _role_out(r, user)


def _category_out(c: TaskCategory, user: User) -> dict:
    return {"id": c.id, "key": c.key, "name": c.name, "description": c.description,
            "color": _color(user, "category", c.id, c.color), "default_color": c.color}


@router.get("/categories", response_model=list[S.CategoryOut])
def categories(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return [_category_out(c, user) for c in db.scalars(select(TaskCategory).order_by(TaskCategory.name))]


@router.put("/categories/{category_id}", response_model=S.CategoryOut, dependencies=[Depends(require_admin)])
def update_category(category_id: uuid.UUID, body: S.CategoryUpdate, db: Session = Depends(get_db),
                    user: User = Depends(current_user)):
    c = db.get(TaskCategory, category_id)
    if c is None:
        raise NotFound("Category")
    if body.name is not None:
        c.name = body.name
    if body.description is not None:
        c.description = body.description
    if body.color:
        _check_color(body.color)
        c.color = body.color
    db.commit()
    return _category_out(c, user)


class ColorIn(BaseModel):
    kind: Literal["role", "category"]
    ref: uuid.UUID
    color: str | None = Field(None, max_length=20)  # null resets to the default


@router.put("/me/colors")
def set_my_color(body: ColorIn, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    """Per-user tag colour for a role or category (palette tokens only)."""
    model = DeliveryRole if body.kind == "role" else TaskCategory
    if db.get(model, body.ref) is None:
        raise NotFound(body.kind.capitalize())
    colors = dict(user.tag_colors or {})
    key = f"{body.kind}:{body.ref}"
    if body.color is None:
        colors.pop(key, None)
    else:
        _check_color(body.color)
        colors[key] = body.color
    user.tag_colors = colors
    db.commit()
    return {"tag_colors": colors}


class PrefsIn(BaseModel):
    display_currency: Literal["VND", "USD"]


@router.put("/me/preferences")
def set_my_preferences(body: PrefsIn, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    user.display_currency = body.display_currency
    db.commit()
    return {"display_currency": user.display_currency}


@router.get("/fx")
def get_workspace_fx(db: Session = Depends(get_db)) -> dict:
    """Workspace USD/VND rate (canonical money is VND)."""
    fx.maybe_refresh(db)
    return fx.get_fx(db)


@router.get("/me/usage")
def my_usage(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    """The user's AI allowance for today (no model or provider details)."""
    today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    spent = float(db.scalar(select(func.coalesce(func.sum(LLMCall.cost_usd), 0))
                            .where(LLMCall.user_id == user.id, LLMCall.created_at >= today)) or 0)
    cap = user.daily_usd_cap if user.daily_usd_cap is not None else get_settings().user_daily_usd_cap
    return {"spent_today_usd": round(spent, 4), "daily_cap_usd": cap,
            "remaining_usd": round(max(0.0, cap - spent), 4), "resets_at": today.replace(day=today.day).isoformat()}


@router.get("/jobs/{job_id}", response_model=S.JobOut)
def get_job(job_id: uuid.UUID, db: Session = Depends(get_db)):
    return jobs.get_job(db, job_id)


@router.get("/me/progress")
def my_progress(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    """Getting-started checklist, derived from what the user has actually done."""
    from app.db.models import AgentMessage, AgentSession, Document, Estimate, Project, Task, TaskActual

    mine = select(Project.id).where(Project.owner_id == user.id)
    if user.role == "admin":  # the admin's checklist only counts projects they created themselves
        mine = mine.where(Project.is_archive.is_(False))
    pids = list(db.scalars(mine))
    eids = list(db.scalars(select(Estimate.id).where(Estimate.project_id.in_(pids)))) if pids else []
    state = user.onboarding_state or {}

    def exists(q) -> bool:
        return bool(db.scalar(select(func.count()).select_from(q.subquery())))

    return {
        "created_project": bool(pids),
        "uploaded_brief": bool(pids) and exists(select(Document.id).where(Document.project_id.in_(pids))),
        "generated_estimate": bool(eids),
        "used_agent": bool(eids) and exists(select(AgentMessage.id).join(AgentSession, AgentSession.id ==
                                                                         AgentMessage.session_id)
                                            .where(AgentSession.estimate_id.in_(eids), AgentMessage.role == "user")),
        "finalized": bool(pids) and exists(select(Estimate.id).where(Estimate.project_id.in_(pids),
                                                                     Estimate.status == "final")),
        "entered_actuals": bool(eids) and exists(select(TaskActual.id).join(Task, Task.id == TaskActual.task_id)
                                                 .where(Task.estimate_id.in_(eids))),
        "viewed_insights": bool(state.get("viewed_insights")),
    }
