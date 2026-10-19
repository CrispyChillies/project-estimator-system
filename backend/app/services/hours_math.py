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


@dataclass
class CostFitResult:
    feasible: bool
    new_ranges: list[tuple[float, float]]
    feasible_min_cost: float
    achieved_cost: float  # cost of the new max hours (<= target when feasible)
    message: str = ""


def fit_to_cost_budget(ranges: list[tuple[float, float]], rates: list[float], target_cost: float, *,
                       locked: list[bool] | None = None) -> CostFitResult:
    """Scale unlocked tasks so the cost of the max hours (sum max_h * rate) is as close as possible to `target_cost`
    without exceeding it. Same rules as `fit_to_budget`: half-hour steps, each task keeps at least MIN_FRACTION of its
    max, min <= max, tasks at rate 0 only count as fixed. Infeasible -> unchanged ranges + the minimum possible cost.
    Pure arithmetic; the LLM never computes money."""
    n = len(ranges)
    locked = locked or [False] * n
    locked_cost = sum(r[1] * rt for r, rt, lk in zip(ranges, rates, locked, strict=True) if lk)
    free = [i for i in range(n) if not locked[i] and ranges[i][1] > 0]
    fixed_cost = locked_cost + sum(ranges[i][1] * rates[i] for i in range(n) if not locked[i] and ranges[i][1] <= 0)
    floors = {i: task_floor(ranges[i][1]) for i in free}
    min_cost = fixed_cost + sum(floors[i] * rates[i] for i in free)
    zero_rate = [i for i in free if rates[i] <= 0]
    if not free or target_cost < min_cost - 1e-6:
        return CostFitResult(False, list(ranges), min_cost, sum(r[1] * rt for r, rt in zip(ranges, rates, strict=True)),
                             f"Cannot fit {target_cost:,.0f} ₫: the smallest sensible total is {min_cost:,.0f} ₫ "
                             f"(no task cut by more than {100 * (1 - MIN_FRACTION):.0f}%).")
    # one common factor f over free tasks: cost(f) = fixed + sum(rate * max(floor, hi * f)); monotone -> bisection
    def cost_at(f: float) -> float:
        return fixed_cost + sum(rates[i] * max(floors[i], ranges[i][1] * f) for i in free)

    lo_f, hi_f = 0.0, 1.0
    while cost_at(hi_f) < target_cost and hi_f < 1e6:
        hi_f *= 2
    for _ in range(80):
        mid_f = (lo_f + hi_f) / 2
        if cost_at(mid_f) < target_cost:
            lo_f = mid_f
        else:
            hi_f = mid_f
    f = lo_f
    units = {i: max(math.ceil(floors[i] / STEP - 1e-9), math.floor(ranges[i][1] * f / STEP + 1e-9)) for i in free}
    cost = fixed_cost + sum(units[i] * STEP * rates[i] for i in free)
    # spend the remaining budget in half-hour steps, largest fractional remainder first, never exceeding the target
    order = sorted((i for i in free if rates[i] > 0),
                   key=lambda i: -((ranges[i][1] * f / STEP) - math.floor(ranges[i][1] * f / STEP + 1e-9)))
    progressed = True
    while progressed:
        progressed = False
        for i in order:
            if cost + STEP * rates[i] <= target_cost + 1e-6:
                units[i] += 1
                cost += STEP * rates[i]
                progressed = True
    out = list(ranges)
    for i in free:
        lo, hi = ranges[i]
        mx = units[i] * STEP
        ratio = mx / hi if hi > 0 else 1.0
        out[i] = (min(mx, max(0.0, round_step(lo * ratio))), mx)
    for i in zero_rate:  # unpriced tasks keep their scale factor so the plan stays proportional
        lo, hi = ranges[i]
        mx = max(floors[i], round_step(hi * f))
        out[i] = (min(mx, max(0.0, round_step(lo * f))), mx)
    achieved = sum(out[i][1] * rates[i] for i in range(n))
    return CostFitResult(True, out, min_cost, achieved)
