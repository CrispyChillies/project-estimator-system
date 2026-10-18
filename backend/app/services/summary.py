"""Estimate summary: totals, cost, Monte Carlo P10..P90."""

from __future__ import annotations

import uuid
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import DeliveryRole, Estimate, Module, Task, TaskAIBaseline
from app.services import estimates as es
from app.services.calibration import mid, raw_sigma
from app.services.learning import load_stats
from app.services.reference import category_maps
from app.services.settings import get_params
from app.services.simulation import SimTask, simulate


def compute_summary(db: Session, estimate_id: uuid.UUID, *, persist: bool = True) -> dict:
    est = es.get_estimate(db, estimate_id)
    p = get_params(db)
    id2cat, _ = category_maps(db)
    modules = {m.id: m for m in db.scalars(select(Module).where(Module.estimate_id == estimate_id))}
    roles = {r.id: r for r in db.scalars(select(DeliveryRole))}
    baselines = {b.task_id: b for b in db.scalars(select(TaskAIBaseline).where(TaskAIBaseline.estimate_id == estimate_id))}
    tasks = [t for t in db.scalars(select(Task).where(Task.estimate_id == estimate_id))
             if es.is_effectively_included(t, modules[t.module_id].removed)]
    by_module: dict[str, dict] = defaultdict(lambda: {"min": 0.0, "max": 0.0, "mid": 0.0, "cost": 0.0})
    by_role: dict[str, dict] = defaultdict(lambda: {"min": 0.0, "max": 0.0, "mid": 0.0, "cost": 0.0})
    sim_tasks = []
    total_cost = 0.0
    currency = "EUR"
    for t in tasks:
        m = mid(t.min_hours, t.max_hours)
        role = roles.get(t.delivery_role_id)
        rate = role.hourly_rate if role else 0.0
        currency = role.currency if role else currency
        for bucket, key in ((by_module, modules[t.module_id].name), (by_role, role.name if role else "Unassigned")):
            bucket[key]["min"] += t.min_hours
            bucket[key]["max"] += t.max_hours
            bucket[key]["mid"] += m
            bucket[key]["cost"] += m * rate
        total_cost += m * rate
        b = baselines.get(t.id)
        cal = (b.provenance or {}).get("calibration") if b else None
        sigma = cal["sigma"] if cal and cal.get("sigma") else raw_sigma(t.min_hours, t.max_hours, p)
        sim_tasks.append(SimTask(mid=m, category=id2cat.get(t.category_id, "other"), sigma=sigma))
    _, actual = load_stats(db)
    sim = simulate(sim_tasks, actual, p, seed=int(uuid.UUID(str(estimate_id)).int % 2**31))
    summary = {
        "total_min": sum(t.min_hours for t in tasks), "total_max": sum(t.max_hours for t in tasks),
        "total_mid": sum(mid(t.min_hours, t.max_hours) for t in tasks), "task_count": len(tasks),
        "total_cost_mid": total_cost, "currency": currency,
        "by_module": [{"name": k, **v} for k, v in by_module.items()],
        "by_role": [{"name": k, **v} for k, v in by_role.items()],
        "simulation": sim,
    }
    if persist:
        est.summary = summary
        db.flush()
    return summary


def ensure_summary(db: Session, est: Estimate) -> dict:
    return est.summary if est.summary and "simulation" in est.summary else compute_summary(db, est.id)
