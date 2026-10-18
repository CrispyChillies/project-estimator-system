"""Backtest: leave-one-project-out / chronological evaluation of estimators. Never calls the LLM."""

from __future__ import annotations

import math
import random
import statistics
import uuid
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from statistics import NormalDist

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import BacktestResult, BacktestRun, CalibrationRun, Project
from app.services.calibration import Analog, predict_task
from app.services.learning import ProjectRec, TaskRec, load_records, stats_from_records
from app.services.retrieval import Candidate, cosine_rank, select_analogs
from app.services.settings import LearningParams, get_params
from app.services.simulation import SimTask, simulate

ESTIMATORS = ["E0_median", "E1_raw_llm", "E2_analogs", "E3_calibrated_edit", "E4_calibrated_full"]
Z = NormalDist()


@dataclass
class Pred:
    task_key: str | None
    p50: float
    p80: float
    p10: float
    p90: float
    actual: float


def eval_tasks(r: ProjectRec) -> list[TaskRec]:
    return [t for t in r.tasks if t.raw_mid and t.final_mid and t.actual and t.actual > 0]


def _raw(t: TaskRec, r: ProjectRec) -> tuple[float, float]:
    ss = r.raw_samples.get(t.key or "", [])
    if ss:
        return statistics.median(s[0] for s in ss), statistics.median(s[1] for s in ss)
    assert t.raw_min is not None and t.raw_max is not None
    return t.raw_min, t.raw_max


class AnalogIndex:
    """In-memory analog index over TRAINING projects only."""

    def __init__(self, train: list[ProjectRec]):
        self.items: list[tuple[TaskRec, ProjectRec]] = [
            (t, r) for r in train for t in r.tasks if t.embedding is not None and t.final_mid]
        self.matrix = np.vstack([t.embedding for t, _ in self.items]) if self.items else None

    def query(self, t: TaskRec, top_k: int) -> list[Analog]:
        if self.matrix is None or t.embedding is None:
            return []
        sims = cosine_rank(t.embedding, self.matrix)
        order = np.argsort(-sims)[: top_k * 6]
        cands = [Candidate(Analog(task_id=c.task_id, project_id=r.id, project_name=r.name, title=c.title,
                                  similarity=float(sims[i]), raw_mid=c.raw_mid, final_mid=c.final_mid,
                                  actual_mid=c.actual if r.delivered else None), c.category)
                 for i in order for c, r in [self.items[int(i)]]]
        return select_analogs(cands, t.category, top_k)


def predict(target: ProjectRec, train: list[ProjectRec], estimator: str, p: LearningParams, *,
            index: AnalogIndex | None = None, stats=None, project_level: bool = True,
            draws: int = 4000) -> tuple[list[Pred], Pred | None]:
    """Predict target's tasks using ONLY `train`. The target must not be in `train`."""
    assert all(r.id != target.id for r in train), "leakage: target project in training set"
    tasks = eval_tasks(target)
    preds: list[Pred] = []
    sim_tasks: list[SimTask] = []
    edit, actual = stats if stats is not None else stats_from_records(train, p)
    if estimator == "E0_median":
        by_cat: dict[str, list[float]] = defaultdict(list)
        for r in train:
            for t in r.tasks:
                ref = t.actual if (r.delivered and t.actual) else t.final_mid
                if ref:
                    by_cat[t.category].append(ref)
        all_vals = [v for vs in by_cat.values() for v in vs] or [8.0]
        for t in tasks:
            vals = by_cat.get(t.category) if len(by_cat.get(t.category, [])) >= 3 else all_vals
            q10, q50, q80, q90 = np.percentile(vals, [10, 50, 80, 90])
            preds.append(Pred(t.key, float(q50), float(q80), float(q10), float(q90), float(t.actual or 0)))
            sim_tasks.append(SimTask(float(q50), t.category, max(math.log(max(q90, 1e-6) / max(q50, 1e-6)) / 1.2816, 0.05)))
    else:
        idx = index if index is not None else (AnalogIndex(train) if estimator != "E1_raw_llm" else None)
        for t in tasks:
            rmin, rmax = _raw(t, target)
            if estimator == "E1_raw_llm":
                pr = predict_task(rmin, rmax, t.category, None, [], {}, {}, p, learning=False)
                center, sigma = pr.mid, pr.sigma
            else:
                analogs = idx.query(t, p.analog_top_k) if idx else []
                pr = predict_task(rmin, rmax, t.category, target.author, analogs, edit, actual, p,
                                  use_edit=estimator in ("E3_calibrated_edit", "E4_calibrated_full"),
                                  use_actual=estimator == "E4_calibrated_full")
                center, sigma = pr.mid, pr.sigma
            preds.append(Pred(t.key, center, center * math.exp(Z.inv_cdf(0.8) * sigma),
                              center * math.exp(Z.inv_cdf(0.1) * sigma), center * math.exp(Z.inv_cdf(0.9) * sigma),
                              float(t.actual or 0)))
            sim_tasks.append(SimTask(center, t.category, sigma))
    proj = None
    if project_level and tasks:
        calibrated = estimator in ("E3_calibrated_edit", "E4_calibrated_full")
        sim = simulate(sim_tasks, actual if estimator == "E4_calibrated_full" else {}, p, seed=1234, draws=draws,
                       shared_factor=calibrated)
        proj = Pred(None, sim["p50"], sim["p80"], sim["p10"], sim["p90"], sum(t.actual or 0 for t in tasks))
    return preds, proj


def metrics(preds: list[Pred]) -> dict:
    preds = [x for x in preds if x.actual > 0 and x.p50 > 0]
    if not preds:
        return {"n": 0}
    apes = [abs(x.p50 - x.actual) / x.actual for x in preds]
    return {
        "n": len(preds),
        "MAPE": 100 * float(np.mean(apes)),
        "MdAPE": 100 * float(np.median(apes)),
        "MMRE": float(np.mean(apes)),
        "PRED25": float(np.mean([a <= 0.25 for a in apes])),
        "bias": float(np.mean([math.log(x.p50 / x.actual) for x in preds])),
        "coverage_p80": float(np.mean([x.actual <= x.p80 for x in preds])),
        "interval_width": float(np.mean([(x.p90 - x.p10) / x.p50 for x in preds])),
    }


def bootstrap_ci(groups: list[list[Pred]], keys=("MAPE", "MdAPE", "coverage_p80", "PRED25"), b: int = 500,
                 seed: int = 7) -> dict:
    rng = random.Random(seed)
    vals: dict[str, list[float]] = defaultdict(list)
    for _ in range(b):
        sample = [x for _ in groups for x in rng.choice(groups)]
        m = metrics(sample)
        for k in keys:
            if k in m:
                vals[k].append(m[k])
    return {k: [float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))] for k, v in vals.items() if v}


def splits(recs: list[ProjectRec], protocol: str) -> list[tuple[ProjectRec, list[ProjectRec]]]:
    out = []
    for i, r in enumerate(recs):
        if protocol == "chronological":
            train = recs[:i]  # recs are sorted by date
            if len(train) < 2:
                continue
        else:
            train = [x for x in recs if x.id != r.id]
        out.append((r, train))
    return out


def learning_curve(recs: list[ProjectRec], p: LearningParams, estimators=("E1_raw_llm", "E3_calibrated_edit", "E4_calibrated_full"),
                   orderings: int = 6, max_test: int = 4, seed: int = 11) -> list[dict]:
    rng = random.Random(seed)
    max_test = min(max_test, max(1, len(recs) // 3))
    acc: dict[tuple[int, str], list[float]] = defaultdict(list)
    for _ in range(orderings):
        order = recs[:]
        rng.shuffle(order)
        # Fixed test set per ordering so the curve isolates the effect of more training data.
        test, pool = order[-max_test:], order[:-max_test]
        for n in range(1, len(pool) + 1):
            train = pool[:n]
            stats = stats_from_records(train, p)
            idx = AnalogIndex(train)
            for est in estimators:
                preds = [x for r in test for x in predict(r, train, est, p, index=idx, stats=stats, project_level=False)[0]]
                m = metrics(preds)
                if m.get("n"):
                    acc[(n, est)].append(m["MdAPE"])
    rows: dict[int, dict] = defaultdict(dict)
    for (n, est), v in acc.items():
        rows[n][est] = float(np.mean(v))
    return [{"n_train": n, **rows[n]} for n in sorted(rows)]


def run_backtest_core(recs: list[ProjectRec], p: LearningParams, protocol: str = "loo",
                      progress: Callable[[float, str], None] | None = None, with_curve: bool = True) -> dict:
    task_preds: dict[str, dict[str, list[Pred]]] = {e: {} for e in ESTIMATORS}
    proj_preds: dict[str, dict[str, Pred]] = {e: {} for e in ESTIMATORS}
    n_train: dict[str, int] = {}
    sp = splits(recs, protocol)
    for i, (target, train) in enumerate(sp):
        stats = stats_from_records(train, p)
        idx = AnalogIndex(train)
        n_train[target.id] = len(train)
        for est in ESTIMATORS:
            tp, pp = predict(target, train, est, p, index=idx, stats=stats)
            task_preds[est][target.id] = tp
            if pp:
                proj_preds[est][target.id] = pp
        if progress:
            progress(0.1 + 0.6 * (i + 1) / max(len(sp), 1), f"Fold {i + 1}/{len(sp)}")
    summary: dict = {"protocol": protocol, "n_projects": len(sp), "estimators": {}}
    for est in ESTIMATORS:
        groups = [v for v in task_preds[est].values() if v]
        all_tasks = [x for g in groups for x in g]
        projs = list(proj_preds[est].values())
        summary["estimators"][est] = {
            "task": metrics(all_tasks), "project": metrics(projs),
            "task_ci": bootstrap_ci(groups), "project_ci": bootstrap_ci([[x] for x in projs]),
        }
    if with_curve:
        if progress:
            progress(0.75, "Learning curve")
        summary["learning_curve"] = learning_curve(recs, p)
    summary["small_sample"] = len(sp) <= 20
    summary["data_sources"] = sorted({r.data_source for r in recs})
    return {"summary": summary, "task_preds": task_preds, "proj_preds": proj_preds, "n_train": n_train}


def eligible_records(db: Session, data_source: str | None = None) -> list[ProjectRec]:
    recs = load_records(db, with_embeddings=True, with_raw_samples=True)
    sources = (data_source,) if data_source else ("dataset", "synthetic")
    return [r for r in recs if r.data_source in sources and r.delivered and eval_tasks(r)]


def run_backtest(db: Session, config: dict, progress: Callable[[float, str], None] | None = None) -> BacktestRun:
    from app.services.learning import active_model_key

    p = get_params(db)
    protocol = config.get("protocol", "loo")
    # Never pool synthetic and real dataset projects.
    source = config.get("data_source") or "synthetic"
    run = BacktestRun(config={"protocol": protocol, "params": p.model_dump(), "model_key": active_model_key(),
                              "data_source": source}, status="running")
    db.add(run)
    db.flush()
    recs = eligible_records(db, source)
    if progress:
        progress(0.05, f"{len(recs)} eligible projects")
    out = run_backtest_core(recs, p, protocol, progress)
    for est in ESTIMATORS:
        for pid, preds in out["task_preds"][est].items():
            for x in preds:
                db.add(BacktestResult(run_id=run.id, estimator_key=est, project_id=uuid.UUID(pid), task_key=x.task_key,
                                      level="task", n_train=out["n_train"][pid], predicted_p50=x.p50,
                                      predicted_p80=x.p80, actual=x.actual, ape=abs(x.p50 - x.actual) / x.actual,
                                      covered_p80=x.actual <= x.p80, interval_width=(x.p90 - x.p10) / x.p50))
        for pid, x in out["proj_preds"][est].items():
            db.add(BacktestResult(run_id=run.id, estimator_key=est, project_id=uuid.UUID(pid), task_key=None,
                                  level="project", n_train=out["n_train"][pid], predicted_p50=x.p50,
                                  predicted_p80=x.p80, actual=x.actual, ape=abs(x.p50 - x.actual) / x.actual,
                                  covered_p80=x.actual <= x.p80, interval_width=(x.p90 - x.p10) / x.p50))
    run.summary = out["summary"]
    run.status = "done"
    db.add(CalibrationRun(trigger="backtest", layer="actual", stats_snapshot={"backtest_run_id": str(run.id)}))
    db.flush()
    return run


def run_results(db: Session, run_id: uuid.UUID) -> dict:
    run = db.get(BacktestRun, run_id)
    rows = list(db.scalars(select(BacktestResult).where(BacktestResult.run_id == run_id, BacktestResult.level == "project")))
    names = {p.id: (p.name, p.data_source) for p in db.scalars(select(Project).where(
        Project.id.in_({r.project_id for r in rows})))}
    per_project: dict[str, dict] = {}
    for r in rows:
        d = per_project.setdefault(str(r.project_id), {"project_id": str(r.project_id), "name": names[r.project_id][0],
                                                       "data_source": names[r.project_id][1], "actual": r.actual,
                                                       "n_train": r.n_train, "estimators": {}})
        d["estimators"][r.estimator_key] = {"p50": r.predicted_p50, "p80": r.predicted_p80, "ape": r.ape,
                                           "covered_p80": r.covered_p80}
    return {"run": run, "projects": sorted(per_project.values(), key=lambda x: x["name"])}
