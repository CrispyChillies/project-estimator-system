"""Pure calibration math (no DB). See docs/LEARNING.md.

All ratios are in log space: x = ln(reference_mid / raw_mid).
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass, field
from statistics import NormalDist

from app.services.settings import LearningParams

RESIDUAL_CAP = 500
MIN_SIGMA2 = 0.01


@dataclass(frozen=True)
class Sample:
    x: float
    category: str
    project: str
    author: str | None = None


@dataclass
class ScopeStat:
    layer: str
    scope_type: str
    scope_key: str
    n: int
    mean: float
    var: float
    shrunk_mean: float
    shrunk_var: float
    residuals: list[float] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


StatsMap = dict[tuple[str, str], ScopeStat]


def mid(lo: float, hi: float) -> float:
    return (lo + hi) / 2.0


def log_ratio(reference: float, raw: float) -> float | None:
    if reference is None or raw is None or reference <= 0 or raw <= 0:
        return None
    return math.log(reference / raw)


def moments(xs: Sequence[float]) -> tuple[int, float, float]:
    n = len(xs)
    if n == 0:
        return 0, 0.0, 0.0
    m = sum(xs) / n
    v = sum((x - m) ** 2 for x in xs) / (n - 1) if n > 1 else 0.0
    return n, m, v


def shrink(n: int, value: float, parent: float, k: float) -> float:
    return (n * value + k * parent) / (n + k)


def _scope(layer: str, stype: str, key: str, xs: list[float], parent_m: float, parent_v: float,
           k: float) -> ScopeStat:
    n, m, v = moments(xs)
    return ScopeStat(
        layer=layer, scope_type=stype, scope_key=key, n=n, mean=m, var=v,
        shrunk_mean=shrink(n, m, parent_m, k), shrunk_var=shrink(n, v, parent_v, k),
        residuals=[x - m for x in xs][-RESIDUAL_CAP:],
    )


def build_stats(samples: Iterable[Sample], layer: str, p: LearningParams) -> StatsMap:
    """Recompute every scope from scratch (idempotent by construction)."""
    samples = list(samples)
    out: StatsMap = {}
    if not samples:
        return out
    g = _scope(layer, "global", "global", [s.x for s in samples], 0.0, p.default_sigma2, p.shrink_k)
    out[("global", "global")] = g

    by_cat: dict[str, list[Sample]] = defaultdict(list)
    for s in samples:
        by_cat[s.category].append(s)
    for cat, ss in sorted(by_cat.items()):
        c = _scope(layer, "category", cat, [s.x for s in ss], g.shrunk_mean, g.shrunk_var, p.shrink_k)
        out[("category", cat)] = c
        if layer == "edit":
            by_author: dict[str, list[float]] = defaultdict(list)
            for s in ss:
                if s.author:
                    by_author[s.author].append(s.x)
            for author, xs in sorted(by_author.items()):
                key = f"{cat}|{author}"
                out[("category_author", key)] = _scope(
                    layer, "category_author", key, xs, c.shrunk_mean, c.shrunk_var, p.shrink_k
                )

    if layer == "actual":
        # Shared project-level component: mean residual per project after removing category effect.
        per_project: dict[str, list[float]] = defaultdict(list)
        for s in samples:
            per_project[s.project].append(s.x - out[("category", s.category)].shrunk_mean)
        proj_means = [sum(v) / len(v) for _, v in sorted(per_project.items())]
        n, m, v = moments(proj_means)
        out[("project", "shared")] = ScopeStat(
            layer, "project", "shared", n, m, v, m, v, residuals=proj_means[-RESIDUAL_CAP:]
        )
    return out


@dataclass
class Calibration:
    mu: float
    sigma2: float
    factor: float
    scope_used: str
    n_edit: int
    n_actual: int
    mu_edit: float
    mu_actual: float | None

    @property
    def sigma(self) -> float:
        return math.sqrt(self.sigma2)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["sigma"] = self.sigma
        return d


def _edit_scope(category: str, author: str | None, edit: StatsMap, p: LearningParams):
    if author:
        s = edit.get(("category_author", f"{category}|{author}"))
        if s and s.n >= p.author_min_n:
            return s
    return edit.get(("category", category)) or edit.get(("global", "global"))


def calibrate(category: str, author: str | None, edit: StatsMap, actual: StatsMap,
              p: LearningParams) -> Calibration:
    es = _edit_scope(category, author, edit, p)
    mu_e = es.shrunk_mean if es else 0.0
    var_e = es.shrunk_var if es else p.default_sigma2
    n_e = es.n if es else 0

    as_ = actual.get(("category", category)) or actual.get(("global", "global"))
    if as_ and as_.n > 0:
        n_a, mu_a, var_a = as_.n, as_.mean, as_.shrunk_var
        k = p.actual_prior_k
        mu = (n_a * mu_a + k * mu_e) / (n_a + k)
        s2 = (n_a * var_a + k * var_e) / (n_a + k)
        scope = f"actual:{as_.scope_type}:{as_.scope_key}+edit:{es.scope_type if es else 'none'}"
    else:
        n_a, mu_a, mu, s2 = 0, None, mu_e, var_e
        scope = f"edit:{es.scope_type}:{es.scope_key}" if es else "cold_start"
    s2 = max(s2, MIN_SIGMA2)
    return Calibration(mu=mu, sigma2=s2, factor=math.exp(mu), scope_used=scope, n_edit=n_e,
                       n_actual=n_a, mu_edit=mu_e, mu_actual=mu_a)


@dataclass
class Analog:
    task_id: str
    project_id: str
    project_name: str
    title: str
    similarity: float
    raw_mid: float | None
    final_mid: float | None
    actual_mid: float | None

    @property
    def reference(self) -> float | None:
        return self.actual_mid if self.actual_mid else self.final_mid

    def to_dict(self) -> dict:
        return asdict(self)


def weighted_median(values: Sequence[float], weights: Sequence[float]) -> float:
    pairs = sorted(zip(values, weights, strict=True))
    total = sum(w for _, w in pairs)
    acc = 0.0
    for v, w in pairs:
        acc += w
        if acc >= total / 2:
            return v
    return pairs[-1][0]


def analog_estimate(analogs: Sequence[Analog], p: LearningParams) -> tuple[float | None, list[Analog]]:
    used = [a for a in analogs if a.similarity >= p.sim_min and a.reference and a.reference > 0]
    if not used:
        return None, []
    return weighted_median([a.reference for a in used], [a.similarity for a in used]), used


def blend(base_mid: float, analog_mid: float | None, n_eff: int, p: LearningParams) -> tuple[float, float]:
    if analog_mid is None or n_eff == 0 or base_mid <= 0:
        return base_mid, 0.0
    w = min(max(p.w_per_analog * n_eff, 0.0), p.w_max)
    return math.exp((1 - w) * math.log(base_mid) + w * math.log(analog_mid)), w


def round_half(x: float) -> float:
    return round(x * 2) / 2


def task_range(center: float, sigma: float, p: LearningParams) -> tuple[float, float]:
    nd = NormalDist()
    lo = center * math.exp(nd.inv_cdf(p.range_low_q) * sigma)
    hi = center * math.exp(nd.inv_cdf(p.range_high_q) * sigma)
    lo = max(p.min_task_hours, round_half(lo))
    hi = min(max(round_half(hi), lo), center * p.max_range_multiple)
    return lo, hi


@dataclass
class TaskPrediction:
    min_hours: float
    max_hours: float
    mid: float
    sigma: float
    applied_factor: float
    analog_mid: float | None
    blend_weight: float
    calibration: Calibration | None
    analogs_used: list[Analog]


def raw_sigma(raw_min: float, raw_max: float, p: LearningParams) -> float:
    """Sigma implied by the LLM's own min-max, treated as the configured quantile range."""
    z = NormalDist().inv_cdf(p.range_high_q) - NormalDist().inv_cdf(p.range_low_q)
    if raw_min <= 0 or raw_max <= raw_min:
        return math.sqrt(p.default_sigma2)
    return max(math.log(raw_max / raw_min) / z, 0.05)


def predict_task(raw_min: float, raw_max: float, category: str, author: str | None,
                 analogs: Sequence[Analog], edit: StatsMap, actual: StatsMap, p: LearningParams,
                 *, learning: bool = True, use_analogs: bool = True,
                 use_edit: bool = True, use_actual: bool = True) -> TaskPrediction:
    raw_mid = mid(raw_min, raw_max)
    if not learning:
        return TaskPrediction(raw_min, raw_max, raw_mid, raw_sigma(raw_min, raw_max, p), 1.0, None, 0.0,
                              None, [])
    cal = None
    center = raw_mid
    sigma = raw_sigma(raw_min, raw_max, p)
    if use_edit or use_actual:
        cal = calibrate(category, author, edit if use_edit else {}, actual if use_actual else {}, p)
        # Calibrate the raw mid first, then blend with analogs (avoids double counting; DECISIONS.md).
        center = raw_mid * cal.factor
        sigma = cal.sigma
    a_mid, used = analog_estimate(analogs, p) if use_analogs else (None, [])
    center, w = blend(center, a_mid, len(used), p)
    lo, hi = task_range(center, sigma, p)
    return TaskPrediction(lo, hi, center, sigma, center / raw_mid if raw_mid > 0 else 1.0, a_mid, w, cal, used)


def impact_score(delta_mid: float, prior_probability: float) -> float:
    p = min(max(prior_probability, 0.0), 1.0)
    return abs(delta_mid) * 4 * p * (1 - p)
