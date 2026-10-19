"""AI estimates for tasks a PM (or the agent) added to an estimate: same pipeline as generation, restricted to those tasks."""

from __future__ import annotations

import uuid
from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents import chains
from app.agents import templates as T
from app.db.models import Estimate, Project, Task, TaskAIBaseline
from app.llm.gateway import get_gateway
from app.prompts import PROMPT_VERSIONS
from app.services import estimates as es
from app.services.calibration import predict_task
from app.services.learning import active_rules, load_stats
from app.services.reference import category_maps, role_maps
from app.services.retrieval import find_analogs
from app.services.settings import get_params

Progress = Callable[[float, str], None]


def pending_task_ids(db: Session, estimate_id: uuid.UUID, task_ids: list[uuid.UUID] | None = None) -> list[uuid.UUID]:
    """Tasks without an AI baseline. Without explicit ids: only added tasks that still have 0/0 hours."""
    has_baseline = set(db.scalars(select(TaskAIBaseline.task_id).where(TaskAIBaseline.estimate_id == estimate_id)))
    q = select(Task).where(Task.estimate_id == estimate_id, Task.removed.is_(False), Task.enabled.is_(True))
    if task_ids:
        q = q.where(Task.id.in_(task_ids))
    else:
        q = q.where(Task.origin != "ai", Task.min_hours == 0, Task.max_hours == 0)
    return [t.id for t in db.scalars(q.order_by(Task.created_at)) if t.id not in has_baseline]


def estimate_added_tasks(db: Session, estimate_id: uuid.UUID, task_ids: list[uuid.UUID], user_id: uuid.UUID | None,
                         progress: Progress) -> str:
    est: Estimate = es.ensure_draft(db, estimate_id)
    project = db.get(Project, est.project_id)
    gw = get_gateway()
    p = get_params(db)
    id2cat, cat2id = category_maps(db)
    id2role, role2id = role_maps(db)
    tasks = [db.get(Task, tid) for tid in task_ids]
    tasks = [t for t in tasks if t is not None and t.estimate_id == estimate_id]

    progress(0.1, f"Preparing {len(tasks)} task(s)")
    from app.core.access import pool_project_ids

    pool = pool_project_ids(db, user_id)
    rules = [r.text for r in active_rules(db, user_id)] if est.learning_enabled else []
    items = []
    for i, t in enumerate(tasks):
        cat = id2cat.get(t.category_id) if t.category_id else None
        cat = cat or T.classify(f"{t.title} {t.description}")
        role = id2role.get(t.delivery_role_id) if t.delivery_role_id else None
        role = role or T.CATEGORY_INFO.get(cat, T.CATEGORY_INFO["other"])["role"]
        items.append({"key": f"t{i + 1}", "title": t.title, "description": t.description or t.title,
                      "category_key": cat, "role_name": role})
        changes = {}
        if t.category_id is None and cat in cat2id:
            changes["category_id"] = cat2id[cat]
        if t.delivery_role_id is None and role in role2id:
            changes["delivery_role_id"] = role2id[role]
        if changes:
            es.update_task(db, t.id, changes, es.SYSTEM)

    progress(0.3, f"Estimating hours ({p.raw_samples} samples)")
    summary = (est.model_snapshot or {}).get("summary") or (project.name if project else "")
    raw, samples = chains.run_estimation(items, summary, rules, p.raw_samples)

    progress(0.7, "Retrieving analogs and calibrating")
    vectors = gw.embed([f"{it['title']}\n{it['description']}" for it in items])
    edit_stats, actual_stats = load_stats(db, pool) if est.learning_enabled else ({}, {})
    author = str(user_id) if user_id else None
    for t, it, vec in zip(tasks, items, vectors, strict=True):
        rmin, rmax = raw[it["key"]]
        analogs = find_analogs(db, vec, it["category_key"], exclude_project_id=est.project_id, top_k=p.analog_top_k,
                               allowed_project_ids=pool) \
            if est.learning_enabled else []
        pred = predict_task(rmin, rmax, it["category_key"], author, analogs, edit_stats, actual_stats, p,
                            learning=est.learning_enabled)
        key = f"added_{t.id.hex[:12]}"
        es.update_task(db, t.id, {"min_hours": pred.min_hours, "max_hours": pred.max_hours}, es.SYSTEM,
                       reason_text="AI estimate for added task")
        t.embedding = vec
        t.ai_key = key
        t.rationale = t.rationale or "AI estimate for a task added by the PM."
        db.add(TaskAIBaseline(
            task_id=t.id, estimate_id=estimate_id, ai_key=key, raw_min=rmin, raw_max=rmax, analog_mid=pred.analog_mid,
            analog_task_ids=[uuid.UUID(a.task_id) for a in pred.analogs_used],
            calibrated_min=pred.min_hours if est.learning_enabled else None,
            calibrated_max=pred.max_hours if est.learning_enabled else None, applied_factor=pred.applied_factor,
            shown_min=pred.min_hours, shown_max=pred.max_hours, category_key=it["category_key"],
            provenance={"raw": {"min": rmin, "max": rmax, "samples": [list(s) for s in samples[it["key"]]]},
                        "analogs": [a.to_dict() for a in pred.analogs_used], "analog_mid": pred.analog_mid,
                        "blend_weight": pred.blend_weight,
                        "calibration": pred.calibration.to_dict() if pred.calibration else None,
                        "source_chunk_ids": [], "rules_applied": [], "learning": est.learning_enabled,
                        "added_by_pm": True},
            prompt_version=PROMPT_VERSIONS["estimation"], model=gw.model, model_key=gw.model_key))
    db.flush()
    from app.services.summary import compute_summary

    compute_summary(db, estimate_id)
    progress(0.98, "Done")
    return str(estimate_id)
