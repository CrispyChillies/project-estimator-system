"""DB-facing learning: load history, recompute stats from scratch, finalize/deliver hooks, lessons."""

from __future__ import annotations

import logging
import math
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime

import numpy as np
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import (
    CalibrationRun,
    CalibrationStat,
    EditEvent,
    Estimate,
    LearnedRule,
    LLMRawEstimate,
    Module,
    Project,
    Task,
    TaskActual,
    TaskAIBaseline,
    UnplannedActual,
)
from app.services import estimates as es
from app.services.calibration import Sample, ScopeStat, StatsMap, build_stats, log_ratio, mid
from app.services.reference import category_maps
from app.services.settings import LearningParams, get_params

log = logging.getLogger(__name__)


@dataclass
class TaskRec:
    task_id: str
    key: str | None
    title: str
    category: str
    raw_min: float | None
    raw_max: float | None
    final_min: float | None  # None if removed / disabled in the final estimate
    final_max: float | None
    actual: float | None
    origin: str
    embedding: np.ndarray | None = None

    @property
    def raw_mid(self) -> float | None:
        return mid(self.raw_min, self.raw_max) if self.raw_min is not None else None

    @property
    def final_mid(self) -> float | None:
        return mid(self.final_min, self.final_max) if self.final_min is not None else None


@dataclass
class ProjectRec:
    id: str
    name: str
    data_source: str
    status: str
    author: str | None
    date: datetime | None
    estimate_id: str
    tasks: list[TaskRec] = field(default_factory=list)
    unplanned_hours: float = 0.0
    raw_samples: dict[str, list[tuple[float, float]]] = field(default_factory=dict)

    @property
    def delivered(self) -> bool:
        return self.status == "delivered"


def active_model_key() -> str:
    from app.llm.gateway import get_gateway

    return get_gateway().model_key


def latest_final_estimates(db: Session, project_ids: list[uuid.UUID] | None = None,
                           model_key: str | None = None) -> dict[uuid.UUID, Estimate]:
    q = select(Estimate).where(Estimate.status == "final").order_by(Estimate.finalized_at.asc().nulls_first())
    if project_ids is not None:
        q = q.where(Estimate.project_id.in_(project_ids))
    if model_key is not None:
        q = q.where(Estimate.model_key == model_key)
    out: dict[uuid.UUID, Estimate] = {}
    for e in db.scalars(q):
        out[e.project_id] = e  # last wins
    return out


def load_records(db: Session, project_ids: list[uuid.UUID] | None = None, *, with_embeddings: bool = False,
                 with_raw_samples: bool = False, model_key: str | None = None) -> list[ProjectRec]:
    """History for ONE model_key (default: the active one) so fake and live data never mix."""
    id2cat, _ = category_maps(db)
    key = model_key or active_model_key()
    finals = latest_final_estimates(db, project_ids, key)
    if not finals:
        return []
    projects = {p.id: p for p in db.scalars(select(Project).where(Project.id.in_(list(finals))))}
    est_ids = [e.id for e in finals.values()]
    removed_modules = set(db.scalars(select(Module.id).where(Module.estimate_id.in_(est_ids), Module.removed.is_(True))))
    baselines = {b.task_id: b for b in db.scalars(select(TaskAIBaseline).where(TaskAIBaseline.estimate_id.in_(est_ids)))}
    tasks = list(db.scalars(select(Task).where(Task.estimate_id.in_(est_ids))))
    actuals = {a.task_id: a.actual_hours for a in db.scalars(
        select(TaskActual).where(TaskActual.task_id.in_([t.id for t in tasks])))}
    unplanned: dict[uuid.UUID, float] = defaultdict(float)
    for u in db.scalars(select(UnplannedActual).where(UnplannedActual.project_id.in_(list(finals)))):
        unplanned[u.project_id] += u.hours
    raw_samples: dict[uuid.UUID, dict[str, list[tuple[float, float]]]] = defaultdict(lambda: defaultdict(list))
    if with_raw_samples:
        for r in db.scalars(select(LLMRawEstimate).where(LLMRawEstimate.project_id.in_(list(finals)),
                                                         LLMRawEstimate.model_key == key)
                            .order_by(LLMRawEstimate.run_idx)):
            raw_samples[r.project_id][r.task_key].append((r.raw_min, r.raw_max))

    by_est: dict[uuid.UUID, list[TaskRec]] = defaultdict(list)
    for t in tasks:
        b = baselines.get(t.id)
        included = es.is_effectively_included(t, t.module_id in removed_modules)
        by_est[t.estimate_id].append(TaskRec(
            task_id=str(t.id), key=t.ai_key, title=t.title,
            category=id2cat.get(t.category_id, "other") if t.category_id else (b.category_key if b else "other"),
            raw_min=b.raw_min if b else None, raw_max=b.raw_max if b else None,
            final_min=t.min_hours if included else None, final_max=t.max_hours if included else None,
            actual=actuals.get(t.id), origin=t.origin,
            embedding=np.asarray(t.embedding, dtype=float) if with_embeddings and t.embedding is not None else None,
        ))
    out = []
    for pid, e in finals.items():
        p = projects[pid]
        out.append(ProjectRec(
            id=str(pid), name=p.name, data_source=p.data_source, status=p.status,
            author=str(e.finalized_by) if e.finalized_by else None,
            date=p.delivered_at or e.finalized_at or p.created_at, estimate_id=str(e.id),
            tasks=by_est[e.id], unplanned_hours=unplanned[pid],
            raw_samples={k: v for k, v in raw_samples[pid].items()},
        ))
    out.sort(key=lambda r: (r.date or datetime.min.replace(tzinfo=UTC), r.name))
    return out


def samples_from_records(recs: list[ProjectRec], layer: str) -> list[Sample]:
    """Learning always uses the RAW LLM output as the denominator (never the calibrated number)."""
    out = []
    for r in recs:
        for t in r.tasks:
            if t.raw_mid is None:
                continue  # user/agent-added task: structural signal only
            if layer == "edit":
                x = log_ratio(t.final_mid, t.raw_mid) if t.final_mid else None
            else:
                if not r.delivered:
                    continue
                x = log_ratio(t.actual, t.raw_mid) if t.actual and t.final_mid else None
            if x is not None:
                out.append(Sample(x=x, category=t.category, project=r.id, author=r.author if layer == "edit" else None))
    return out


def stats_from_records(recs: list[ProjectRec], p: LearningParams) -> tuple[StatsMap, StatsMap]:
    return (build_stats(samples_from_records(recs, "edit"), "edit", p),
            build_stats(samples_from_records(recs, "actual"), "actual", p))


def structural_signals(recs: list[ProjectRec]) -> dict:
    added: Counter[str] = Counter()
    removed: Counter[str] = Counter()
    ai_total: Counter[str] = Counter()
    final_total: Counter[str] = Counter()
    added_titles: Counter[tuple[str, str]] = Counter()
    unplanned_share = []
    for r in recs:
        for t in r.tasks:
            if t.raw_mid is not None and t.origin == "ai":
                ai_total[t.category] += 1
                if t.final_mid is None:
                    removed[t.category] += 1
            elif t.origin != "ai" and t.final_mid is not None:
                added[t.category] += 1
                added_titles[(t.category, t.title)] += 1
            if t.final_mid is not None:
                final_total[t.category] += 1
        if r.delivered:
            planned = sum(t.actual or 0 for t in r.tasks)
            if planned + r.unplanned_hours > 0:
                unplanned_share.append(r.unplanned_hours / (planned + r.unplanned_hours))
    cats = sorted(set(ai_total) | set(added))
    return {
        "categories": [{
            "category": c, "ai_tasks": ai_total[c], "added": added[c], "removed": removed[c],
            "missing_task_rate": added[c] / final_total[c] if final_total[c] else 0.0,
            "false_positive_rate": removed[c] / ai_total[c] if ai_total[c] else 0.0,
        } for c in cats],
        "frequently_added": [{"category": c, "title": t, "count": n} for (c, t), n in added_titles.most_common(10)],
        "unplanned_share_mean": float(np.mean(unplanned_share)) if unplanned_share else None,
        "unplanned_share_n": len(unplanned_share),
    }


def load_stats(db: Session, pool: list[uuid.UUID] | None = None) -> tuple[StatsMap, StatsMap]:
    """Calibration stats for a learning pool. None = the full (admin) pool, read from calibration_stats."""
    if pool is not None:
        return stats_from_records(load_records(db, pool) if pool else [], get_params(db))
    edit: StatsMap = {}
    actual: StatsMap = {}
    for s in db.scalars(select(CalibrationStat)):
        st = ScopeStat(s.layer, s.scope_type, s.scope_key, s.n, s.mean_log_ratio, s.var_log_ratio, s.shrunk_mean,
                       s.shrunk_var, list(s.residuals or []))
        (edit if s.layer == "edit" else actual)[(s.scope_type, s.scope_key)] = st
    return edit, actual


def _snapshot(stats: StatsMap) -> dict:
    return {f"{k[0]}:{k[1]}": {"n": s.n, "mean": s.mean, "shrunk_mean": s.shrunk_mean, "shrunk_var": s.shrunk_var,
                               "factor": math.exp(s.shrunk_mean)}
            for k, s in stats.items() if k[0] in ("global", "category", "project")}


def recompute(db: Session, trigger: str, *, project_id: uuid.UUID | None = None,
              upto_project_ids: list[uuid.UUID] | None = None, layers: tuple[str, ...] = ("edit", "actual")) -> dict:
    """Recompute stats from the full history (idempotent) and write a calibration_runs row per layer."""
    p = get_params(db)
    recs = load_records(db, upto_project_ids)
    edit, actual = stats_from_records(recs, p)
    signals = structural_signals(recs)
    for layer, stats in (("edit", edit), ("actual", actual)):
        if layer not in layers:
            continue
        db.execute(delete(CalibrationStat).where(CalibrationStat.layer == layer))
        for s in stats.values():
            db.add(CalibrationStat(layer=layer, scope_type=s.scope_type, scope_key=s.scope_key, n=s.n,
                                   mean_log_ratio=s.mean, var_log_ratio=s.var, shrunk_mean=s.shrunk_mean,
                                   shrunk_var=s.shrunk_var, residuals=s.residuals))
        db.add(CalibrationRun(trigger=trigger, layer=layer, project_id=project_id,
                              stats_snapshot={"stats": _snapshot(stats), "structural": signals,
                                              "n_projects": len(recs), "model_key": active_model_key()}))
    db.flush()
    from app.db.models import Setting

    row = db.get(Setting, "calibration_model_key")
    if row is None:
        db.add(Setting(key="calibration_model_key", value=active_model_key()))
    else:
        row.value = active_model_key()
    db.flush()
    return {"edit": _snapshot(edit), "actual": _snapshot(actual)}


def model_status(db: Session) -> dict:
    """Which model_key the calibration belongs to, and whether it restarted because the model changed."""
    from sqlalchemy import func as sa_func

    from app.db.models import Setting

    key = active_model_key()
    counts = {k: n for k, n in db.execute(select(Estimate.model_key, sa_func.count())
                                          .where(Estimate.status == "final").group_by(Estimate.model_key))}
    row = db.get(Setting, "calibration_model_key")
    return {"active_model_key": key, "calibration_model_key": row.value if row else None,
            "final_estimates_by_key": counts, "active_history": counts.get(key, 0),
            "restarted": counts.get(key, 0) == 0 and any(n > 0 for k, n in counts.items() if k != key)}


def ensure_calibration_for_active_model(db: Session) -> bool:
    """Recompute stats when the active model_key differs from the one the stored stats were built for."""
    from app.db.models import Setting

    row = db.get(Setting, "calibration_model_key")
    if row is not None and row.value == active_model_key():
        return False
    if row is not None and not latest_final_estimates(db, model_key=active_model_key()):
        # No history for this model yet: keep the stored stats instead of replacing them with empty ones.
        return False
    recompute(db, "manual")
    db.commit()
    log.info("calibration recomputed for model_key", extra={"extra": {"model_key": active_model_key()}})
    return True


# ---------------- hooks ----------------
def finalize_estimate(db: Session, estimate_id: uuid.UUID, user_id: uuid.UUID | None, *, run_lessons: bool = True) -> Estimate:
    est = es.ensure_draft(db, estimate_id)
    est.status = "final"
    est.finalized_at = datetime.now(UTC)
    est.finalized_by = user_id
    es.log_event(db, est.id, es.Actor("user", user_id), "estimate_finalized", new={"version": est.version})
    project = db.get(Project, est.project_id)
    if project and project.status == "draft":
        project.status = "quoted"
    db.flush()
    recompute(db, "estimate_finalized", project_id=est.project_id, layers=("edit",))
    _member_snapshot(db, user_id, "estimate_finalized", est.project_id, ("edit",))
    if run_lessons:
        _lessons_for(db, user_id)
    return est


def deliver_project(db: Session, project_id: uuid.UUID, *, run_lessons: bool = True,
                    user_id: uuid.UUID | None = None) -> Project:
    from app.core.errors import AppError, NotFound

    project = db.get(Project, project_id)
    if project is None:
        raise NotFound("Project")
    if project_id not in latest_final_estimates(db, [project_id]):
        raise AppError("no_final_estimate", "Finalize an estimate before marking the project delivered", 409)
    project.status = "delivered"
    project.delivered_at = project.delivered_at or datetime.now(UTC)
    db.flush()
    recompute(db, "project_delivered", project_id=project_id, layers=("actual",))
    _member_snapshot(db, user_id, "project_delivered", project_id, ("actual",))
    if run_lessons:
        _lessons_for(db, user_id)
    return project


def _member_snapshot(db: Session, user_id: uuid.UUID | None, trigger: str, project_id: uuid.UUID,
                     layers: tuple[str, ...]) -> None:
    """Members get their own calibration history computed only from their pool."""
    from app.core.access import pool_project_ids

    pool = pool_project_ids(db, user_id)
    if pool is None:
        return
    recs = load_records(db, pool) if pool else []
    edit, actual = stats_from_records(recs, get_params(db))
    for layer, stats in (("edit", edit), ("actual", actual)):
        if layer in layers:
            db.add(CalibrationRun(trigger=trigger, layer=layer, project_id=project_id, owner_id=user_id,
                                  stats_snapshot={"stats": _snapshot(stats), "n_projects": len(recs),
                                                  "model_key": active_model_key()}))
    db.flush()


def _lessons_for(db: Session, user_id: uuid.UUID | None) -> None:
    from app.core.access import pool_project_ids

    propose_lessons(db, pool_project_ids(db, user_id), owner_id=user_id)


# ---------------- lessons ----------------
def lesson_evidence(db: Session, pool: list[uuid.UUID] | None = None
                    ) -> tuple[list[dict], dict[str, list[uuid.UUID]]]:
    from app.agents.templates import CATEGORY_NAMES

    recs = load_records(db, pool) if pool is None or pool else []
    evidence: list[dict] = []
    event_ids: dict[str, list[uuid.UUID]] = {}
    task_cat = {t.task_id: t.category for r in recs for t in r.tasks}
    reasons: dict[str, Counter[str]] = defaultdict(Counter)
    ev_by_cat: dict[str, list[uuid.UUID]] = defaultdict(list)
    est_ids = [uuid.UUID(r.estimate_id) for r in recs]
    for ev in db.scalars(select(EditEvent).where(EditEvent.estimate_id.in_(est_ids),
                                                 EditEvent.event_type.in_(["hours_changed", "task_added"]))):
        cat = task_cat.get(str(ev.task_id))
        if cat:
            ev_by_cat[cat].append(ev.id)
            if ev.reason_tag:
                reasons[cat][ev.reason_tag] += 1
    for layer in ("edit", "actual"):
        samples = samples_from_records(recs, layer)
        by_cat: dict[str, list[float]] = defaultdict(list)
        for s in samples:
            by_cat[s.category].append(s.x)
        for cat, xs in by_cat.items():
            m = float(np.mean(xs))
            n_dir = sum(1 for x in xs if (x > 0.02 if m > 0 else x < -0.02))
            evidence.append({
                "kind": "category_bias", "layer": layer, "category": cat,
                "category_name": CATEGORY_NAMES.get(cat, (cat,))[0], "n": len(xs), "n_dir": n_dir,
                "mean_pct": (math.exp(m) - 1) * 100,
                "top_reason": reasons[cat].most_common(1)[0][0] if reasons[cat] else None,
            })
            event_ids[f"{layer}:{cat}"] = ev_by_cat[cat][:50]
    for fa in structural_signals(recs)["frequently_added"]:
        evidence.append({"kind": "missing_task", "category": fa["category"], "title": fa["title"],
                         "category_name": CATEGORY_NAMES.get(fa["category"], (fa["category"],))[0],
                         "count": fa["count"]})
        event_ids[f"edit:{fa['category']}:missing"] = ev_by_cat[fa["category"]][:50]
    evidence.sort(key=lambda e: -e.get("n", e.get("count", 0)))
    return evidence[:40], event_ids


def propose_lessons(db: Session, pool: list[uuid.UUID] | None = None,
                    owner_id: uuid.UUID | None = None) -> list[LearnedRule]:
    from app.agents.chains import run_lessons

    evidence, event_ids = lesson_evidence(db, pool)
    if not evidence:
        return []
    try:
        result = run_lessons(evidence)
    except Exception:
        log.exception("lessons chain failed")
        return []
    mine = _rules_q(owner_id)
    existing = {(r.layer, (r.scope or {}).get("category_key"), r.text) for r in db.scalars(mine)}
    active_scopes = {(r.layer, (r.scope or {}).get("category_key")) for r in db.scalars(
        mine.where(LearnedRule.status != "proposed"))}
    # Replace stale proposals for the same scope; never touch active/disabled rules.
    new_rules = []
    for lesson in result.rules:
        scope_key = (lesson.layer, lesson.category_key)
        if (lesson.layer, lesson.category_key, lesson.text) in existing or scope_key in active_scopes:
            continue
        db.execute(delete(LearnedRule).where(LearnedRule.status == "proposed", LearnedRule.layer == lesson.layer,
                                             LearnedRule.owner_id == owner_id if owner_id else LearnedRule.owner_id.is_(None),
                                             LearnedRule.scope["category_key"].astext == (lesson.category_key or "")))
        ids = event_ids.get(f"{lesson.layer}:{lesson.category_key}") or event_ids.get(
            f"edit:{lesson.category_key}:missing", [])
        rule = LearnedRule(text=lesson.text[:500], layer=lesson.layer, scope={"category_key": lesson.category_key},
                           evidence_event_ids=ids, evidence_count=lesson.evidence_count, status="proposed",
                           owner_id=owner_id)
        db.add(rule)
        new_rules.append(rule)
    db.flush()
    return new_rules


def _rules_q(owner_id: uuid.UUID | None):
    q = select(LearnedRule)
    return q.where(LearnedRule.owner_id == owner_id) if owner_id else q


def active_rules(db: Session, owner_id: uuid.UUID | None = None) -> list[LearnedRule]:
    """Rules are per owner: a member only ever gets rules learned from their own pool."""
    p = get_params(db)
    return list(db.scalars(_rules_q(owner_id).where(LearnedRule.status == "active")
                           .order_by(LearnedRule.evidence_count.desc()).limit(p.max_active_rules)))
