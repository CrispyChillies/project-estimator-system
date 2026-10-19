import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.auth import current_user, require_admin
from app.core.config import get_settings
from app.core.errors import NotFound
from app.db.models import DeliveryRole, LLMCall, TaskCategory, User
from app.db.session import get_db
from app.schemas import api as S
from app.services import jobs

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


@router.get("/roles", response_model=list[S.RoleOut])
def roles(db: Session = Depends(get_db)):
    return list(db.scalars(select(DeliveryRole).order_by(DeliveryRole.name)))


@router.put("/roles/{role_id}", response_model=S.RoleOut, dependencies=[Depends(require_admin)])
def update_role(role_id: uuid.UUID, body: S.RoleUpdate, db: Session = Depends(get_db)):
    r = db.get(DeliveryRole, role_id)
    if r is None:
        raise NotFound("Role")
    r.hourly_rate, r.currency = body.hourly_rate, body.currency.upper()
    if body.color:
        r.color = body.color
    db.commit()
    return r


@router.get("/categories", response_model=list[S.CategoryOut])
def categories(db: Session = Depends(get_db)):
    return list(db.scalars(select(TaskCategory).order_by(TaskCategory.name)))


@router.put("/categories/{category_id}", response_model=S.CategoryOut, dependencies=[Depends(require_admin)])
def update_category(category_id: uuid.UUID, body: S.CategoryUpdate, db: Session = Depends(get_db)):
    c = db.get(TaskCategory, category_id)
    if c is None:
        raise NotFound("Category")
    c.name, c.description = body.name, body.description
    db.commit()
    return c


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
