from __future__ import annotations

import math

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.templates import CATEGORY_NAMES
from app.db.models import CalibrationRun, CalibrationStat, Project
from app.services.actuals import accuracy
from app.services.learning import load_records, structural_signals


def calibration_overview(db: Session) -> list[dict]:
    rows = list(db.scalars(select(CalibrationStat).order_by(CalibrationStat.layer, CalibrationStat.scope_type,
                                                            CalibrationStat.scope_key)))
    out = []
    for s in rows:
        se = math.sqrt(s.shrunk_var / max(s.n, 1))
        out.append({
            "layer": s.layer, "scope_type": s.scope_type, "scope_key": s.scope_key,
            "label": CATEGORY_NAMES.get(s.scope_key, (s.scope_key,))[0], "n": s.n,
            "mean_log_ratio": s.mean_log_ratio, "shrunk_mean": s.shrunk_mean, "shrunk_var": s.shrunk_var,
            "factor": math.exp(s.shrunk_mean), "factor_lo": math.exp(s.shrunk_mean - 1.96 * se),
            "factor_hi": math.exp(s.shrunk_mean + 1.96 * se), "updated_at": s.updated_at,
        })
    return out


def timeline(db: Session) -> list[dict]:
    runs = list(db.scalars(select(CalibrationRun).where(CalibrationRun.trigger != "backtest")
                           .order_by(CalibrationRun.created_at)))
    out = []
    for r in runs:
        stats = (r.stats_snapshot or {}).get("stats", {})
        point = {"id": str(r.id), "created_at": r.created_at, "trigger": r.trigger, "layer": r.layer,
                 "n_projects": (r.stats_snapshot or {}).get("n_projects")}
        for k, v in stats.items():
            if k.startswith("category:") or k == "global:global":
                point[k.split(":", 1)[1]] = v["factor"]
        out.append(point)
    return out


def accuracy_over_time(db: Session) -> list[dict]:
    projects = list(db.scalars(select(Project).where(Project.status == "delivered").order_by(Project.delivered_at)))
    out = []
    for p in projects:
        try:
            a = accuracy(db, p.id)
        except Exception:
            continue
        out.append({"project_id": str(p.id), "name": p.name, "data_source": p.data_source,
                    "delivered_at": p.delivered_at, "ape": a["project_ape"], "task_mdape": a["task_mdape"],
                    "within_p80": a["within_p80"], "unplanned_share": a["unplanned_share"]})
    return out


def structural(db: Session) -> dict:
    return structural_signals(load_records(db))
