"""The ONLY write path for tasks/modules. Every change is diffed and logged to `edit_events` in the same
transaction. Functions here never commit; the caller owns the transaction (atomicity)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError, Conflict, NotFound
from app.db.models import EditEvent, Estimate, Module, Task, TaskAIBaseline


@dataclass(frozen=True)
class Actor:
    kind: str = "user"  # user | agent | system
    user_id: uuid.UUID | None = None
    proposal_id: uuid.UUID | None = None
    operation_id: uuid.UUID | None = None
    batch_id: uuid.UUID | None = None
    session_id: uuid.UUID | None = None


SYSTEM = Actor("system")

TASK_FIELDS = {"title", "description", "category_id", "delivery_role_id", "min_hours", "max_hours", "enabled",
               "module_id", "position", "confidence", "rationale"}


def _j(v: Any) -> Any:
    return str(v) if isinstance(v, uuid.UUID) else v


def log_event(db: Session, estimate_id: uuid.UUID, actor: Actor, event_type: str, *, task_id=None, module_id=None,
              field: str | None = None, old: Any = None, new: Any = None, reason_tag: str | None = None,
              reason_text: str | None = None) -> EditEvent:
    ev = EditEvent(estimate_id=estimate_id, task_id=task_id, module_id=module_id, user_id=actor.user_id,
                   actor=actor.kind, event_type=event_type, field=field, old_value=old, new_value=new,
                   reason_tag=reason_tag, reason_text=reason_text, proposal_id=actor.proposal_id,
                   operation_id=actor.operation_id, batch_id=actor.batch_id, session_id=actor.session_id)
    db.add(ev)
    if task_id is not None and event_type != "task_added":
        t = db.get(Task, task_id)
        if t is not None:
            t.row_version = (t.row_version or 1) + 1
    return ev


def check_version(t: Task, expected: int | None) -> None:
    """Optimistic concurrency: reject writes based on a stale read."""
    if expected is not None and expected != t.row_version:
        raise Conflict(f"Task '{t.title}' changed since it was read (version {t.row_version}, expected {expected})")


def get_estimate(db: Session, estimate_id: uuid.UUID) -> Estimate:
    est = db.get(Estimate, estimate_id)
    if est is None:
        raise NotFound("Estimate")
    return est


def ensure_draft(db: Session, estimate_id: uuid.UUID) -> Estimate:
    est = get_estimate(db, estimate_id)
    if est.status != "draft":
        raise Conflict("Estimate is final; clone it to make changes")
    return est


def get_task(db: Session, task_id: uuid.UUID) -> Task:
    t = db.get(Task, task_id)
    if t is None:
        raise NotFound("Task")
    return t


def _task_snapshot(t: Task) -> dict:
    return {"title": t.title, "module_id": str(t.module_id), "category_id": _j(t.category_id),
            "delivery_role_id": _j(t.delivery_role_id), "min_hours": t.min_hours, "max_hours": t.max_hours}


def create_module(db: Session, estimate_id: uuid.UUID, name: str, actor: Actor, description: str = "",
                  log: bool = True) -> Module:
    ensure_draft(db, estimate_id)
    pos = db.scalar(select(func.coalesce(func.max(Module.position), -1)).where(Module.estimate_id == estimate_id)) + 1
    m = Module(id=uuid.uuid4(), estimate_id=estimate_id, name=name, description=description, position=pos)
    db.add(m)
    db.flush()
    if log:
        log_event(db, estimate_id, actor, "module_added", module_id=m.id, new={"name": name})
    return m


def remove_module(db: Session, module_id: uuid.UUID, actor: Actor) -> Module:
    m = db.get(Module, module_id)
    if m is None:
        raise NotFound("Module")
    ensure_draft(db, m.estimate_id)
    if not m.removed:
        m.removed = True
        log_event(db, m.estimate_id, actor, "module_removed", module_id=m.id, old={"name": m.name})
        for t in db.scalars(select(Task).where(Task.module_id == m.id, Task.removed.is_(False))):
            remove_task(db, t.id, actor, reason_text="module removed")
    return m


def restore_module(db: Session, module_id: uuid.UUID, actor: Actor) -> Module:
    m = db.get(Module, module_id)
    if m is None:
        raise NotFound("Module")
    ensure_draft(db, m.estimate_id)
    if m.removed:
        m.removed = False
        log_event(db, m.estimate_id, actor, "module_restored", module_id=m.id, new={"name": m.name})
    return m


def rename_module(db: Session, module_id: uuid.UUID, name: str, actor: Actor) -> Module:
    m = db.get(Module, module_id)
    if m is None:
        raise NotFound("Module")
    ensure_draft(db, m.estimate_id)
    if name != m.name:
        log_event(db, m.estimate_id, actor, "title_changed", module_id=m.id, field="module_name", old=m.name, new=name)
        m.name = name
    return m


def create_task(db: Session, estimate_id: uuid.UUID, data: dict, actor: Actor, *, origin: str | None = None,
                log: bool = True, reason_tag: str | None = None, reason_text: str | None = None) -> Task:
    ensure_draft(db, estimate_id)
    module = db.get(Module, data["module_id"])
    if module is None or module.estimate_id != estimate_id:
        raise AppError("invalid_module", "Module does not belong to this estimate", 422)
    lo, hi = float(data.get("min_hours", 0)), float(data.get("max_hours", 0))
    if lo < 0 or hi < lo:
        raise AppError("invalid_hours", "Require 0 <= min_hours <= max_hours", 422)
    pos = db.scalar(select(func.coalesce(func.max(Task.position), -1)).where(Task.module_id == module.id)) + 1
    t = Task(id=uuid.uuid4(), estimate_id=estimate_id, module_id=module.id, title=data["title"],
             description=data.get("description", ""), category_id=data.get("category_id"),
             delivery_role_id=data.get("delivery_role_id"), min_hours=lo, max_hours=hi, position=pos,
             confidence=data.get("confidence", "medium"), rationale=data.get("rationale", ""),
             origin=origin or ("agent" if actor.kind == "agent" else "user"), ai_key=data.get("ai_key"),
             source_chunk_ids=data.get("source_chunk_ids", []), embedding=data.get("embedding"))
    db.add(t)
    db.flush()
    if log:
        log_event(db, estimate_id, actor, "task_added", task_id=t.id, new=_task_snapshot(t),
                  reason_tag=reason_tag, reason_text=reason_text)
    return t


def update_task(db: Session, task_id: uuid.UUID, changes: dict, actor: Actor, *, reason_tag: str | None = None,
                reason_text: str | None = None, expected_version: int | None = None) -> Task:
    t = get_task(db, task_id)
    ensure_draft(db, t.estimate_id)
    check_version(t, expected_version)
    changes = {k: v for k, v in changes.items() if k in TASK_FIELDS and v is not None}
    new_min = float(changes.get("min_hours", t.min_hours))
    new_max = float(changes.get("max_hours", t.max_hours))
    if new_min < 0 or new_max < new_min:
        raise AppError("invalid_hours", "Require 0 <= min_hours <= max_hours", 422)
    if "module_id" in changes:
        m = db.get(Module, changes["module_id"])
        if m is None or m.estimate_id != t.estimate_id:
            raise AppError("invalid_module", "Module does not belong to this estimate", 422)

    ev = lambda et, **kw: log_event(db, t.estimate_id, actor, et, task_id=t.id, reason_tag=reason_tag,  # noqa: E731
                                    reason_text=reason_text, **kw)
    if new_min != t.min_hours or new_max != t.max_hours:
        ev("hours_changed", field="hours", old={"min": t.min_hours, "max": t.max_hours},
           new={"min": new_min, "max": new_max})
        t.min_hours, t.max_hours = new_min, new_max
    if "delivery_role_id" in changes and changes["delivery_role_id"] != t.delivery_role_id:
        ev("role_changed", field="delivery_role_id", old=_j(t.delivery_role_id), new=_j(changes["delivery_role_id"]))
        t.delivery_role_id = changes["delivery_role_id"]
    if "category_id" in changes and changes["category_id"] != t.category_id:
        ev("category_changed", field="category_id", old=_j(t.category_id), new=_j(changes["category_id"]))
        t.category_id = changes["category_id"]
    for f in ("title", "description", "confidence", "rationale"):
        if f in changes and changes[f] != getattr(t, f):
            ev("title_changed", field=f, old=getattr(t, f), new=changes[f])
            setattr(t, f, changes[f])
    if "enabled" in changes and bool(changes["enabled"]) != t.enabled:
        ev("task_toggled", field="enabled", old=t.enabled, new=bool(changes["enabled"]))
        t.enabled = bool(changes["enabled"])
    moved_module = "module_id" in changes and changes["module_id"] != t.module_id
    moved_pos = "position" in changes and changes["position"] != t.position
    if moved_module or moved_pos:
        ev("task_moved", field="position",
           old={"module_id": str(t.module_id), "position": t.position},
           new={"module_id": str(changes.get("module_id", t.module_id)), "position": changes.get("position", t.position)})
        t.module_id = changes.get("module_id", t.module_id)
        t.position = changes.get("position", t.position)
    db.flush()
    return t


def remove_task(db: Session, task_id: uuid.UUID, actor: Actor, *, reason_tag: str | None = None,
                reason_text: str | None = None) -> Task:
    t = get_task(db, task_id)
    ensure_draft(db, t.estimate_id)
    if not t.removed:
        t.removed = True
        log_event(db, t.estimate_id, actor, "task_removed", task_id=t.id, old=_task_snapshot(t),
                  reason_tag=reason_tag, reason_text=reason_text)
    return t


def restore_task(db: Session, task_id: uuid.UUID, actor: Actor) -> Task:
    t = get_task(db, task_id)
    ensure_draft(db, t.estimate_id)
    if t.removed:
        t.removed = False
        log_event(db, t.estimate_id, actor, "task_restored", task_id=t.id, new=_task_snapshot(t))
    return t


def reorder_tasks(db: Session, module_id: uuid.UUID, ordered_task_ids: list[uuid.UUID], actor: Actor) -> None:
    m = db.get(Module, module_id)
    if m is None:
        raise NotFound("Module")
    for pos, tid in enumerate(ordered_task_ids):
        t = get_task(db, tid)
        if t.estimate_id != m.estimate_id:
            raise AppError("invalid_task", "Task belongs to another estimate", 422)
        if t.module_id != module_id or t.position != pos:
            update_task(db, tid, {"module_id": module_id, "position": pos}, actor)


def baseline_for(db: Session, task_id: uuid.UUID) -> TaskAIBaseline | None:
    return db.scalar(select(TaskAIBaseline).where(TaskAIBaseline.task_id == task_id))


def is_effectively_included(t: Task, module_removed: bool) -> bool:
    return t.enabled and not t.removed and not module_removed


def clone_estimate(db: Session, estimate_id: uuid.UUID, user_id: uuid.UUID | None) -> Estimate:
    """New draft version with the same tasks; AI baselines are copied so learning stays anchored to raw output."""
    src = get_estimate(db, estimate_id)
    version = (db.scalar(select(func.max(Estimate.version)).where(Estimate.project_id == src.project_id)) or 0) + 1
    est = Estimate(project_id=src.project_id, version=version, status="draft", source="clone", model_key=src.model_key,
                   learning_enabled=src.learning_enabled, model_snapshot=src.model_snapshot, summary=src.summary,
                   created_by=user_id, parent_estimate_id=src.id)
    db.add(est)
    db.flush()
    mod_map: dict[uuid.UUID, uuid.UUID] = {}
    for m in db.scalars(select(Module).where(Module.estimate_id == src.id)):
        nm = Module(id=uuid.uuid4(), estimate_id=est.id, name=m.name, description=m.description, position=m.position,
                    removed=m.removed)
        db.add(nm)
        mod_map[m.id] = nm.id
    db.flush()
    baselines = {b.task_id: b for b in db.scalars(select(TaskAIBaseline).where(TaskAIBaseline.estimate_id == src.id))}
    for t in db.scalars(select(Task).where(Task.estimate_id == src.id)):
        nt = Task(id=uuid.uuid4(), estimate_id=est.id, module_id=mod_map[t.module_id], title=t.title,
                  description=t.description, category_id=t.category_id, delivery_role_id=t.delivery_role_id,
                  min_hours=t.min_hours, max_hours=t.max_hours, position=t.position, enabled=t.enabled,
                  removed=t.removed, confidence=t.confidence, rationale=t.rationale,
                  source_chunk_ids=t.source_chunk_ids, origin=t.origin, ai_key=t.ai_key, embedding=t.embedding)
        db.add(nt)
        db.flush()
        b = baselines.get(t.id)
        if b:
            db.add(TaskAIBaseline(task_id=nt.id, estimate_id=est.id, ai_key=b.ai_key, raw_min=b.raw_min,
                                  raw_max=b.raw_max, analog_mid=b.analog_mid, analog_task_ids=b.analog_task_ids,
                                  calibrated_min=b.calibrated_min, calibrated_max=b.calibrated_max,
                                  applied_factor=b.applied_factor, shown_min=b.shown_min, shown_max=b.shown_max,
                                  category_key=b.category_key, provenance=b.provenance,
                                  prompt_version=b.prompt_version, model=b.model, model_key=b.model_key))
    db.flush()
    return est
