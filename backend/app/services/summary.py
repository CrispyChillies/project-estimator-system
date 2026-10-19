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
    def _bucket() -> dict:
        return {"min": 0.0, "max": 0.0, "mid": 0.0, "cost": 0.0, "roles": {}}

    by_module: dict[str, dict] = defaultdict(_bucket)
    by_role: dict[str, dict] = defaultdict(_bucket)
    role_ids: dict[str, str | None] = {}
    sim_tasks = []
    for t in tasks:
        m = mid(t.min_hours, t.max_hours)
        role = roles.get(t.delivery_role_id)
        rate = int(role.hourly_rate_vnd or 0) if role else 0
        rkey = role.name if role else "Unassigned"
        role_ids[rkey] = str(role.id) if role else None
        for bucket, key in ((by_module, modules[t.module_id].name), (by_role, rkey)):
            bucket[key]["min"] += t.min_hours
            bucket[key]["max"] += t.max_hours
            bucket[key]["mid"] += m
            bucket[key]["cost"] += m * rate
            rr = bucket[key]["roles"].setdefault(str(role.id) if role else "unassigned", {"min": 0.0, "max": 0.0})
            rr["min"] += t.min_hours
            rr["max"] += t.max_hours
        b = baselines.get(t.id)
        cal = (b.provenance or {}).get("calibration") if b else None
        sigma = cal["sigma"] if cal and cal.get("sigma") else raw_sigma(t.min_hours, t.max_hours, p)
        sim_tasks.append(SimTask(mid=m, category=id2cat.get(t.category_id, "other"), sigma=sigma))
    from app.core.access import pool_project_ids
    from app.db.models import Project

    owner = db.scalar(select(Project.owner_id).where(Project.id == est.project_id))
    _, actual = load_stats(db, pool_project_ids(db, owner))
    sim = simulate(sim_tasks, actual, p, seed=int(uuid.UUID(str(estimate_id)).int % 2**31))
    summary = {
        "total_min": sum(t.min_hours for t in tasks), "total_max": sum(t.max_hours for t in tasks),
        "total_mid": sum(mid(t.min_hours, t.max_hours) for t in tasks), "task_count": len(tasks),
        "currency": "VND", "cost_basis": 2,
        "by_module": [{"name": k, **v} for k, v in by_module.items()],
        "by_role": [{"name": k, "role_id": role_ids.get(k), **v} for k, v in by_role.items()],
        "simulation": sim,
    }
    summary.update(_totals(summary, {str(r.id): int(r.hourly_rate_vnd or 0) for r in roles.values()}))
    if persist:
        est.summary = summary
        db.flush()
    return summary


def _totals(summary: dict, rates: dict[str, int]) -> dict:
    """Cost range (VND) from per-role hours; mutates by_role/by_module costs to `rates`. Rate 0 for unassigned."""
    tot = {"total_cost_min": 0.0, "total_cost_mid": 0.0, "total_cost_max": 0.0}
    for r in summary["by_role"]:
        rate = rates.get(str(r.get("role_id")), 0)
        r["cost_min"], r["cost_max"], r["cost"] = r["min"] * rate, r["max"] * rate, r["mid"] * rate
        tot["total_cost_min"] += r["cost_min"]
        tot["total_cost_max"] += r["cost_max"]
        tot["total_cost_mid"] += r["cost"]
    for m in summary["by_module"]:
        m["cost_min"] = sum(v["min"] * rates.get(k, 0) for k, v in m["roles"].items())
        m["cost_max"] = sum(v["max"] * rates.get(k, 0) for k, v in m["roles"].items())
        m["cost"] = sum((v["min"] + v["max"]) / 2 * rates.get(k, 0) for k, v in m["roles"].items())
    return tot


def with_user_costs(db: Session, summary: dict, user) -> dict:
    """Copy of a stored summary with costs at this user's effective VND rates (own overrides, else workspace)."""
    import copy

    from app.services.rates import effective_rates

    out = copy.deepcopy(summary)
    out.update(_totals(out, {str(k): v for k, v in effective_rates(db, user).items()}))
    return out


def ensure_summary(db: Session, est: Estimate) -> dict:
    ok = est.summary and "simulation" in est.summary and est.summary.get("cost_basis") == 2
    return est.summary if ok else compute_summary(db, est.id)
