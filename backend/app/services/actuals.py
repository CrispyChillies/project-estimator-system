"""Actual hours (manual / CSV), unplanned work and the post-delivery accuracy summary."""

from __future__ import annotations

import csv
import io
import math
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError, NotFound
from app.db.models import Module, Project, Task, TaskActual, UnplannedActual
from app.services import estimates as es
from app.services.calibration import mid
from app.services.learning import latest_final_estimates

CSV_COLUMNS = ["task_id", "module", "title", "estimate_min", "estimate_max", "actual_hours", "note"]


def final_estimate_id(db: Session, project_id: uuid.UUID) -> uuid.UUID:
    finals = latest_final_estimates(db, [project_id])
    if project_id not in finals:
        raise AppError("no_final_estimate", "Finalize an estimate first", 409)
    return finals[project_id].id


def final_tasks(db: Session, project_id: uuid.UUID) -> list[tuple[Task, Module, TaskActual | None]]:
    eid = final_estimate_id(db, project_id)
    rows = db.execute(select(Task, Module, TaskActual).join(Module, Module.id == Task.module_id)
                      .outerjoin(TaskActual, TaskActual.task_id == Task.id)
                      .where(Task.estimate_id == eid).order_by(Module.position, Task.position))
    return [(t, m, a) for t, m, a in rows if es.is_effectively_included(t, m.removed)]


def upsert_actual(db: Session, project_id: uuid.UUID, task_id: uuid.UUID, hours: float, user_id: uuid.UUID | None,
                  source: str = "manual", note: str = "") -> TaskActual:
    if hours is None or not math.isfinite(hours) or hours < 0 or hours > 100_000:
        raise AppError("invalid_hours", "actual_hours must be between 0 and 100000", 422)
    t = db.get(Task, task_id)
    if t is None or t.estimate_id != final_estimate_id(db, project_id):
        raise NotFound("Task in final estimate")
    a = db.scalar(select(TaskActual).where(TaskActual.task_id == task_id))
    if a is None:
        a = TaskActual(task_id=task_id, actual_hours=hours, source=source, recorded_by=user_id, note=note)
        db.add(a)
    else:
        a.actual_hours, a.source, a.recorded_by, a.note = hours, source, user_id, note or a.note
    db.flush()
    return a


def csv_template(db: Session, project_id: uuid.UUID) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(CSV_COLUMNS)
    for t, m, a in final_tasks(db, project_id):
        w.writerow([t.id, m.name, t.title, t.min_hours, t.max_hours, a.actual_hours if a else "", a.note if a else ""])
    return buf.getvalue()


def import_csv(db: Session, project_id: uuid.UUID, content: bytes, user_id: uuid.UUID | None) -> dict:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        raise AppError("invalid_csv", "CSV must be UTF-8", 422) from e
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or "actual_hours" not in reader.fieldnames or (
            "task_id" not in reader.fieldnames and "title" not in reader.fieldnames):
        raise AppError("invalid_csv", "CSV needs columns actual_hours and task_id (or title)", 422)
    tasks = final_tasks(db, project_id)
    by_id = {str(t.id): t for t, _, _ in tasks}
    by_title = {t.title.strip().lower(): t for t, _, _ in tasks}
    errors: list[dict] = []
    rows: list[tuple[Task, float, str]] = []
    for i, row in enumerate(reader, start=2):
        raw = (row.get("actual_hours") or "").strip()
        if raw == "":
            continue
        try:
            hours = float(raw)
            if not math.isfinite(hours) or hours < 0:
                raise ValueError
        except ValueError:
            errors.append({"line": i, "error": f"invalid actual_hours '{raw[:20]}'"})
            continue
        t = by_id.get((row.get("task_id") or "").strip()) or by_title.get((row.get("title") or "").strip().lower())
        if t is None:
            errors.append({"line": i, "error": "unknown task"})
            continue
        rows.append((t, hours, (row.get("note") or "")[:500]))
    if errors:
        raise AppError("invalid_csv", f"{len(errors)} invalid row(s); nothing imported", 422, errors[:50])
    for t, h, note in rows:
        upsert_actual(db, project_id, t.id, h, user_id, "csv", note)
    return {"imported": len(rows)}


def add_unplanned(db: Session, project_id: uuid.UUID, title: str, hours: float, category_id: uuid.UUID | None,
                  note: str = "", reason: str = "unspecified") -> UnplannedActual:
    if db.get(Project, project_id) is None:
        raise NotFound("Project")
    if hours <= 0:
        raise AppError("invalid_hours", "hours must be > 0", 422)
    u = UnplannedActual(project_id=project_id, title=title, hours=hours, category_id=category_id, note=note,
                        reason=reason)
    db.add(u)
    db.flush()
    return u


def accuracy(db: Session, project_id: uuid.UUID) -> dict:
    eid = final_estimate_id(db, project_id)
    est = es.get_estimate(db, eid)
    tasks = final_tasks(db, project_id)
    with_actual = [(t, a) for t, _, a in tasks if a]
    planned_actual = sum(a.actual_hours for _, a in with_actual)
    est_mid = sum(mid(t.min_hours, t.max_hours) for t, _ in with_actual)
    unplanned = sum(u.hours for u in db.scalars(select(UnplannedActual).where(UnplannedActual.project_id == project_id)))
    sim = (est.summary or {}).get("simulation", {})
    apes = [abs(mid(t.min_hours, t.max_hours) - a.actual_hours) / a.actual_hours for t, a in with_actual if a.actual_hours > 0]
    in_range = sum(1 for t, a in with_actual if t.min_hours <= a.actual_hours <= t.max_hours)
    return {
        "estimate_id": str(eid), "tasks_total": len(tasks), "tasks_with_actuals": len(with_actual),
        "estimate_mid_for_tasks_with_actuals": est_mid, "planned_actual_hours": planned_actual,
        "unplanned_hours": unplanned, "total_actual_hours": planned_actual + unplanned,
        "unplanned_share": unplanned / (planned_actual + unplanned) if planned_actual + unplanned else None,
        "p50": sim.get("p50"), "p80": sim.get("p80"),
        "within_p80": (planned_actual <= sim["p80"]) if sim.get("p80") and len(with_actual) == len(tasks) else None,
        "project_ape": abs(est_mid - planned_actual) / planned_actual if planned_actual else None,
        "task_mdape": sorted(apes)[len(apes) // 2] if apes else None,
        "task_in_range_share": in_range / len(with_actual) if with_actual else None,
    }
