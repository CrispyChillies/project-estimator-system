import uuid

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.access import is_admin, pool_project_ids, pool_uses_archive
from app.core.auth import current_user
from app.core.errors import NotFound
from app.db.models import BacktestRun, LearnedRule, User
from app.db.session import get_db
from app.schemas import api as S
from app.services import backtest as bt
from app.services import insights, jobs
from app.services.learning import propose_lessons, recompute

router = APIRouter(tags=["insights"])


@router.get("/insights/scope")
def scope(db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    pool = pool_project_ids(db, user.id)
    return {"projects": None if pool is None else len(pool), "includes_reference_library": pool_uses_archive(db, user.id)}


@router.get("/insights/analytics")
def productivity_analytics(db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    from app.services.analytics import analytics

    return {**analytics(db, pool_project_ids(db, user.id)),
            "includes_reference_library": pool_uses_archive(db, user.id)}


@router.get("/insights/calibration")
def calibration(db: Session = Depends(get_db), user: User = Depends(current_user)) -> list[dict]:
    return insights.calibration_overview(db, pool_project_ids(db, user.id))


@router.get("/insights/timeline")
def timeline(db: Session = Depends(get_db), user: User = Depends(current_user)) -> list[dict]:
    return insights.timeline(db, user.id, is_admin(user))


@router.get("/insights/accuracy")
def accuracy(db: Session = Depends(get_db), user: User = Depends(current_user)) -> list[dict]:
    return insights.accuracy_over_time(db, pool_project_ids(db, user.id))


@router.get("/insights/structural")
def structural(db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    return insights.structural(db, pool_project_ids(db, user.id))


@router.post("/insights/recompute", status_code=204)
def manual_recompute(db: Session = Depends(get_db), user: User = Depends(current_user)):
    if is_admin(user):
        recompute(db, "manual")
        db.commit()


def _rules_query(user: User):
    q = select(LearnedRule).order_by(LearnedRule.status, LearnedRule.evidence_count.desc())
    return q.where(LearnedRule.owner_id == user.id)


@router.get("/rules", response_model=list[S.RuleOut])
def list_rules(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return list(db.scalars(_rules_query(user)))


@router.post("/rules/propose", response_model=list[S.RuleOut])
def propose(db: Session = Depends(get_db), user: User = Depends(current_user)):
    rules = propose_lessons(db, pool_project_ids(db, user.id), owner_id=user.id)
    db.commit()
    return rules


@router.post("/rules/{rule_id}/status", response_model=S.RuleOut)
def set_rule_status(rule_id: uuid.UUID, body: S.RuleStatusIn, db: Session = Depends(get_db),
                    user: User = Depends(current_user)):
    r = db.get(LearnedRule, rule_id)
    if r is None:
        raise NotFound("Rule")
    r.status = body.status
    if body.status == "active":
        r.approved_by = user.id
    db.commit()
    return r


# ---- backtest ----
@router.post("/backtest", response_model=S.JobOut, status_code=202)
def start_backtest(body: S.BacktestIn, bg: BackgroundTasks, db: Session = Depends(get_db),
                   user: User = Depends(current_user)):
    job = jobs.create_job(db, "backtest", user.id)
    uid = user.id
    bg.add_task(jobs.run_job, job.id, lambda s, progress: str(bt.run_backtest(s, body.model_dump(), progress,
                                                                               owner_id=uid).id))
    return job


@router.get("/backtest/runs", response_model=list[S.BacktestRunOut])
def list_runs(db: Session = Depends(get_db), user: User = Depends(current_user)):
    q = select(BacktestRun).order_by(BacktestRun.created_at.desc()).limit(20)
    if not is_admin(user):
        q = q.where(BacktestRun.owner_id == user.id)
    return list(db.scalars(q))


@router.get("/backtest/runs/{run_id}", response_model=S.BacktestDetail)
def get_run(run_id: uuid.UUID, db: Session = Depends(get_db)):
    if db.get(BacktestRun, run_id) is None:
        raise NotFound("Backtest run")
    res = bt.run_results(db, run_id)
    return S.BacktestDetail(run=S.BacktestRunOut.model_validate(res["run"]), projects=res["projects"])
