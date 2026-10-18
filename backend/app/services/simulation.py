"""Monte Carlo interval simulation (Evidence-Based-Scheduling style). Pure NumPy, no DB."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

import numpy as np

from app.services.calibration import StatsMap
from app.services.settings import LearningParams


@dataclass(frozen=True)
class SimTask:
    mid: float
    category: str
    sigma: float


def simulate(tasks: list[SimTask], actual: StatsMap, p: LearningParams, *, seed: int | None = 42,
             draws: int | None = None, shared_factor: bool = True, bins: int = 30) -> dict:
    n_draws = draws or p.sim_draws
    rng = np.random.default_rng(seed)
    if not tasks:
        return {"p10": 0.0, "p50": 0.0, "p80": 0.0, "p90": 0.0, "mean": 0.0, "histogram": [],
                "draws": n_draws, "empirical_categories": [], "shared": "none"}

    total = np.zeros(n_draws)
    groups: dict[str, list[SimTask]] = defaultdict(list)
    for t in tasks:
        groups[t.category].append(t)
    empirical: list[str] = []
    for cat, ts in groups.items():
        mids = np.array([t.mid for t in ts])
        stat = actual.get(("category", cat))
        if stat and stat.n >= p.empirical_min_n and stat.residuals:
            pool = np.asarray(stat.residuals)
            res = rng.choice(pool, size=(n_draws, len(ts)), replace=True)
            empirical.append(cat)
        else:
            sig = np.array([t.sigma for t in ts])
            res = rng.standard_normal((n_draws, len(ts))) * sig
        total += (mids * np.exp(res)).sum(axis=1)

    shared_kind = "none"
    if shared_factor:
        ps = actual.get(("project", "shared"))
        if ps and ps.n >= p.project_factor_min_n:
            pool = np.asarray(ps.residuals) - np.mean(ps.residuals)
            total *= np.exp(rng.choice(pool, size=n_draws, replace=True))
            shared_kind = f"empirical(n={ps.n})"
        elif p.sigma_proj > 0:
            total *= np.exp(rng.standard_normal(n_draws) * p.sigma_proj)
            shared_kind = f"normal(sigma={p.sigma_proj})"

    q = np.percentile(total, [10, 50, 80, 90])
    counts, edges = np.histogram(total, bins=bins)
    return {
        "p10": float(q[0]), "p50": float(q[1]), "p80": float(q[2]), "p90": float(q[3]),
        "mean": float(total.mean()), "draws": n_draws,
        "histogram": [{"x0": float(edges[i]), "x1": float(edges[i + 1]), "count": int(counts[i])}
                      for i in range(len(counts))],
        "empirical_categories": sorted(empirical), "shared": shared_kind,
    }
