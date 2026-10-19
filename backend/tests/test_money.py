"""VND/USD conversion, formatting, the Vietnamese/English money parser and fit_to_cost_budget (pure functions)."""

import math

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.services import hours_math as hm
from app.services import money
from app.services.money import Money, parse_money

RATE = 25_869.0


def test_to_vnd_rounds_to_thousand_and_roundtrips_within_rounding():
    assert money.to_vnd(1, "USD", RATE) == 26_000
    assert money.to_vnd(0, "USD", RATE) == 0
    assert money.to_vnd(1_234_567, "VND", RATE) == 1_235_000
    for usd in (0.5, 12.34, 5_000, 250_000.75):
        back = money.from_vnd(money.to_vnd(usd, "USD", RATE), "USD", RATE)
        assert abs(back - usd) <= 500 / RATE + 1e-9  # half a step (500 ₫) expressed in USD


def test_large_values_and_rate_changes():
    assert money.to_vnd(10_000_000, "USD", RATE) == 258_690_000_000
    a, b = money.to_vnd(100, "USD", 25_000), money.to_vnd(100, "USD", 26_000)
    assert (a, b) == (2_500_000, 2_600_000)
    with pytest.raises(ValueError):
        money.to_vnd(1, "EUR", RATE)


def test_format_money():
    assert money.format_money(1_250_000, "VND", RATE) == "1.250.000 ₫"
    assert money.format_money(0, "VND", RATE) == "0 ₫"
    assert money.format_money(2_586_900, "USD", RATE) == "$100.00"


@pytest.mark.parametrize("text,default,expected", [
    ("300tr", "VND", Money(300e6, "VND")),
    ("ngân sách 200 triệu", "VND", Money(200e6, "VND")),
    ("1,5 tỷ", "VND", Money(1.5e9, "VND")),
    ("1.5 tỷ", "VND", Money(1.5e9, "VND")),
    ("50k", "VND", Money(50_000, "VND")),
    ("50k", "USD", Money(50_000, "USD")),
    ("$5,000", "VND", Money(5_000, "USD")),
    ("5000 USD", "VND", Money(5_000, "USD")),
    ("5,000 usd", "VND", Money(5_000, "USD")),
    ("200.000.000đ", "VND", Money(200e6, "VND")),
    ("1.250.000 ₫", "VND", Money(1_250_000, "VND")),
    ("20 triệu đồng", "VND", Money(20e6, "VND")),
    ("350tr", "USD", Money(350e6, "VND")),  # Vietnamese units always mean VND
    ("budget 12,5k usd", "VND", Money(12_500, "USD")),
    ("make it 1,25 tỷ", "VND", Money(1.25e9, "VND")),
])
def test_parse_money(text, default, expected):
    got = parse_money(text, default_currency=default)
    assert got is not None and got.currency == expected.currency and math.isclose(got.amount, expected.amount)


@pytest.mark.parametrize("text", ["reduce QA by 20%", "add 12-20 hours", "5 minutes", "5 kg", "no numbers here", ""])
def test_parse_money_ignores_non_money(text):
    assert parse_money(text) is None


def _total(ranges, rates):
    return sum(hi * r for (_, hi), r in zip(ranges, rates, strict=True))


def test_fit_to_cost_budget_hits_target_without_exceeding():
    ranges = [(8, 16), (20, 40), (10, 20), (4, 8)]
    rates = [600_000, 550_000, 490_000, 790_000]
    for target in (12e6, 30e6, 45e6, 60e6):
        res = hm.fit_to_cost_budget(ranges, rates, target)
        assert res.feasible and res.achieved_cost <= target + 1e-6
        assert target - res.achieved_cost <= 0.5 * max(rates) + 1e-6
        assert all(lo <= hi and hi % 0.5 == 0 and lo % 0.5 == 0 for lo, hi in res.new_ranges)


def test_fit_to_cost_budget_infeasible_and_locked():
    ranges, rates = [(8, 16), (20, 40)], [600_000, 550_000]
    res = hm.fit_to_cost_budget(ranges, rates, 1_000_000)
    assert not res.feasible and res.new_ranges == ranges and res.feasible_min_cost > 1_000_000
    locked = hm.fit_to_cost_budget(ranges, rates, 30e6, locked=[True, False])
    assert locked.new_ranges[0] == ranges[0] and locked.feasible


@settings(max_examples=150, deadline=None)
@given(
    tasks=st.lists(st.tuples(st.integers(1, 80), st.integers(1, 80), st.sampled_from([0, 490_000, 600_000, 830_000])),
                   min_size=1, max_size=12),
    factor=st.floats(0.3, 1.8),
)
def test_fit_to_cost_budget_properties(tasks, factor):
    ranges = [(min(a, b) * 1.0, max(a, b) * 1.0) for a, b, _ in tasks]
    rates = [float(r) for _, _, r in tasks]
    current = _total(ranges, rates)
    target = round(current * factor)
    res = hm.fit_to_cost_budget(ranges, rates, float(target))
    if not res.feasible:
        assert res.new_ranges == ranges and target < res.feasible_min_cost
        return
    assert res.achieved_cost <= target + 1e-6
    for (lo, hi), (_olo, ohi) in zip(res.new_ranges, ranges, strict=True):
        assert 0 <= lo <= hi and hi >= hm.task_floor(ohi) - 1e-9 and hi % 0.5 == 0
