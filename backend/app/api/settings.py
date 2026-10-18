import uuid
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.errors import NotFound
from app.db.models import (
    CalibrationRun,
    CalibrationStat,
    DeliveryRole,
    LearnedRule,
    LLMCall,
    TaskCategory,
    User,
)
from app.db.session import get_db
from app.llm.gateway import get_gateway
from app.schemas import api as S
from app.services import jobs
from app.services.settings import DEFAULTS, LearningParams, get_params, reset_params, save_params

router = APIRouter(tags=["settings"])


@router.get("/health", tags=["health"])
def health(db: Session = Depends(get_db)) -> dict:
    db.execute(text("SELECT 1"))
    rev = db.execute(text("SELECT version_num FROM alembic_version")).scalar()
    return {"status": "ok", "db": True, "migration": rev, "llm_mode": get_gateway().mode}


@router.get("/users", response_model=list[S.UserOut])
def users(db: Session = Depends(get_db)):
    return list(db.scalars(select(User).order_by(User.name)))


@router.get("/roles", response_model=list[S.RoleOut])
def roles(db: Session = Depends(get_db)):
    return list(db.scalars(select(DeliveryRole).order_by(DeliveryRole.name)))


@router.put("/roles/{role_id}", response_model=S.RoleOut)
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


@router.put("/categories/{category_id}", response_model=S.CategoryOut)
def update_category(category_id: uuid.UUID, body: S.CategoryUpdate, db: Session = Depends(get_db)):
    c = db.get(TaskCategory, category_id)
    if c is None:
        raise NotFound("Category")
    c.name, c.description = body.name, body.description
    db.commit()
    return c


@router.get("/settings/learning")
def learning(db: Session = Depends(get_db)) -> dict[str, Any]:
    schema = LearningParams.model_json_schema()["properties"]
    return {"values": get_params(db).model_dump(), "defaults": DEFAULTS.model_dump(),
            "descriptions": {k: v.get("description", "") for k, v in schema.items()}}


@router.put("/settings/learning")
def update_learning(values: dict[str, Any], db: Session = Depends(get_db)) -> dict[str, Any]:
    return save_params(db, values).model_dump()


@router.post("/settings/learning/reset")
def reset_learning_params(db: Session = Depends(get_db)) -> dict[str, Any]:
    return reset_params(db).model_dump()


@router.post("/admin/reset-learning", status_code=204)
def reset_learning(db: Session = Depends(get_db)):
    """Clears learned stats, runs and rules. Edit history and actuals are kept, so learning can be recomputed."""
    db.query(CalibrationStat).delete()
    db.query(CalibrationRun).delete()
    db.query(LearnedRule).delete()
    db.commit()


@router.get("/llm/usage", response_model=S.LLMUsage)
def llm_usage(db: Session = Depends(get_db)):
    gw = get_gateway()
    agg = db.execute(select(func.count(), func.coalesce(func.sum(LLMCall.input_tokens), 0),
                            func.coalesce(func.sum(LLMCall.output_tokens), 0), func.coalesce(func.sum(LLMCall.cost_usd), 0),
                            func.count().filter(LLMCall.cache_hit.is_(True)))).one()
    by = db.execute(select(LLMCall.purpose, func.count(), func.coalesce(func.sum(LLMCall.cost_usd), 0))
                    .group_by(LLMCall.purpose)).all()
    return S.LLMUsage(calls=agg[0], input_tokens=agg[1], output_tokens=agg[2], cost_usd=float(agg[3]), cache_hits=agg[4],
                      mode=gw.mode, model=gw.model, embedding_model=gw.embedding_model,
                      by_purpose=[{"purpose": p, "calls": c, "cost_usd": float(x)} for p, c, x in by])


@router.get("/jobs/{job_id}", response_model=S.JobOut)
def get_job(job_id: uuid.UUID, db: Session = Depends(get_db)):
    return jobs.get_job(db, job_id)
