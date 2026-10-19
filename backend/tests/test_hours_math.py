from hypothesis import given, settings
from hypothesis import strategies as st

from app.services import hours_math as hm

ranges_st = st.lists(
    st.tuples(st.integers(0, 80), st.integers(1, 80)).map(lambda p: (min(p) / 2, max(p) / 2 or 0.5)),
    min_size=1, max_size=40)


@settings(max_examples=300, deadline=None)
@given(ranges_st, st.floats(1, 2000), st.data())
def test_fit_to_budget_properties(ranges, target, data):
    locked = data.draw(st.lists(st.booleans(), min_size=len(ranges), max_size=len(ranges)))
    res = hm.fit_to_budget(ranges, target, locked=locked)
    t = hm.round_step(target)
    if not res.feasible:
        assert t < res.feasible_min or all(locked)
        assert res.new_ranges == ranges  # infeasible never changes anything
        return
    assert sum(hi for _, hi in res.new_ranges) == t  # exact, in half-hour units
    for (lo0, hi0), (lo, hi), lk in zip(ranges, res.new_ranges, locked, strict=True):
        assert (lo * 2).is_integer() and (hi * 2).is_integer()
        assert 0 <= lo <= hi
        if lk:
            assert (lo, hi) == (lo0, hi0)
        else:
            assert hi >= hm.task_floor(hi0)


@settings(max_examples=200, deadline=None)
@given(st.lists(st.floats(0.1, 100), min_size=1, max_size=30), st.integers(0, 400))
def test_largest_remainder_exact_and_floored(values, units):
    target = max(units * 0.5, 0.5 * len(values))
    out = hm.largest_remainder(values, target)
    assert sum(out) == target and all(v >= 0.5 for v in out)


def test_fit_is_deterministic_and_proportional():
    r = [(4, 8), (10, 20), (20, 40)]
    a = hm.fit_to_budget(r, 34)
    assert a == hm.fit_to_budget(r, 34)
    assert [hi for _, hi in a.new_ranges] == [4.0, 10.0, 20.0]


def test_fit_infeasible_reports_bounds():
    res = hm.fit_to_budget([(10, 40)] * 10, 50)
    assert not res.feasible and res.feasible_min == 100 and "100" in res.message


def test_rebalance_share_keeps_total():
    r = [(10, 20), (10, 20), (30, 50)]
    out = hm.rebalance_share(r, [True, False, False], 0.4)
    mids = [(lo + hi) / 2 for lo, hi in out]
    assert abs(sum(mids) - 70) <= 1.5 and abs(mids[0] / sum(mids) - 0.4) < 0.03
