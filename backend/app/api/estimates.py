import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user_id
from app.core.errors import AppError
from app.db.models import Assumption, Estimate
from app.db.session import get_db
from app.schemas import api as S
from app.services import added_tasks, exports, jobs, sensitivity
from app.services import estimates as es
from app.services.generation import generate
from app.services.learning import finalize_estimate
from app.services.summary import compute_summary, ensure_summary
from app.services.views import activity, compare, estimate_tree

router = APIRouter(tags=["estimates"])


def _actor(uid) -> es.Actor:
    return es.Actor("user", uid)


def _done(db: Session, estimate_id: uuid.UUID) -> None:
    compute_summary(db, estimate_id)
    db.commit()


@router.post("/projects/{project_id}/estimates/generate", response_model=S.JobOut, status_code=202)
def start_generation(project_id: uuid.UUID, body: S.GenerateIn, bg: BackgroundTasks, db: Session = Depends(get_db),
                     uid=Depends(current_user_id)):
    job = jobs.create_job(db, "generate_estimate")

    def work(s: Session, progress):
        est = generate(s, project_id, body.document_ids, body.learning, uid, progress)
        return str(est.id)

    bg.add_task(jobs.run_job, job.id, work)
    return job


@router.get("/projects/{project_id}/estimates", response_model=list[S.EstimateOut])
def list_estimates(project_id: uuid.UUID, db: Session = Depends(get_db)):
    return list(db.scalars(select(Estimate).where(Estimate.project_id == project_id).order_by(Estimate.version.desc())))


@router.get("/estimates/{estimate_id}", response_model=S.EstimateTree)
def get_estimate(estimate_id: uuid.UUID, db: Session = Depends(get_db)):
    return estimate_tree(db, estimate_id)


@router.get("/estimates/{estimate_id}/summary")
def get_summary(estimate_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    s = ensure_summary(db, es.get_estimate(db, estimate_id))
    db.commit()
    return s


@router.get("/estimates/{estimate_id}/references")
def get_references(estimate_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    """References used when this estimate was generated (frozen in the snapshot)."""
    snap = es.get_estimate(db, estimate_id).model_snapshot or {}
    return {"retrieval": snap.get("retrieval"), "references": snap.get("reference_projects", [])}


@router.get("/estimates/{estimate_id}/similar-projects")
def similar_projects(estimate_id: uuid.UUID, k: int | None = Query(None, ge=0, le=10),
                     db: Session = Depends(get_db)) -> dict:
    """Live retrieval against the current state of the estimate (used by the agent and the References card)."""
    from app.db.models import Project
    from app.services import project_retrieval as pr
    from app.services.settings import get_params

    est = es.get_estimate(db, estimate_id)
    project = db.get(Project, est.project_id)
    card = pr.build_card(db, project, est)
    refs, err = pr.safe_retrieve(db, pr.card_text(card), get_params(db), exclude_project_id=project.id,
                                 tags=project.tech_tags, domain=project.domain, cat_share=card["category_share"],
                                 k=k, estimate_id=est.id)
    db.commit()
    return {"references": [r.to_dict() for r in refs], "error": err}


@router.get("/estimates/{estimate_id}/compare", response_model=S.CompareOut)
def compare_estimates(estimate_id: uuid.UUID, with_: uuid.UUID = Query(alias="with"), db: Session = Depends(get_db)):
    return compare(db, with_, estimate_id)


@router.post("/estimates/{estimate_id}/clone", response_model=S.EstimateOut, status_code=201)
def clone(estimate_id: uuid.UUID, db: Session = Depends(get_db), uid=Depends(current_user_id)):
    est = es.clone_estimate(db, estimate_id, uid)
    db.commit()
    return est


@router.post("/estimates/{estimate_id}/finalize", response_model=S.EstimateOut)
def finalize(estimate_id: uuid.UUID, db: Session = Depends(get_db), uid=Depends(current_user_id)):
    compute_summary(db, estimate_id)
    est = finalize_estimate(db, estimate_id, uid)
    db.commit()
    return est


@router.delete("/estimates/{estimate_id}", status_code=204)
def delete_estimate(estimate_id: uuid.UUID, db: Session = Depends(get_db)):
    est = es.ensure_draft(db, estimate_id)  # final estimates are history; never deleted
    db.delete(est)
    db.commit()


# ---- modules ----
@router.post("/estimates/{estimate_id}/modules", response_model=S.ModuleOut, status_code=201)
def add_module(estimate_id: uuid.UUID, body: S.ModuleCreate, db: Session = Depends(get_db), uid=Depends(current_user_id)):
    m = es.create_module(db, estimate_id, body.name, _actor(uid), body.description)
    db.commit()
    return m


@router.patch("/modules/{module_id}", response_model=S.ModuleOut)
def rename_module(module_id: uuid.UUID, body: S.ModulePatch, db: Session = Depends(get_db), uid=Depends(current_user_id)):
    m = es.rename_module(db, module_id, body.name, _actor(uid))
    db.commit()
    return m


@router.delete("/modules/{module_id}", response_model=S.ModuleOut)
def delete_module(module_id: uuid.UUID, db: Session = Depends(get_db), uid=Depends(current_user_id)):
    m = es.remove_module(db, module_id, _actor(uid))
    _done(db, m.estimate_id)
    return m


# ---- tasks ----
@router.post("/estimates/{estimate_id}/tasks", response_model=S.TaskOut, status_code=201)
def add_task(estimate_id: uuid.UUID, body: S.TaskCreate, db: Session = Depends(get_db), uid=Depends(current_user_id)):
    data = body.model_dump(exclude={"reason_tag", "reason_text"})
    t = es.create_task(db, estimate_id, data, _actor(uid), reason_tag=body.reason_tag, reason_text=body.reason_text)
    _done(db, estimate_id)
    return t


@router.patch("/tasks/{task_id}", response_model=S.TaskOut)
def patch_task(task_id: uuid.UUID, body: S.TaskPatch, db: Session = Depends(get_db), uid=Depends(current_user_id)):
    changes = body.model_dump(exclude_unset=True, exclude={"reason_tag", "reason_text"})
    t = es.update_task(db, task_id, changes, _actor(uid), reason_tag=body.reason_tag, reason_text=body.reason_text)
    _done(db, t.estimate_id)
    return t


@router.post("/tasks/{task_id}/reason", status_code=204)
def add_reason(task_id: uuid.UUID, body: S.ReasonIn, db: Session = Depends(get_db), uid=Depends(current_user_id)):
    """Attach a 'Why?' reason after the fact (non-blocking chips). Appends a new event; never edits old ones."""
    t = es.get_task(db, task_id)
    es.log_event(db, t.estimate_id, _actor(uid), "hours_changed", task_id=t.id, field="reason",
                 old=None, new={"min": t.min_hours, "max": t.max_hours}, reason_tag=body.reason_tag,
                 reason_text=body.reason_text)
    db.commit()


@router.delete("/tasks/{task_id}", response_model=S.TaskOut)
def delete_task(task_id: uuid.UUID, db: Session = Depends(get_db), uid=Depends(current_user_id)):
    t = es.remove_task(db, task_id, _actor(uid))
    _done(db, t.estimate_id)
    return t


@router.post("/tasks/{task_id}/restore", response_model=S.TaskOut)
def restore_task(task_id: uuid.UUID, db: Session = Depends(get_db), uid=Depends(current_user_id)):
    t = es.restore_task(db, task_id, _actor(uid))
    _done(db, t.estimate_id)
    return t


@router.post("/estimates/{estimate_id}/tasks/reorder", status_code=204)
def reorder(estimate_id: uuid.UUID, body: S.ReorderIn, db: Session = Depends(get_db), uid=Depends(current_user_id)):
    es.reorder_tasks(db, body.module_id, body.task_ids, _actor(uid))
    db.commit()


@router.post("/estimates/{estimate_id}/tasks/bulk", status_code=204)
def bulk(estimate_id: uuid.UUID, body: S.BulkIn, db: Session = Depends(get_db), uid=Depends(current_user_id)):
    from app.services.calibration import round_half

    for tid in body.task_ids:
        t = es.get_task(db, tid)
        changes: dict = {}
        if body.enabled is not None:
            changes["enabled"] = body.enabled
        if body.percent is not None:
            f = 1 + body.percent / 100
            changes["min_hours"] = max(0.25, round_half(t.min_hours * f))
            changes["max_hours"] = max(changes["min_hours"], round_half(t.max_hours * f))
        es.update_task(db, tid, changes, _actor(uid), reason_tag=body.reason_tag)
    _done(db, estimate_id)


@router.post("/estimates/{estimate_id}/tasks/estimate", response_model=S.JobOut, status_code=202)
def estimate_added(estimate_id: uuid.UUID, body: S.EstimateAddedIn, bg: BackgroundTasks, db: Session = Depends(get_db),
                   uid=Depends(current_user_id)):
    """Background AI estimate for added tasks (given ids, or every added task still at 0 h)."""
    es.ensure_draft(db, estimate_id)
    ids = added_tasks.pending_task_ids(db, estimate_id, body.task_ids)
    if not ids:
        raise AppError("nothing_to_estimate", "No added tasks need an AI estimate", 422)
    job = jobs.create_job(db, "estimate_added_tasks")
    bg.add_task(jobs.run_job, job.id, lambda s, progress: added_tasks.estimate_added_tasks(s, estimate_id, ids, uid, progress))
    return job


# ---- activity, questions, assumptions, export ----
@router.get("/estimates/{estimate_id}/activity", response_model=list[S.EditEventOut])
def get_activity(estimate_id: uuid.UUID, actor: str | None = None, db: Session = Depends(get_db)):
    return activity(db, estimate_id, actor)


@router.get("/estimates/{estimate_id}/questions", response_model=list[S.QuestionOut])
def list_questions(estimate_id: uuid.UUID, db: Session = Depends(get_db)):
    return sensitivity.list_questions(db, estimate_id)


@router.post("/questions/{question_id}/answer", response_model=S.AnswerOut)
def answer_question(question_id: uuid.UUID, body: S.AnswerIn, db: Session = Depends(get_db), uid=Depends(current_user_id)):
    q, prop = sensitivity.answer(db, question_id, body.answer, body.scenario_applies, uid)
    db.commit()
    return S.AnswerOut(question=S.QuestionOut.model_validate(q),
                       proposal=S.ProposalOut.model_validate(prop) if prop else None)


@router.post("/questions/{question_id}/dismiss", response_model=S.QuestionOut)
def dismiss_question(question_id: uuid.UUID, db: Session = Depends(get_db)):
    q = sensitivity.dismiss(db, question_id)
    db.commit()
    return q


@router.get("/estimates/{estimate_id}/assumptions", response_model=list[S.AssumptionOut])
def list_assumptions(estimate_id: uuid.UUID, db: Session = Depends(get_db)):
    return list(db.scalars(select(Assumption).where(Assumption.estimate_id == estimate_id)))


@router.get("/estimates/{estimate_id}/export")
def export(estimate_id: uuid.UUID, format: str = "xlsx", db: Session = Depends(get_db)):
    est = es.get_estimate(db, estimate_id)
    name = f"estimate-v{est.version}"
    if format == "csv":
        return Response(exports.to_csv(db, estimate_id), media_type="text/csv",
                        headers={"Content-Disposition": f'attachment; filename="{name}.csv"'})
    return Response(exports.to_xlsx(db, estimate_id),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{name}.xlsx"'})
