"""Deterministic hour arithmetic for agent tools: half-hour rounding with largest remainder, budget fitting,
role rebalancing. Pure functions over plain numbers so they can be property-tested."""

from __future__ import annotations

import math
from dataclasses import dataclass

STEP = 0.5
# A fitted task keeps at least this share of its current max; cutting deeper means removing scope, not squeezing.
MIN_FRACTION = 0.25


def round_step(x: float, step: float = STEP) -> float:
    return round(x / step) * step


def largest_remainder(values: list[float], target: float, floors: list[float] | float = STEP,
                      step: float = STEP) -> list[float]:
    """Split `target` proportionally to `values` in `step` units, each >= its floor (water-filling for floors,
    then largest remainder). Caller guarantees feasibility: target >= sum of floors (in units)."""
    n = len(values)
    if n == 0:
        return []
    fl = floors if isinstance(floors, list) else [floors] * n
    fu = [math.ceil(f / step - 1e-9) for f in fl]
    total = round(target / step)
    fixed: dict[int, int] = {}
    while True:  # pin items whose proportional share falls below their floor
        free = [i for i in range(n) if i not in fixed]
        rem = total - sum(fixed.values())
        s = sum(values[i] for i in free)
        share = {i: (values[i] / s if s > 0 else 1 / len(free)) * rem for i in free}
        low = [i for i in free if share[i] < fu[i]]
        if not low:
            break
        for i in low:
            fixed[i] = fu[i]
    units = [0] * n
    for i, u in fixed.items():
        units[i] = u
    for i in free:
        units[i] = max(fu[i], math.floor(share[i]))
    diff = total - sum(units)
    order = sorted(free, key=lambda i: (-(share[i] - math.floor(share[i])), i))
    k = 0
    while diff > 0 and order:
        units[order[k % len(order)]] += 1
        diff -= 1
        k += 1
    while diff < 0:
        cand = sorted((i for i in range(n) if units[i] > fu[i]), key=lambda i: (units[i] - values[i], -i), reverse=True)
        if not cand:
            break
        units[cand[0]] -= 1
        diff += 1
    return [u * step for u in units]


@dataclass
class FitResult:
    feasible: bool
    new_ranges: list[tuple[float, float]]
    feasible_min: float
    message: str = ""


def task_floor(max_hours: float) -> float:
    return max(STEP, math.ceil(max_hours * MIN_FRACTION / STEP - 1e-9) * STEP)


def fit_to_budget(ranges: list[tuple[float, float]], target: float, *,
                  locked: list[bool] | None = None) -> FitResult:
    """Scale unlocked ranges so the sum of max hours equals `target` (rounded to 0.5 h). Min hours scale by the
    same per-task factor and never exceed max. Infeasible -> unchanged ranges plus the feasible minimum."""
    locked = locked or [False] * len(ranges)
    target = round_step(target)
    locked_max = sum(r[1] for r, lk in zip(ranges, locked, strict=True) if lk)
    free = [i for i, lk in enumerate(locked) if not lk]
    floors = [task_floor(ranges[i][1]) for i in free]
    feasible_min = locked_max + sum(floors)
    if not free or target < feasible_min:
        return FitResult(False, list(ranges), feasible_min,
                         f"Cannot fit {target:g} h: the smallest sensible total is {feasible_min:g} h "
                         f"(no task cut by more than {100 * (1 - MIN_FRACTION):.0f}%"
                         + (f", {locked_max:g} h locked" if locked_max else "") + ").")
    new_max = largest_remainder([ranges[i][1] for i in free], target - locked_max, floors)
    out = list(ranges)
    for i, mx in zip(free, new_max, strict=True):
        lo, hi = ranges[i]
        f = mx / hi if hi > 0 else 1.0
        out[i] = (min(mx, max(0.0, round_step(lo * f))), mx)
    return FitResult(True, out, feasible_min)


def rebalance_share(ranges: list[tuple[float, float]], in_group: list[bool], share: float) -> list[tuple[float, float]]:
    """Scale group tasks and the rest so the group's share of the total midpoint is `share`; total unchanged."""
    mids = [(lo + hi) / 2 for lo, hi in ranges]
    total = sum(mids)
    g = sum(m for m, ing in zip(mids, in_group, strict=True) if ing)
    o = total - g
    if g <= 0 or o <= 0:
        return list(ranges)
    a, b = share * total / g, (1 - share) * total / o
    out = []
    for (lo, hi), ing in zip(ranges, in_group, strict=True):
        f = a if ing else b
        nhi = max(STEP, round_step(hi * f))
        out.append((min(nhi, max(0.0, round_step(lo * f))), nhi))
    return out
