from __future__ import annotations

import math

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.templates import CATEGORY_NAMES
from app.db.models import CalibrationRun, CalibrationStat, Project
from app.services.actuals import accuracy
from app.services.learning import load_records, structural_signals


def calibration_overview(db: Session, pool: list | None = None) -> list[dict]:
    if pool is None:
        rows = list(db.scalars(select(CalibrationStat).order_by(CalibrationStat.layer, CalibrationStat.scope_type,
                                                                CalibrationStat.scope_key)))
    else:
        from datetime import UTC, datetime
        from types import SimpleNamespace

        from app.services.learning import load_stats

        edit, actual = load_stats(db, pool)
        now = datetime.now(UTC)
        rows = [SimpleNamespace(layer=st.layer, scope_type=st.scope_type, scope_key=st.scope_key, n=st.n,
                                mean_log_ratio=st.mean, shrunk_mean=st.shrunk_mean, shrunk_var=st.shrunk_var,
                                updated_at=now)
                for stats in (edit, actual) for st in stats.values() if st.scope_type in ("global", "category")]
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


def timeline(db: Session, owner_id=None, admin: bool = True) -> list[dict]:
    q = select(CalibrationRun).where(CalibrationRun.trigger != "backtest").order_by(CalibrationRun.created_at)
    if admin:
        q = q.where((CalibrationRun.owner_id.is_(None)) | (CalibrationRun.owner_id == owner_id))
    else:
        q = q.where(CalibrationRun.owner_id == owner_id)
    runs = list(db.scalars(q))
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


def accuracy_over_time(db: Session, pool: list | None = None) -> list[dict]:
    q = select(Project).where(Project.status == "delivered").order_by(Project.delivered_at)
    if pool is not None:
        q = q.where(Project.id.in_(pool))
    projects = list(db.scalars(q))
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


def structural(db: Session, pool: list | None = None) -> dict:
    return structural_signals(load_records(db, pool) if pool is None or pool else [])
