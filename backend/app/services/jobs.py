import logging
import traceback
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.errors import NotFound
from app.db.models import Job
from app.db.session import SessionLocal

log = logging.getLogger(__name__)

Progress = Callable[[float, str], None]


def create_job(db: Session, kind: str) -> Job:
    job = Job(kind=kind, status="queued", progress=0.0)
    db.add(job)
    db.commit()
    return job


def get_job(db: Session, job_id: uuid.UUID) -> Job:
    job = db.get(Job, job_id)
    if job is None:
        raise NotFound("Job")
    return job


def _update(job_id: uuid.UUID, **kw: object) -> None:
    with SessionLocal() as s:
        job = s.get(Job, job_id)
        if job:
            for k, v in kw.items():
                setattr(job, k, v)
            s.commit()


def run_job(job_id: uuid.UUID, fn: Callable[[Session, Progress], str | None]) -> None:
    """Executes `fn(db, progress)` in its own session; result is a reference string (e.g. an id)."""
    _update(job_id, status="running", progress=0.01)
    with SessionLocal() as db:
        try:
            ref = fn(db, lambda p, msg="": _update(job_id, progress=float(min(max(p, 0), 0.99)), message=msg))
            db.commit()
            _update(job_id, status="done", progress=1.0, result_ref=ref, finished_at=datetime.now(UTC))
        except Exception as e:
            db.rollback()
            log.error("job failed", extra={"extra": {"job_id": str(job_id), "trace": traceback.format_exc()}})
            msg = getattr(e, "message", None) or f"{type(e).__name__}: {e}"
            _update(job_id, status="failed", error=str(msg)[:2000], finished_at=datetime.now(UTC))
