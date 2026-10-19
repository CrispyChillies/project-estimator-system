"""Read models (no writes): estimate tree, project list, compare, activity."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    EditEvent,
    Estimate,
    Module,
    Project,
    Task,
    TaskActual,
    TaskAIBaseline,
    TaskCategory,
    User,
)
from app.schemas import api as S
from app.services import estimates as es
from app.services.calibration import mid
from app.services.learning import latest_final_estimates


def estimate_tree(db: Session, estimate_id: uuid.UUID) -> S.EstimateTree:
    est = es.get_estimate(db, estimate_id)
    modules = list(db.scalars(select(Module).where(Module.estimate_id == estimate_id).order_by(Module.position)))
    tasks = list(db.scalars(select(Task).where(Task.estimate_id == estimate_id).order_by(Task.position)))
    baselines = {b.task_id: b for b in db.scalars(select(TaskAIBaseline).where(TaskAIBaseline.estimate_id == estimate_id))}
    actuals = {a.task_id: a.actual_hours for a in db.scalars(select(TaskActual).where(
        TaskActual.task_id.in_([t.id for t in tasks])))}
    counts = dict(db.execute(select(EditEvent.task_id, func.count()).where(EditEvent.estimate_id == estimate_id)
                             .group_by(EditEvent.task_id)).all())
    out_modules = []
    for m in modules:
        mo = S.ModuleOut.model_validate(m)
        for t in tasks:
            if t.module_id != m.id:
                continue
            b = baselines.get(t.id)
            to = S.TaskOut.model_validate(t)
            if b:
                to.baseline = S.BaselineOut.model_validate(b)
                base_mid = mid(b.shown_min, b.shown_max)
                cur = mid(t.min_hours, t.max_hours)
                to.delta_pct = round((cur / base_mid - 1) * 100, 1) if base_mid > 0 and abs(cur - base_mid) > 1e-9 else None
            to.actual_hours = actuals.get(t.id)
            to.comment_count = counts.get(t.id, 0)
            mo.tasks.append(to)
        out_modules.append(mo)
    return S.EstimateTree(estimate=S.EstimateOut.model_validate(est), modules=out_modules)


def project_list(db: Session, status: str | None, search: str | None,
                 visible: list[uuid.UUID] | None = None) -> list[S.ProjectListItem]:
    q = select(Project).order_by(Project.created_at.desc())
    if visible is not None:
        q = q.where(Project.id.in_(visible))
    if status:
        q = q.where(Project.status == status)
    if search:
        like = f"%{search.lower()}%"
        q = q.where(func.lower(Project.name).like(like) | func.lower(Project.client_name).like(like))
    projects = list(db.scalars(q))
    ids = [p.id for p in projects]
    finals = latest_final_estimates(db, ids)
    latest: dict[uuid.UUID, Estimate] = {}
    counts: dict[uuid.UUID, int] = {}
    for e in db.scalars(select(Estimate).where(Estimate.project_id.in_(ids)).order_by(Estimate.version)):
        latest[e.project_id] = e
        counts[e.project_id] = counts.get(e.project_id, 0) + 1
    final_ids = [e.id for e in finals.values()]
    sums: dict[uuid.UUID, tuple[float, float]] = {}
    if final_ids:
        rows = db.execute(
            select(Task.estimate_id, func.sum((Task.min_hours + Task.max_hours) / 2),
                   func.sum(TaskActual.actual_hours))
            .join(Module, Module.id == Task.module_id)
            .outerjoin(TaskActual, TaskActual.task_id == Task.id)
            .where(Task.estimate_id.in_(final_ids), Task.enabled.is_(True), Task.removed.is_(False),
                   Module.removed.is_(False))
            .group_by(Task.estimate_id))
        sums = {eid: (fm or 0.0, act or 0.0) for eid, fm, act in rows}
    out = []
    for p in projects:
        item = S.ProjectListItem.model_validate(p)
        e = finals.get(p.id) or latest.get(p.id)
        item.estimate_count = counts.get(p.id, 0)
        if e is not None:
            sim = (e.summary or {}).get("simulation") or {}
            item.p50_hours, item.p80_hours = sim.get("p50"), sim.get("p80")
        if p.id in finals:
            fm, act = sums.get(finals[p.id].id, (None, None))
            item.final_mid_hours = fm
            item.actual_hours = act or None
            if fm and act:
                item.accuracy_pct = round(100 * (1 - abs(fm - act) / act), 1)
        out.append(item)
    return out


def compare(db: Session, a_id: uuid.UUID, b_id: uuid.UUID) -> S.CompareOut:
    a, b = es.get_estimate(db, a_id), es.get_estimate(db, b_id)
    cats = {c.id: c.key for c in db.scalars(select(TaskCategory))}

    def rows(eid):
        res = {}
        for t, bl in db.execute(select(Task, TaskAIBaseline).outerjoin(TaskAIBaseline, TaskAIBaseline.task_id == Task.id)
                                .where(Task.estimate_id == eid, Task.removed.is_(False))):
            res[t.ai_key or str(t.id)] = (t, bl)
        return res

    ra, rb = rows(a_id), rows(b_id)
    out = []
    for key in list(dict.fromkeys([*ra, *rb])):
        ta, tb = ra.get(key, (None, None)), rb.get(key, (None, None))
        t = ta[0] or tb[0]
        out.append(S.CompareRow(
            ai_key=key, title=t.title, category=cats.get(t.category_id),
            a_min=ta[0].min_hours if ta[0] else None, a_max=ta[0].max_hours if ta[0] else None,
            b_min=tb[0].min_hours if tb[0] else None, b_max=tb[0].max_hours if tb[0] else None,
            factor=tb[1].applied_factor if tb[1] else None,
        ))
    return S.CompareOut(a=S.EstimateOut.model_validate(a), b=S.EstimateOut.model_validate(b), rows=out)


def activity(db: Session, estimate_id: uuid.UUID, actor: str | None) -> list[S.EditEventOut]:
    q = (select(EditEvent, Task.title, User.name).outerjoin(Task, Task.id == EditEvent.task_id)
         .outerjoin(User, User.id == EditEvent.user_id)
         .where(EditEvent.estimate_id == estimate_id).order_by(EditEvent.created_at.desc()).limit(500))
    if actor:
        q = q.where(EditEvent.actor == actor)
    out = []
    for ev, title, uname in db.execute(q):
        o = S.EditEventOut.model_validate(ev)
        o.task_title, o.user_name = title, uname
        out.append(o)
    return out
