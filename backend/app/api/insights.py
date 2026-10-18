import uuid

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user_id
from app.core.errors import NotFound
from app.db.models import BacktestRun, LearnedRule
from app.db.session import get_db
from app.schemas import api as S
from app.services import backtest as bt
from app.services import insights, jobs
from app.services.learning import propose_lessons, recompute

router = APIRouter(tags=["insights"])


@router.get("/insights/calibration")
def calibration(db: Session = Depends(get_db)) -> list[dict]:
    return insights.calibration_overview(db)


@router.get("/insights/timeline")
def timeline(db: Session = Depends(get_db)) -> list[dict]:
    return insights.timeline(db)


@router.get("/insights/accuracy")
def accuracy(db: Session = Depends(get_db)) -> list[dict]:
    return insights.accuracy_over_time(db)


@router.get("/insights/structural")
def structural(db: Session = Depends(get_db)) -> dict:
    return insights.structural(db)


@router.post("/insights/recompute", status_code=204)
def manual_recompute(db: Session = Depends(get_db)):
    recompute(db, "manual")
    db.commit()


@router.get("/rules", response_model=list[S.RuleOut])
def list_rules(db: Session = Depends(get_db)):
    return list(db.scalars(select(LearnedRule).order_by(LearnedRule.status, LearnedRule.evidence_count.desc())))


@router.post("/rules/propose", response_model=list[S.RuleOut])
def propose(db: Session = Depends(get_db)):
    rules = propose_lessons(db)
    db.commit()
    return rules


@router.post("/rules/{rule_id}/status", response_model=S.RuleOut)
def set_rule_status(rule_id: uuid.UUID, body: S.RuleStatusIn, db: Session = Depends(get_db), uid=Depends(current_user_id)):
    r = db.get(LearnedRule, rule_id)
    if r is None:
        raise NotFound("Rule")
    r.status = body.status
    if body.status == "active":
        r.approved_by = uid
    db.commit()
    return r


# ---- backtest ----
@router.post("/backtest", response_model=S.JobOut, status_code=202)
def start_backtest(body: S.BacktestIn, bg: BackgroundTasks, db: Session = Depends(get_db)):
    job = jobs.create_job(db, "backtest")
    bg.add_task(jobs.run_job, job.id, lambda s, progress: str(bt.run_backtest(s, body.model_dump(), progress).id))
    return job


@router.get("/backtest/runs", response_model=list[S.BacktestRunOut])
def list_runs(db: Session = Depends(get_db)):
    return list(db.scalars(select(BacktestRun).order_by(BacktestRun.created_at.desc()).limit(20)))


@router.get("/backtest/runs/{run_id}", response_model=S.BacktestDetail)
def get_run(run_id: uuid.UUID, db: Session = Depends(get_db)):
    if db.get(BacktestRun, run_id) is None:
        raise NotFound("Backtest run")
    res = bt.run_results(db, run_id)
    return S.BacktestDetail(run=S.BacktestRunOut.model_validate(res["run"]), projects=res["projects"])
