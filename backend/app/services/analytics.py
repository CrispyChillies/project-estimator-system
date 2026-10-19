"""Productivity & accuracy analytics for the Insights page. Everything is computed from the requesting user's pool
(their own + shared projects; everything for admins) and returns `n` plus an `enough` flag so the UI can show a
"not enough data" state instead of misleading numbers."""

from __future__ import annotations

import math
import statistics
import uuid
from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents.templates import CATEGORY_NAMES
from app.db.models import (
    DeliveryRole,
    Document,
    EditEvent,
    Estimate,
    Module,
    Project,
    Task,
    TaskActual,
    TaskAIBaseline,
    TaskCategory,
    UnplannedActual,
)
from app.services.calibration import mid

MIN_PROJECTS = 3
MIN_TASKS = 10
ROLLING = 5


def _ape(x: float | None, actual: float) -> float | None:
    return abs(x - actual) / actual if x is not None and actual > 0 else None


def _final_estimates(db: Session, pool: list[uuid.UUID] | None) -> dict[uuid.UUID, Estimate]:
    q = select(Estimate).where(Estimate.status == "final").order_by(Estimate.version)
    if pool is not None:
        q = q.where(Estimate.project_id.in_(pool))
    out: dict[uuid.UUID, Estimate] = {}
    for e in db.scalars(q):
        out[e.project_id] = e  # latest final version wins
    return out


def analytics(db: Session, pool: list[uuid.UUID] | None) -> dict:
    finals = _final_estimates(db, pool)
    projects = {p.id: p for p in db.scalars(select(Project).where(Project.id.in_(list(finals))))} if finals else {}
    est_ids = [e.id for e in finals.values()]
    cats = {c.id: c.key for c in db.scalars(select(TaskCategory))}
    roles = {r.id: r.name for r in db.scalars(select(DeliveryRole))}
    removed_mods = set(db.scalars(select(Module.id).where(Module.estimate_id.in_(est_ids), Module.removed))) \
        if est_ids else set()
    rows = list(db.execute(
        select(Task, TaskAIBaseline, TaskActual.actual_hours)
        .outerjoin(TaskAIBaseline, TaskAIBaseline.task_id == Task.id)
        .outerjoin(TaskActual, TaskActual.task_id == Task.id)
        .where(Task.estimate_id.in_(est_ids)))) if est_ids else []
    unplanned = list(db.scalars(select(UnplannedActual).where(UnplannedActual.project_id.in_(list(finals))))) \
        if finals else []

    by_est: dict[uuid.UUID, list] = defaultdict(list)
    for t, b, act in rows:
        by_est[t.estimate_id].append((t, b, act))
    unpl_by_proj: dict[uuid.UUID, list[UnplannedActual]] = defaultdict(list)
    for u in unplanned:
        unpl_by_proj[u.project_id].append(u)

    delivered = sorted([p for p in projects.values() if p.status == "delivered"],
                       key=lambda p: (p.delivered_at is None, p.delivered_at))
    per_project, learning, coverage_tasks = [], [], []
    cat_ratios: dict[str, list[float]] = defaultdict(list)
    role_pa: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])
    cat_pa: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])
    for p in delivered:
        est = finals[p.id]
        items = by_est.get(est.id, [])
        incl = [(t, b, a) for t, b, a in items if t.enabled and not t.removed and t.module_id not in removed_mods]
        planned_actual = sum(a for _, _, a in incl if a is not None)
        unpl = sum(u.hours for u in unpl_by_proj.get(p.id, []))
        actual = planned_actual + unpl
        if actual <= 0:
            continue
        lo = sum(t.min_hours for t, _, _ in incl)
        hi = sum(t.max_hours for t, _, _ in incl)
        final_mid = sum(mid(t.min_hours, t.max_hours) for t, _, _ in incl)
        sim = (est.summary or {}).get("simulation") or {}
        p50, p80 = sim.get("p50") or final_mid, sim.get("p80")
        raw = sum(mid(b.raw_min, b.raw_max) for _, b, _ in items if b is not None and b.raw_min is not None)
        shown = sum(mid(b.shown_min, b.shown_max) for _, b, _ in items if b is not None and b.shown_min is not None)
        per_project.append({"project_id": str(p.id), "name": p.name, "delivered_at": p.delivered_at,
                            "p50": round(p50, 1), "p80": round(p80, 1) if p80 else None, "min": round(lo, 1),
                            "max": round(hi, 1), "actual": round(actual, 1), "unplanned": round(unpl, 1),
                            "ape": _ape(p50, actual), "within_p80": actual <= p80 if p80 else None})
        if raw > 0:
            learning.append({"name": p.name, "delivered_at": p.delivered_at, "raw_ape": _ape(raw, actual),
                             "calibrated_ape": _ape(shown, actual) if shown else None,
                             "final_ape": _ape(final_mid, actual)})
        for t, _, a in incl:
            if a is None or a <= 0:
                continue
            m = mid(t.min_hours, t.max_hours)
            coverage_tasks.append(t.min_hours <= a <= t.max_hours)
            cat = cats.get(t.category_id, "other")
            if m > 0:
                cat_ratios[cat].append(math.log(a / m))
            role_pa[roles.get(t.delivery_role_id, "Unassigned")][0] += m
            role_pa[roles.get(t.delivery_role_id, "Unassigned")][1] += a
            cat_pa[cat][0] += m
            cat_pa[cat][1] += a

    # 2. accuracy over time with rolling median
    timeline, window = [], []
    for r in per_project:
        if r["ape"] is None:
            continue
        window.append(r["ape"])
        timeline.append({"name": r["name"], "delivered_at": r["delivered_at"], "ape": round(r["ape"] * 100, 1),
                         "rolling_median": round(statistics.median(window[-ROLLING:]) * 100, 1)})

    # 3. bias by category: geometric-mean ratio with a 95% interval
    bias = []
    for cat, xs in sorted(cat_ratios.items(), key=lambda kv: -len(kv[1])):
        n = len(xs)
        m = statistics.fmean(xs)
        se = statistics.stdev(xs) / math.sqrt(n) if n > 1 else None
        bias.append({"category": cat, "label": CATEGORY_NAMES.get(cat, (cat,))[0], "n": n,
                     "ratio": round(math.exp(m), 3),
                     "lo": round(math.exp(m - 1.96 * se), 3) if se is not None else None,
                     "hi": round(math.exp(m + 1.96 * se), 3) if se is not None else None,
                     "enough": n >= 5})

    # 4. coverage
    p80_known = [r["within_p80"] for r in per_project if r["within_p80"] is not None]
    coverage = {"task_in_range": sum(coverage_tasks) / len(coverage_tasks) if coverage_tasks else None,
                "task_n": len(coverage_tasks), "range_target": 0.8,
                "project_below_p80": sum(p80_known) / len(p80_known) if p80_known else None,
                "project_n": len(p80_known), "p80_target": 0.8,
                "enough": len(coverage_tasks) >= MIN_TASKS and len(p80_known) >= MIN_PROJECTS}

    # 5. unplanned work by reason, by project and over time
    reasons: dict[str, float] = defaultdict(float)
    for u in unplanned:
        if u.project_id in {p.id for p in delivered}:
            reasons[u.reason or "unspecified"] += u.hours
    total_actual = sum(r["actual"] for r in per_project)
    unplanned_out = {
        "by_reason": [{"reason": k, "hours": round(v, 1), "share": v / total_actual if total_actual else None}
                      for k, v in sorted(reasons.items(), key=lambda kv: -kv[1])],
        "by_project": [{"name": r["name"], "delivered_at": r["delivered_at"],
                        "share": round(r["unplanned"] / r["actual"] * 100, 1)} for r in per_project],
        "n": len(per_project), "enough": len(per_project) >= MIN_PROJECTS,
    }

    # 6. planned vs actual by role and category
    def pa(d: dict[str, list[float]], label=lambda k: k) -> list[dict]:
        return [{"key": k, "label": label(k), "planned": round(v[0], 1), "actual": round(v[1], 1)}
                for k, v in sorted(d.items(), key=lambda kv: -kv[1][1])]

    # 7. estimating productivity (all finalized estimates in the pool)
    first_doc = dict(db.execute(select(Document.project_id, func.min(Document.created_at))
                                .where(Document.project_id.in_(list(finals))).group_by(Document.project_id)).all()) \
        if finals else {}
    edits = dict(db.execute(select(EditEvent.estimate_id, func.count())
                            .where(EditEvent.estimate_id.in_(est_ids), EditEvent.actor.in_(("user", "agent")),
                                   EditEvent.event_type != "estimate_finalized")
                            .group_by(EditEvent.estimate_id)).all()) if est_ids else {}
    by_actor = dict(db.execute(select(EditEvent.actor, func.count())
                               .where(EditEvent.estimate_id.in_(est_ids), EditEvent.actor.in_(("user", "agent")),
                                      EditEvent.event_type != "estimate_finalized")
                               .group_by(EditEvent.actor)).all()) if est_ids else {}
    prod_rows = []
    for pid, e in finals.items():
        items = by_est.get(e.id, [])
        ai = [(t, b) for t, b, _ in items if b is not None]
        changed = sum(1 for t, b in ai if t.removed or not t.enabled or (b.shown_min, b.shown_max) != (t.min_hours, t.max_hours))
        start = first_doc.get(pid)
        lead_h = (e.finalized_at - start).total_seconds() / 3600 if e.finalized_at and start and e.finalized_at > start \
            else None
        prod_rows.append({"name": projects[pid].name, "finalized_at": e.finalized_at,
                          "lead_time_hours": round(lead_h, 1) if lead_h is not None else None,
                          "edits": edits.get(e.id, 0),
                          "changed_share": changed / len(ai) if ai else None})
    prod_rows.sort(key=lambda r: (r["finalized_at"] is None, r["finalized_at"]))
    leads = [r["lead_time_hours"] for r in prod_rows if r["lead_time_hours"] is not None]
    shares = [r["changed_share"] for r in prod_rows if r["changed_share"] is not None]
    total_edits = sum(by_actor.values())
    productivity = {
        "per_estimate": prod_rows, "n": len(prod_rows), "enough": len(prod_rows) >= MIN_PROJECTS,
        "median_lead_time_hours": statistics.median(leads) if leads else None,
        "median_edits": statistics.median([r["edits"] for r in prod_rows]) if prod_rows else None,
        "median_changed_share": statistics.median(shares) if shares else None,
        "agent_edit_share": by_actor.get("agent", 0) / total_edits if total_edits else None,
        "edits_by_actor": {"manual": by_actor.get("user", 0), "agent": by_actor.get("agent", 0)},
    }

    return {
        "min_projects": MIN_PROJECTS,
        "estimate_vs_actual": {"rows": per_project, "n": len(per_project), "enough": len(per_project) >= MIN_PROJECTS},
        "accuracy_over_time": {"rows": timeline, "n": len(timeline), "enough": len(timeline) >= MIN_PROJECTS,
                               "window": ROLLING},
        "bias_by_category": {"rows": bias, "n": sum(b["n"] for b in bias), "enough": any(b["enough"] for b in bias)},
        "coverage": coverage,
        "unplanned": unplanned_out,
        "planned_vs_actual": {"by_role": pa(role_pa), "by_category": pa(cat_pa, lambda k: CATEGORY_NAMES.get(k, (k,))[0]),
                              "n": len(coverage_tasks), "enough": len(coverage_tasks) >= MIN_TASKS},
        "productivity": productivity,
        "learning_impact": {"rows": [{**r, **{k: round(v * 100, 1) if v is not None else None
                                              for k, v in r.items() if k.endswith("_ape")}} for r in learning],
                            "n": len(learning), "enough": len(learning) >= MIN_PROJECTS},
    }
